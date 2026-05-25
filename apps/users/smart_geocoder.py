import os
import re
import math
import requests
import time
from functools import lru_cache
from typing import Optional, Dict, List, Tuple
from django.conf import settings
import shelve
import hashlib
import json
from pathlib import Path
from functools import wraps

# Persistent cache file (override via env)
CACHE_FILE = os.getenv("GEOCODER_CACHE_PATH", "/tmp/right_route_geocode_cache.db")
CACHE_LOCK = None

def _cache_key(prefix: str, value: str) -> str:
    h = hashlib.sha256(value.encode('utf-8')).hexdigest()
    return f"{prefix}:{h}"

def cache_get(key: str):
    try:
        with shelve.open(CACHE_FILE) as db:
            return db.get(key)
    except Exception:
        return None

def cache_set(key: str, value):
    try:
        with shelve.open(CACHE_FILE) as db:
            db[key] = value
    except Exception:
        pass

def cached(prefix):
    def deco(fn):
        @wraps(fn)
        def wrapper(*args, **kwargs):
            # support being used on plain functions and classmethods
            query = None
            state_code = ''

            # kwargs preference
            if 'query' in kwargs:
                query = kwargs.get('query')
            if 'state_code' in kwargs:
                state_code = kwargs.get('state_code') or ''

            # positional fallback: (cls, query, state_code, ...)
            if query is None and len(args) >= 2:
                query = args[1]
            if not state_code and len(args) >= 3:
                state_code = args[2]

            key_src = f"{query}|{state_code}"
            k = _cache_key(prefix, key_src)
            cached_val = cache_get(k)
            if cached_val is not None:
                return cached_val
            res = fn(*args, **kwargs)
            if res:
                cache_set(k, res)
            return res
        return wrapper
    return deco

class SmartGeocoder:
    GOOGLE_API_KEY = getattr(settings, "GEOCODER_API_KEY", None) or os.getenv('GEOCODER_API_KEY', '')
    USER_AGENT = getattr(settings, "GEOCODER_USER_AGENT", None) or os.getenv('GEOCODER_USER_AGENT', 'RightRoute/1.0 (no-reply@example.com)')
    
    # API URLs
    GOOGLE_GEOCODE_URL = "https://maps.googleapis.com/maps/api/geocode/json"
    NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"
    OVERPASS_URL = "https://overpass-api.de/api/interpreter"
    
    # State Bounds
    STATE_BOUNDS = {
        'IA': {'lat_min': 40.37, 'lat_max': 43.50, 'lon_min': -96.64, 'lon_max': -90.14},
        'SD': {'lat_min': 42.48, 'lat_max': 45.94, 'lon_min': -104.06, 'lon_max': -96.43},
        'MN': {'lat_min': 43.50, 'lat_max': 49.38, 'lon_min': -97.24, 'lon_max': -89.49},
        'NE': {'lat_min': 40.00, 'lat_max': 43.00, 'lon_min': -104.05, 'lon_max': -95.31},
        'ND': {'lat_min': 45.93, 'lat_max': 49.00, 'lon_min': -104.05, 'lon_max': -96.55},
        'WI': {'lat_min': 42.49, 'lat_max': 47.08, 'lon_min': -92.89, 'lon_max': -86.25},
        'IL': {'lat_min': 36.97, 'lat_max': 42.51, 'lon_min': -91.51, 'lon_max': -87.02},
    }
    
    STATE_NAMES = {
        'IA': 'Iowa', 'SD': 'South Dakota', 'MN': 'Minnesota',
        'NE': 'Nebraska', 'ND': 'North Dakota', 'WI': 'Wisconsin',
        'IL': 'Illinois', 'KS': 'Kansas', 'MO': 'Missouri'
    }
    
    # County to State mapping
    COUNTY_TO_STATE = {
        # Iowa Counties (Northwestern)
        'LYON': 'IA', 'SIOUX': 'IA', 'OSCEOLA': 'IA', 'DICKINSON': 'IA',
        "O'BRIEN": 'IA', 'OBRIEN': 'IA', 'CLAY': 'IA', 'PALO ALTO': 'IA',
        'EMMET': 'IA', 'KOSSUTH': 'IA', 'HANCOCK': 'IA', 'WINNEBAGO': 'IA',
        'WORTH': 'IA', 'CERRO GORDO': 'IA', 'FLOYD': 'IA', 'CHICKASAW': 'IA',
        'PLYMOUTH': 'IA', 'CHEROKEE': 'IA', 'BUENA VISTA': 'IA', 'POCAHONTAS': 'IA',
        'HUMBOLDT': 'IA', 'WRIGHT': 'IA', 'FRANKLIN': 'IA', 'BUTLER': 'IA',
        'WOODBURY': 'IA', 'IDA': 'IA', 'SAC': 'IA', 'CALHOUN': 'IA',
        'WEBSTER': 'IA', 'HAMILTON': 'IA', 'HARDIN': 'IA', 'GRUNDY': 'IA',
        # South Dakota
        'ROBERTS': 'SD', 'MINNEHAHA': 'SD', 'LINCOLN': 'SD', 'BROOKINGS': 'SD',
        'CODINGTON': 'SD', 'BROWN': 'SD', 'PENNINGTON': 'SD',
        # Minnesota
        'ROCK': 'MN', 'NOBLES': 'MN', 'JACKSON': 'MN', 'MARTIN': 'MN',
    }

    # ════════════════════════════════════════════════════════════════
    # Known Highway Junctions in Iowa (Pre-computed for accuracy)
    # ════════════════════════════════════════════════════════════════
    KNOWN_JUNCTIONS = {
        ('IA-9', 'US-75'): (43.4331, -96.1907, 'Larchwood'),
        ('US-75', 'IA-9'): (43.4331, -96.1907, 'Larchwood'),
        ('IA-9', 'US-59'): (43.4303, -95.1674, 'Rock Rapids area'),
        ('US-59', 'IA-9'): (43.4303, -95.1674, 'Rock Rapids area'),
        ('US-59', 'US-18'): (43.1860, -95.6298, 'Sanborn'),
        ('US-18', 'US-59'): (43.1860, -95.6298, 'Sanborn'),
        ('US-18', 'IA-4'): (43.1125, -94.6833, 'Emmetsburg'),
        ('IA-4', 'US-18'): (43.1125, -94.6833, 'Emmetsburg'),
        ('IA-4', 'IA-3'): (42.7729, -94.2328, 'Pocahontas'),
        ('IA-3', 'IA-4'): (42.7729, -94.2328, 'Pocahontas'),
        ('IA-3', 'US-69'): (42.9500, -93.8100, 'Kanawha/Hancock'),
        ('US-69', 'IA-3'): (42.9500, -93.8100, 'Kanawha/Hancock'),
        ('US-69', 'B62'): (42.9525, -93.8105, 'Hancock County'),
        ('B62', 'US-69'): (42.9525, -93.8105, 'Hancock County'),
        # Interstate junctions
        ('I-29', 'I-90'): (43.5544, -96.7289, 'Sioux Falls'),
        ('I-90', 'I-29'): (43.5544, -96.7289, 'Sioux Falls'),
        ('I-35', 'I-80'): (41.5868, -93.6250, 'Des Moines'),
        ('I-80', 'I-35'): (41.5868, -93.6250, 'Des Moines'),
    }

    # ════════════════════════════════════════════════════════════════
    # 1. SMART STRING PARSING
    # ════════════════════════════════════════════════════════════════
    @classmethod
    def parse_raw_text(cls, raw_text: str) -> Dict:
        result = {
            'highway': None,
            'highway_type': None,
            'city': None,
            'county': None,
            'direction': None,
            'intersection_road': None,
            'raw_text': raw_text,
            'milepost': None,
            'milepost_county': None,
        }
        
        text_upper = raw_text.upper()
        
        # Extract Highway
        highway_patterns = [
            (r'\b(I-\d+)\b', 'Interstate'),
            (r'\b(US-\d+)\b', 'US Highway'),
            (r'\b([A-Z]{2}-\d+)\b', 'State Highway'),
            (r'\b([A-Z]\d+)\b', 'County Road'),
        ]
        
        for pattern, hw_type in highway_patterns:
            match = re.search(pattern, text_upper)
            if match:
                result['highway'] = match.group(1).replace(' ', '')
                result['highway_type'] = hw_type
                break
        
        # Extract City - "in [City] at" pattern
        city_patterns = [
            r'(?:in|Indiana)\s+([A-Za-z\s]+?)\s+at',
            r'(?:in|Indiana)\s+([A-Za-z\s]+?)(?:\)|$)',
            r'near\s+([A-Za-z\s]+)',
        ]
        
        for pattern in city_patterns:
            match = re.search(pattern, raw_text, re.IGNORECASE)
            if match:
                city = match.group(1).strip()
                if len(city) > 2 and city.lower() not in ['the', 'and', 'for', 'at', 'on', 'quail']:
                    result['city'] = city.title()
                    break
        
        # Extract County from parentheses at end
        county_match = re.search(r'\(([A-Za-z]+)\)$', raw_text.strip())
        if county_match:
            county = county_match.group(1).strip()
            if county.lower() not in ['indiana', 'in']:
                result['county'] = county.title()
        
        # Extract Direction
        direction_map = {
            'EASTBOUND': 'E', 'WESTBOUND': 'W',
            'NORTHBOUND': 'N', 'SOUTHBOUND': 'S',
        }
        
        for dir_text, short in direction_map.items():
            if dir_text in text_upper:
                result['direction'] = short
                break
        
        # Extract Intersection Road
        intersection_match = re.search(r'at\s+([A-Z]\s?\d+|[A-Za-z]+\s+(?:St|Ave|Blvd|Rd))', raw_text, re.IGNORECASE)
        if intersection_match:
            result['intersection_road'] = intersection_match.group(1).strip()
        
        # Extract Milepost (MP) e.g. "MP ROBERTS 252.65" or "MP 252.65"
        mp_match = re.search(r'\bMP\b[\s:,-]*([A-Za-z]+)?[\s,]*([0-9]+(?:\.[0-9]+)?)', raw_text, re.IGNORECASE)
        if mp_match:
            county_token = mp_match.group(1)
            mp_val = mp_match.group(2)
            try:
                result['milepost'] = float(mp_val)
            except Exception:
                result['milepost'] = None
            if county_token and not re.match(r'^\d', county_token):
                result['milepost_county'] = county_token.title()
        
        return result

    @classmethod
    def build_clean_query(cls, parsed: Dict, state_code: str) -> str:
        """Build clean geocoding query"""
        state_name = cls.STATE_NAMES.get(state_code, state_code)
        highway = parsed.get('highway', '')
        city = parsed.get('city')
        county = parsed.get('county')
        
        if city and highway:
            return f"{highway}, {city}, {state_name}"
        elif city:
            return f"{city}, {state_name}"
        elif county and highway:
            return f"{highway}, {county} County, {state_name}"
        elif highway:
            return f"{highway}, {state_name}"
        else:
            return f"{state_name}"

    # ════════════════════════════════════════════════════════════════
    # 2. KNOWN JUNCTION LOOKUP (Pre-computed, most accurate)
    # ════════════════════════════════════════════════════════════════
    @classmethod
    def lookup_known_junction(cls, hw1: str, hw2: str) -> Optional[Dict]:
        """
        ✅ Check pre-computed junction database first
        """
        # Normalize highway names
        hw1_norm = hw1.upper().replace(' ', '')
        hw2_norm = hw2.upper().replace(' ', '')
        
        key = (hw1_norm, hw2_norm)
        
        if key in cls.KNOWN_JUNCTIONS:
            lat, lon, city = cls.KNOWN_JUNCTIONS[key]
            print(f"[KNOWN JUNCTION] ✅ Found: {hw1} ∩ {hw2} at {city}")
            return {
                'found': True,
                'latitude': lat,
                'longitude': lon,
                'display_name': f"{hw1} and {hw2}, {city}",
                'source': 'known_junction_db',
                'confidence': 'high'
            }
        
        return None

    # ════════════════════════════════════════════════════════════════
    # 3. CONTEXT-AWARE JUNCTION DETECTION (Overpass with proximity)
    # ════════════════════════════════════════════════════════════════
    @classmethod
    def _dedupe_nodes(cls, elements: List[Dict]) -> List[Tuple[float,float]]:
        """Return unique (lat,lon) tuples from Overpass elements (rounded)."""
        seen = {}
        for el in elements:
            lat = el.get('lat')
            lon = el.get('lon')
            if lat is None or lon is None:
                continue
            key = (round(float(lat), 5), round(float(lon), 5))
            seen.setdefault(key, 0)
            seen[key] += 1
        return [(k[0], k[1], v) for k, v in seen.items()]  # lat, lon, count

    @classmethod
    def find_junction_with_context(cls, hw1: str, hw2: str, state_code: str, prev_lat: float = None, prev_lon: float = None) -> Optional[Dict]:
        """
        ✅ Find junction with proximity check to previous waypoint (improved dedupe + dynamic threshold)
        """
        # Step 1: Check known junctions first
        known = cls.lookup_known_junction(hw1, hw2)
        if known:
            return known
        
        # Step 2: Query Overpass for all possible junctions
        bounds = cls.STATE_BOUNDS.get(state_code, cls.STATE_BOUNDS['IA'])
        
        ref1 = re.search(r'(\d+)', hw1)
        ref2 = re.search(r'(\d+)', hw2)
        
        if not ref1 or not ref2:
            return None
        
        ref1 = ref1.group(1)
        ref2 = ref2.group(1)
        
        query = f"""
        [out:json][timeout:30];
        (
          way["highway"]["ref"~"{ref1}"]
            ({bounds['lat_min']},{bounds['lon_min']},{bounds['lat_max']},{bounds['lon_max']});
        )->.a;
        (
          way["highway"]["ref"~"{ref2}"]
            ({bounds['lat_min']},{bounds['lon_min']},{bounds['lat_max']},{bounds['lon_max']});
        )->.b;
        node(w.a)(w.b);
        out body;
        """
        
        try:
            print(f"[OVERPASS CONTEXT] Finding junction: {hw1} ∩ {hw2} with proximity check")
            
            response = requests.post(
                cls.OVERPASS_URL,
                data={'data': query},
                timeout=30,
                headers={'User-Agent': cls.USER_AGENT}
            )
            
            if response.status_code == 200:
                data = response.json()
                elements = data.get('elements', [])
                
                if not elements:
                    print(f"[OVERPASS CONTEXT] No junctions found")
                    return None
                
                # dedupe coordinates (many near-duplicate nodes from OSM)
                nodes = cls._dedupe_nodes(elements)  # list of (lat,lon,count)
                total = len(nodes)
                print(f"[OVERPASS CONTEXT] Found {total} unique candidate junction coords (raw elements: {len(elements)})")
                
                # If we have a previous location, find the closest junction with dynamic thresholds
                if cls._valid_latlon(prev_lat, prev_lon) and total > 0:
                    best = None
                    min_distance = float('inf')
                    for lat, lon, cnt in nodes:
                        # check bounds again defensively
                        if not cls._is_within_bounds(lat, lon, state_code):
                            continue
                        dist = cls._calculate_distance(float(prev_lat), float(prev_lon), lat, lon)
                        # slight preference for clustered nodes (higher cnt) by subtracting small amount
                        score = dist - (0.01 * cnt)
                        if score < min_distance:
                            min_distance = score
                            best = (lat, lon, dist)
                        # log only close candidates to avoid huge logs
                        if dist <= float(os.getenv("GEOCODER_OVERPASS_DETAIL_MILES", "10")):
                            print(f"[OVERPASS CONTEXT] Nearby junction at ({lat:.4f}, {lon:.4f}) is {dist:.1f} miles from previous (count={cnt})")
                    
                    if best:
                        lat, lon, real_dist = best[0], best[1], best[2]
                        threshold = cls._intersection_threshold(hw1, hw2, state_code)
                        # allow slightly larger threshold for interstates
                        if hw1.upper().startswith('I-') or hw2.upper().startswith('I-'):
                            threshold = max(threshold, float(os.getenv("GEOCODER_INTERSTATE_RELAX_MILES", "60")))
                        print(f"[OVERPASS CONTEXT] ✅ Selected closest: ({lat:.4f}, {lon:.4f}), {real_dist:.1f} miles (threshold {threshold:.1f})")
                        if real_dist > threshold:
                            print(f"[OVERPASS CONTEXT] Selected junction {real_dist:.1f}mi > threshold {threshold:.1f}; rejecting proximity choose")
                            return None
                        return {
                            'found': True,
                            'latitude': lat,
                            'longitude': lon,
                            'display_name': f"{hw1} and {hw2}, {cls.STATE_NAMES.get(state_code, state_code)}",
                            'source': 'overpass_context',
                            'confidence': 'high',
                            'distance_from_prev': real_dist
                        }
                    else:
                        print("[OVERPASS CONTEXT] No suitable candidate near previous point")
                        return None
                else:
                    # No previous location: pick the densest cluster (highest count) within bounds
                    nodes_sorted = sorted(nodes, key=lambda x: x[2], reverse=True)
                    for lat, lon, cnt in nodes_sorted:
                        if cls._is_within_bounds(lat, lon, state_code):
                            print(f"[OVERPASS CONTEXT] ✅ Picked clustered junction: ({lat:.4f}, {lon:.4f}) count={cnt}")
                            return {
                                'found': True,
                                'latitude': lat,
                                'longitude': lon,
                                'display_name': f"{hw1} and {hw2}, {cls.STATE_NAMES.get(state_code, state_code)}",
                                'source': 'overpass_api',
                                'confidence': 'high'
                            }
                            
        except Exception as e:
            print(f"[OVERPASS CONTEXT] Error: {e}")
        
        return None

    # ════════════════════════════════════════════════════════════════
    # 4. GOOGLE GEOCODING WITH STATE RESTRICTION
    # ════════════════════════════════════════════════════════════════
    @classmethod
    @cached("google")
    def geocode_with_google(cls, query: str, state_code: str) -> Optional[Dict]:
        """Google Geocoding API with components filter (with stronger validation)."""
        if not cls.GOOGLE_API_KEY:
            print("[GOOGLE GEOCODE] ⚠️ No API key, skipping...")
            return None
        
        try:
            params = {
                'address': query,
                'components': f'administrative_area:{state_code}|country:US',
                'key': cls.GOOGLE_API_KEY,
                'region': state_code.lower()
            }
            print(f"[GOOGLE GEOCODE] Query: {query} | State: {state_code}")
            response = requests.get(cls.GOOGLE_GEOCODE_URL, params=params, timeout=10)
            if response.status_code != 200:
                snippet = (response.text or "")[:300].replace("\n", " ")
                print(f"[GOOGLE GEOCODE] HTTP {response.status_code} - snippet: {snippet!r}")
                return None
            try:
                data = response.json()
            except ValueError as je:
                snippet = (response.text or "")[:300].replace("\n", " ")
                print(f"[GOOGLE GEOCODE] JSON decode error: {je} - snippet: {snippet!r}")
                return None
            
            if data.get('status') == 'OK' and data.get('results'):
                result = data['results'][0]
                location = result['geometry']['location']
                lat = location['lat']
                lon = location['lng']

                # Validate administrative area matches expected state (short_name or long_name)
                addr_comps = result.get('address_components', [])
                state_match = False
                expected_state_name = cls.STATE_NAMES.get(state_code, state_code)
                for comp in addr_comps:
                    if 'administrative_area_level_1' in comp.get('types', []):
                        short = comp.get('short_name', '').upper()
                        longn = comp.get('long_name', '')
                        if short == state_code.upper() or longn.lower() == expected_state_name.lower():
                            state_match = True
                            break

                if not state_match:
                    # sometimes Google returns a place with missing component; discard to avoid cross-state matches
                    print(f"[GOOGLE GEOCODE] Result administrative area mismatch for {query}; got: {[(c.get('short_name'), c.get('types')) for c in addr_comps]}")
                    # allow if the coordinates are within our state bounds (defensive)
                    if not cls._is_within_bounds(lat, lon, state_code):
                        return None

                # Optional: prefer results that contain the highway/ref string (if query included highway)
                # extract highway token from query if present (I-29, SD-42, etc.)
                ref_match = re.search(r'\b([AIU]{1,2}-\d+)\b', query.upper())
                if ref_match:
                    ref = ref_match.group(1)
                    formatted = result.get('formatted_address', '').upper()
                    if ref not in formatted and not cls._is_within_bounds(lat, lon, state_code):
                        print(f"[GOOGLE GEOCODE] Result does not mention {ref} in address; rejecting: {formatted}")
                        return None

                if cls._is_within_bounds(lat, lon, state_code):
                    print(f"[GOOGLE GEOCODE] ✅ Found: {lat}, {lon}")
                    return {
                        'latitude': lat,
                        'longitude': lon,
                        'display_name': result.get('formatted_address', query),
                        'source': 'google_geocode',
                        'confidence': 'high',
                        'query_used': query
                    }
                else:
                    print(f"[GOOGLE GEOCODE] ⚠️ Result outside {state_code} bounds")
            else:
                print(f"[GOOGLE GEOCODE] No results for: {query}")
                
        except Exception as e:
            print(f"[GOOGLE GEOCODE] Error: {e}")
        
        return None

    # ════════════════════════════════════════════════════════════════
    # 5. NOMINATIM FALLBACK WITH BETTER QUERY
    # ════════════════════════════════════════════════════════════════
    @classmethod
    def geocode_with_nominatim(cls, query: str, state_code: str) -> Optional[Dict]:
        """Nominatim geocoding as fallback"""
        state_name = cls.STATE_NAMES.get(state_code, state_code)
        full_query = f"{query}, {state_name}, USA"
        bounds = cls.STATE_BOUNDS.get(state_code, cls.STATE_BOUNDS['IA'])
        
        try:
            time.sleep(0.5)
            
            params = {
                'q': full_query,
                'format': 'json',
                'limit': 5,
                'countrycodes': 'us',
                'addressdetails': 1
            }
            
            print(f"[NOMINATIM] Query: {full_query}")
            
            response = requests.get(
                cls.NOMINATIM_URL,
                params=params,
                headers={'User-Agent': cls.USER_AGENT},
                timeout=10
            )
            
            for result in response.json():
                lat = float(result['lat'])
                lon = float(result['lon'])
                
                if cls._is_within_bounds(lat, lon, state_code):
                    print(f"[NOMINATIM] ✅ Found: {lat}, {lon}")
                    return {
                        'latitude': lat,
                        'longitude': lon,
                        'display_name': result.get('display_name'),
                        'source': 'nominatim',
                        'confidence': 'medium',
                        'query_used': full_query
                    }
                    
        except Exception as e:
            print(f"[NOMINATIM] Error: {e}")
        
        return None

    # ════════════════════════════════════════════════════════════════
    # 6. CITY-BASED GEOCODING (For segments with city names)
    # ════════════════════════════════════════════════════════════════
    @classmethod
    def geocode_by_city(cls, city: str, highway: str, state_code: str) -> Optional[Dict]:
        """
        ✅ Geocode using city name when available
        This is more reliable than highway junction for known cities
        """
        state_name = cls.STATE_NAMES.get(state_code, state_code)
        
        # Try with highway first
        if highway:
            query = f"{highway}, {city}, {state_name}"
        else:
            query = f"{city}, {state_name}"
        
        # Try Google first
        result = cls.geocode_with_google(query, state_code)
        if result:
            return result
        
        # Fallback to Nominatim
        return cls.geocode_with_nominatim(query, state_code)

    # ════════════════════════════════════════════════════════════════
    # MAIN SMART GEOCODE METHOD
    # ════════════════════════════════════════════════════════════════
    @classmethod
    def smart_geocode(cls, raw_text: str, previous_highway: str, state_code: str,
                      prev_lat: float = None, prev_lon: float = None) -> Dict:
        """
        ✅ Main Smart Geocoding Method (updated)
        - If previous_highway present, first try a Google "Intersection of A and B, STATE" query
        - Falls back to existing logic (known junctions, city-based, overpass, nominatim)
        """
        parsed = cls.parse_raw_text(raw_text)
        current_highway = parsed.get('highway')
        city = parsed.get('city')
        county = parsed.get('county')

        state_name = cls.STATE_NAMES.get(state_code, state_code)
        force_google = False
        try:
            # avoid direct Django import in some contexts; read env fallback
            from django.conf import settings as _settings
            force_google = getattr(_settings, "GEOCODER_FORCE_GOOGLE", False)
        except Exception:
            pass

        print(f"\n[SMART GEOCODE] Raw: {raw_text}")
        print(f"[SMART GEOCODE] Parsed: {parsed}")
        print(f"[SMART GEOCODE] State: {state_code}, Previous: {previous_highway} | prev_loc=({prev_lat},{prev_lon})")

        # If MP present -> try MP-targeted logic first (best-effort)
        mp = parsed.get('milepost')
        mp_county = parsed.get('milepost_county')
        if mp is not None:
            state_name = cls.STATE_NAMES.get(state_code, state_code)
            mp_query = f"{current_highway} milepost {mp}"
            if mp_county:
                mp_query = f"{current_highway} milepost {mp} {mp_county} County, {state_name}"
            else:
                mp_query = f"{current_highway} milepost {mp}, {state_name}"

            print(f"[SMART GEOCODE] Trying milepost query: {mp_query}")
            mp_result = cls.geocode_with_google(mp_query, state_code)
            if mp_result:
                mp_result['match_type'] = 'milepost_google'
                mp_result['query_used'] = mp_query
                # sanity-check distance from prev (only if prev is valid)
                if cls._valid_latlon(prev_lat, prev_lon) and mp_result.get('latitude') and mp_result.get('longitude'):
                    dist_miles = cls._calculate_distance(float(prev_lat), float(prev_lon),
                                                         float(mp_result['latitude']), float(mp_result['longitude']))
                    if dist_miles < float(os.getenv("GEOCODER_INTERSECTION_MAX_MILES", "50")):
                        return mp_result
                    else:
                        print(f"[SANITY] Milepost result {dist_miles:.1f} miles from previous; ignoring")
            # If Google failed for MP, try Overpass approximation if county provided
            if mp_county:
                print(f"[OVERPASS CONTEXT] Trying to approx milepost by finding {current_highway} nodes in {mp_county}")
                # best-effort: fallthrough to main logic / other fallbacks

        # If we have both previous and current highways, try Overpass/known-junction first
        if previous_highway and current_highway:
            # guard: don't query intersection if same highway
            if previous_highway == current_highway:
                print("[SMART GEOCODE] previous == current highway; skipping self-intersection query")
            else:
                # 1) try known junction DB
                known = cls.lookup_known_junction(previous_highway, current_highway)
                if known:
                    return known

                # 2) try Overpass context (closest to previous)
                junction = cls.find_junction_with_context(previous_highway, current_highway, state_code, prev_lat, prev_lon)
                if junction and junction.get('found'):
                    return {
                        'query_used': f"{previous_highway} and {current_highway}",
                        'latitude': junction['latitude'],
                        'longitude': junction['longitude'],
                        'display_name': junction.get('display_name'),
                        'source': junction.get('source'),
                        'confidence': junction.get('confidence'),
                        'match_type': 'overpass_junction'
                    }

                # 3) try Google intersection (with sanity distance threshold)
                force_google = getattr(settings, "GEOCODER_FORCE_GOOGLE", False)
                intersection_query = f"Intersection of {previous_highway} and {current_highway}, {state_name}"
                if force_google or True:
                    google_result = cls.geocode_with_google(intersection_query, state_code)
                    if google_result:
                        # distance sanity check (miles)
                        if cls._valid_latlon(prev_lat, prev_lon) and google_result.get('latitude') and google_result.get('longitude'):
                            dist_miles = cls._calculate_distance(float(prev_lat), float(prev_lon),
                                                                 float(google_result['latitude']), float(google_result['longitude']))
                            print(f"[SANITY] Distance from prev: {dist_miles:.1f} miles")
                            threshold = cls._intersection_threshold(previous_highway, current_highway, state_code)
                            if dist_miles <= threshold:
                                google_result['match_type'] = 'intersection_google'
                                google_result['query_used'] = intersection_query
                                return google_result
                            else:
                                print("[SANITY] Intersection result too far; rejecting and trying fallbacks")
                        else:
                            # no reliable prev coord -> accept google intersection result
                            google_result['match_type'] = 'intersection_google'
                            google_result['query_used'] = intersection_query
                            return google_result

                # 4) continue to other fallbacks below

        # If city is available try city-based geocoding next
        if city:
            result = cls.geocode_by_city(city, current_highway, state_code)
            if result:
                result['match_type'] = 'city_based'
                return result

        # County-based
        if county and current_highway:
            clean_query = f"{current_highway}, {county} County, {state_name}"
            result = cls.geocode_with_google(clean_query, state_code)
            if result:
                result['match_type'] = 'county_based'
                return result
            result = cls.geocode_with_nominatim(clean_query, state_code)
            if result:
                result['match_type'] = 'county_based'
                return result

        # Highway-only fallback (Google then Nominatim)
        clean_query = cls.build_clean_query(parsed, state_code)
        result = cls.geocode_with_google(clean_query, state_code)
        if result:
            result['match_type'] = 'google_fallback'
            return result

        result = cls.geocode_with_nominatim(clean_query, state_code)
        if result:
            result['match_type'] = 'nominatim_fallback'
            return result

        # final failure
        return {
            'query_used': clean_query,
            'latitude': None,
            'longitude': None,
            'display_name': raw_text,
            'source': 'none',
            'confidence': 'low',
            'match_type': 'failed'
        }

    # ════════════════════════════════════════════════════════════════
    # UTILITY METHODS
    # ════════════════════════════════════════════════════════════════
    @classmethod
    def _is_within_bounds(cls, lat: float, lon: float, state_code: str) -> bool:
        """Check if coordinates are within state bounds"""
        bounds = cls.STATE_BOUNDS.get(state_code)
        if not bounds:
            return True
        
        within = (
            bounds['lat_min'] <= lat <= bounds['lat_max'] and
            bounds['lon_min'] <= lon <= bounds['lon_max']
        )
        
        if not within:
            print(f"[BOUNDS CHECK] ❌ ({lat:.4f}, {lon:.4f}) is outside {state_code}!")
        
        return within

    @classmethod
    def _calculate_distance(cls, lat1: float, lon1: float, lat2: float, lon2: float) -> float:
        """Calculate distance in miles (Haversine)"""
        R = 3959

        lat1_rad = math.radians(lat1)
        lat2_rad = math.radians(lat2)
        delta_lat = math.radians(lat2 - lat1)
        delta_lon = math.radians(lon2 - lon1)

        a = math.sin(delta_lat/2)**2 + math.cos(lat1_rad) * math.cos(lat2_rad) * math.sin(delta_lon/2)**2
        c = 2 * math.atan2(math.sqrt(a), math.sqrt(1-a))

        return R * c

    @staticmethod
    def haversine_km(a_lat: float, a_lng: float, b_lat: float, b_lng: float) -> float:
        """Module haversine in kilometers (kept as static utility inside class)"""
        R = 6371.0
        phi1, phi2 = math.radians(a_lat), math.radians(b_lat)
        dphi = math.radians(b_lat - a_lat)
        dlambda = math.radians(b_lng - a_lng)
        a_ = math.sin(dphi/2)**2 + math.cos(phi1)*math.cos(phi2)*math.sin(dlambda/2)**2
        c = 2 * math.atan2(math.sqrt(a_), math.sqrt(1-a_))
        return R * c

    @classmethod
    def validate_route_continuity(cls, waypoints: List[Dict], max_distance_miles: float = 100) -> List[Dict]:
        """Validate consecutive waypoints are not too far apart"""
        for i, wp in enumerate(waypoints):
            geocode = wp.get('geocode', {})
            lat = geocode.get('latitude')
            lon = geocode.get('longitude')

            if i > 0 and lat and lon:
                prev_geocode = waypoints[i-1].get('geocode', {})
                prev_lat = prev_geocode.get('latitude')
                prev_lon = prev_geocode.get('longitude')

                if prev_lat and prev_lon:
                    distance = cls._calculate_distance(prev_lat, prev_lon, lat, lon)

                    if distance > max_distance_miles:
                        print(f"[SANITY CHECK] ⚠️ Point {i+1} is {distance:.1f} miles from point {i}!")
                        geocode['warning'] = f"Distance from previous point: {distance:.1f} miles"
                        geocode['needs_verification'] = True

        return waypoints

    @classmethod
    def detect_state_from_text(cls, text: str, default_state: str = 'IA') -> str:
        """Detect state from text"""
        text_upper = text.upper()

        for county, state in cls.COUNTY_TO_STATE.items():
            if county in text_upper:
                return state

        state_match = re.search(r'\b([A-Z]{2})-\d+', text_upper)
        if state_match:
            state = state_match.group(1)
            if state in cls.STATE_BOUNDS:
                return state

        return default_state

    @classmethod
    def _valid_latlon(cls, lat, lon) -> bool:
        try:
            lat_f = float(lat)
            lon_f = float(lon)
        except Exception:
            return False
        return -90.0 <= lat_f <= 90.0 and -180.0 <= lon_f <= 180.0

    @classmethod
    def _intersection_threshold(cls, prev_hw: str, curr_hw: str, state_code: str = None) -> float:
        """
        Dynamic threshold in miles:
         - Interstate intersections: allow larger radius (default 50)
         - US highways: medium (30)
         - State/County: smaller (10-20)
        Can be overridden via GEOCODER_INTERSECTION_MAX_MILES env var (upper bound).
        """
        env_max = float(os.getenv("GEOCODER_INTERSECTION_MAX_MILES", "50"))
        # determine by prefixes
        def hw_type(hw):
            if not hw:
                return 'state'
            hw = hw.upper()
            if hw.startswith('I-'):
                return 'interstate'
            if hw.startswith('US-'):
                return 'us'
            if re.match(r'^[A-Z]{2}-\d+', hw):
                return 'state'
            return 'county'
        p_type = hw_type(prev_hw)
        c_type = hw_type(curr_hw)
        # pick the coarser of the two
        rank = {'interstate': 50.0, 'us': 30.0, 'state': 20.0, 'county': 10.0}
        base = max(rank.get(p_type, 20.0), rank.get(c_type, 20.0))
        # allow smaller values for small states if provided
        return min(base, env_max)

    @classmethod
    def smart_geocode_auto(cls, raw_text: str, previous_highway: str, state_code: str,
                           prev_lat: float = None, prev_lon: float = None) -> Dict:
        """
        Auto-resolution wrapper:
         - Calls smart_geocode first
         - If that fails or low-confidence, attempts deterministic fallbacks:
           * normalize query (case, punctuation)
           * try Nominatim if Google failed / returned out-of-bounds
           * try Overpass context again with relaxed proximity
         - Returns dict with:
            - existing geocode keys (latitude, longitude, confidence, source, ...)
            - 'auto_resolved': bool
            - 'auto_attempts': list of {'step':..., 'result':... , 'reason':...}
        """
        attempts = []
        try:
            primary = cls.smart_geocode(raw_text, previous_highway, state_code, prev_lat, prev_lon)
        except TypeError:
            primary = cls.smart_geocode(raw_text, previous_highway, state_code)
        # store only a small summary to avoid circular references
        attempts.append({'step': 'primary', 'result_summary': cls._summarize_result(primary)})

        # if primary looks good, return
        lat = primary.get('latitude')
        lon = primary.get('longitude')
        conf = primary.get('confidence')
        if lat and lon and conf == 'high':
            primary['auto_resolved'] = True
            primary['auto_attempts'] = attempts
            return primary

        # collect reasons
        reasons = []
        if not lat or not lon:
            reasons.append('no_coords')
        if conf != 'high':
            reasons.append('low_confidence')

        # 1) try normalized query to Google
        norm_q = re.sub(r'\s+', ' ', raw_text.strip())
        if norm_q != raw_text:
            g = cls.geocode_with_google(norm_q, state_code)
            attempts.append({'step': 'google_normalized', 'query': norm_q, 'result_summary': cls._summarize_result(g)})
            if g and g.get('latitude') and g.get('longitude'):
                g['auto_resolved'] = True
                g['auto_attempts'] = attempts
                g['fail_reasons'] = reasons
                return g

        # 2) try Nominatim fallback
        nom = cls.geocode_with_nominatim(norm_q, state_code)
        attempts.append({'step': 'nominatim', 'query': norm_q, 'result_summary': cls._summarize_result(nom)})
        if nom and nom.get('latitude') and nom.get('longitude'):
            nom['auto_resolved'] = True
            nom['auto_attempts'] = attempts
            nom['fail_reasons'] = reasons
            return nom

        # 3) relax overpass proximity (increase threshold) and retry junction/context
        try:
            # temporarily increase env threshold for this attempt
            old = os.getenv("GEOCODER_INTERSECTION_MAX_MILES")
            os.environ["GEOCODER_INTERSECTION_MAX_MILES"] = str(max(100, float(old) if old else 100))
        except Exception:
            pass
        junction = cls.find_junction_with_context(previous_highway, primary.get('structured_highway') or primary.get('highway') or previous_highway, state_code, prev_lat, prev_lon)
        attempts.append({'step': 'overpass_relaxed', 'result_summary': cls._summarize_result(junction)})
        if junction and junction.get('found'):
             res = {
                 'latitude': junction['latitude'],
                 'longitude': junction['longitude'],
                 'display_name': junction.get('display_name'),
                 'source': junction.get('source', 'overpass'),
                 'confidence': 'high',
                 'match_type': 'overpass_relaxed',
                 'auto_resolved': True,
                 'auto_attempts': attempts,
                 'fail_reasons': reasons
             }
             return res

        # restore env if changed
        try:
            if old is None:
                del os.environ["GEOCODER_INTERSECTION_MAX_MILES"]
            else:
                os.environ["GEOCODER_INTERSECTION_MAX_MILES"] = old
        except Exception:
            pass

        # final: return primary with diagnostics
        primary['auto_resolved'] = False
        primary['auto_attempts'] = attempts
        primary['fail_reasons'] = reasons
        return primary

    @classmethod
    def _summarize_result(cls, res: dict) -> dict:
        """Return small summary of a geocode result to avoid embedding full objects (prevents cycles)."""
        if not isinstance(res, dict):
            return {'raw': str(res)}
        return {
            'latitude': res.get('latitude'),
            'longitude': res.get('longitude'),
            'confidence': res.get('confidence'),
            'source': res.get('source'),
            'match_type': res.get('match_type'),
            'query_used': res.get('query_used'),
            'display_name': res.get('display_name'),
        }

