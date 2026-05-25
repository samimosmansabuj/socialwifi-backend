# Junction finder service for highways using Overpass API and Nominatim
import requests
import time
import re
from functools import lru_cache


class JunctionService:
    """
    ✅ FIXED: Real-time Highway Junction Detection
    - County-based State Detection
    - Clean Nominatim queries (no "Junction:" prefix)
    - Better Overpass regex patterns
    """
    
    OVERPASS_URL = "https://overpass-api.de/api/interpreter"
    NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"
    
    # ════════════════════════════════════════════════════════════════
    # ✅ FIX 1: County-based State Detection Database
    # ════════════════════════════════════════════════════════════════
    COUNTY_TO_STATE = {
        # South Dakota Counties
        'ROBERTS': 'SD', 'MINNEHAHA': 'SD', 'LINCOLN': 'SD', 'UNION': 'SD',
        'CLAY': 'SD', 'TURNER': 'SD', 'HUTCHINSON': 'SD', 'YANKTON': 'SD',
        'BON HOMME': 'SD', 'CHARLES MIX': 'SD', 'DOUGLAS': 'SD', 'AURORA': 'SD',
        'DAVISON': 'SD', 'HANSON': 'SD', 'MCCOOK': 'SD', 'LAKE': 'SD',
        'MOODY': 'SD', 'BROOKINGS': 'SD', 'DEUEL': 'SD', 'GRANT': 'SD',
        'CODINGTON': 'SD', 'HAMLIN': 'SD', 'KINGSBURY': 'SD', 'BEADLE': 'SD',
        'SPINK': 'SD', 'CLARK': 'SD', 'DAY': 'SD', 'MARSHALL': 'SD',
        'BROWN': 'SD', 'EDMUNDS': 'SD', 'FAULK': 'SD', 'HAND': 'SD',
        'BUFFALO': 'SD', 'JERAULD': 'SD', 'SANBORN': 'SD', 'MINER': 'SD',
        'PENNINGTON': 'SD', 'MEADE': 'SD', 'LAWRENCE': 'SD', 'BUTTE': 'SD',
        'CUSTER': 'SD', 'FALL RIVER': 'SD',
        
        # Iowa Counties  
        'LYON': 'IA', 'OSCEOLA': 'IA', 'DICKINSON': 'IA', 'EMMET': 'IA',
        'KOSSUTH': 'IA', 'WINNEBAGO': 'IA', 'WORTH': 'IA', 'MITCHELL': 'IA',
        'HOWARD': 'IA', 'WINNESHIEK': 'IA', 'ALLAMAKEE': 'IA', 'SIOUX': 'IA',
        "O'BRIEN": 'IA', 'OBRIEN': 'IA', 'PALO ALTO': 'IA', 'HANCOCK': 'IA',
        'CERRO GORDO': 'IA', 'FLOYD': 'IA', 'CHICKASAW': 'IA', 'FAYETTE': 'IA',
        'CLAYTON': 'IA', 'PLYMOUTH': 'IA', 'CHEROKEE': 'IA', 'BUENA VISTA': 'IA',
        'POCAHONTAS': 'IA', 'HUMBOLDT': 'IA', 'WRIGHT': 'IA', 'FRANKLIN': 'IA',
        'BUTLER': 'IA', 'BREMER': 'IA', 'WOODBURY': 'IA', 'IDA': 'IA',
        'SAC': 'IA', 'CALHOUN': 'IA', 'WEBSTER': 'IA', 'HAMILTON': 'IA',
        'HARDIN': 'IA', 'GRUNDY': 'IA', 'BLACK HAWK': 'IA', 'BUCHANAN': 'IA',
        'DELAWARE': 'IA', 'DUBUQUE': 'IA', 'MONONA': 'IA', 'CRAWFORD': 'IA',
        'CARROLL': 'IA', 'GREENE': 'IA', 'BOONE': 'IA', 'STORY': 'IA',
        'MARSHALL': 'IA', 'TAMA': 'IA', 'BENTON': 'IA', 'LINN': 'IA',
        'JONES': 'IA', 'JACKSON': 'IA', 'HARRISON': 'IA', 'SHELBY': 'IA',
        'AUDUBON': 'IA', 'GUTHRIE': 'IA', 'DALLAS': 'IA', 'POLK': 'IA',
        'JASPER': 'IA', 'POWESHIEK': 'IA', 'IOWA': 'IA', 'JOHNSON': 'IA',
        'CEDAR': 'IA', 'CLINTON': 'IA', 'SCOTT': 'IA',
        
        # Minnesota Counties (border areas)
        'ROCK': 'MN', 'NOBLES': 'MN', 'JACKSON': 'MN', 'MARTIN': 'MN',
        'FARIBAULT': 'MN', 'FREEBORN': 'MN', 'MOWER': 'MN', 'FILLMORE': 'MN',
        'HOUSTON': 'MN', 'PIPESTONE': 'MN', 'MURRAY': 'MN', 'COTTONWOOD': 'MN',
        'WATONWAN': 'MN', 'BLUE EARTH': 'MN',
        
        # Nebraska Counties
        'DAKOTA': 'NE', 'DIXON': 'NE', 'CEDAR': 'NE', 'KNOX': 'NE',
        'THURSTON': 'NE', 'BURT': 'NE', 'CUMING': 'NE', 'STANTON': 'NE',
    }
    
    # State Bounding Boxes
    STATE_BOUNDS = {
        'SD': {'s': 42.48, 'n': 45.94, 'w': -104.06, 'e': -96.43},
        'IA': {'s': 40.37, 'n': 43.50, 'w': -96.64, 'e': -90.14},
        'MN': {'s': 43.50, 'n': 49.38, 'w': -97.24, 'e': -89.49},
        'NE': {'s': 40.00, 'n': 43.00, 'w': -104.05, 'e': -95.31},
        'ND': {'s': 45.93, 'n': 49.00, 'w': -104.05, 'e': -96.55},
    }
    
    STATE_NAMES = {
        'SD': 'South Dakota', 'IA': 'Iowa', 'MN': 'Minnesota',
        'NE': 'Nebraska', 'ND': 'North Dakota', 'KS': 'Kansas',
        'MO': 'Missouri', 'IL': 'Illinois', 'WI': 'Wisconsin'
    }

    # ════════════════════════════════════════════════════════════════
    # ✅ FIX 1: County-based State Detection
    # ════════════════════════════════════════════════════════════════
    @classmethod
    def detect_state_from_text(cls, text: str, default_state: str = 'IA') -> str:
        """
        টেক্সট থেকে County নাম খুঁজে State বের করুন
        Example: "MP ROBERTS 252.65" → Roberts County → SD
        """
        text_upper = text.upper()
        
        # Mile Marker দিয়ে স্টেট ডিটেক্ট
        mp_match = re.search(r'MP\s+([A-Z]+)\s+(\d+)', text_upper)
        if mp_match:
            county_name = mp_match.group(1)
            mile_marker = float(mp_match.group(2))
            
            # Roberts County, SD চেক
            if county_name in cls.COUNTY_TO_STATE:
                detected_state = cls.COUNTY_TO_STATE[county_name]
                print(f"[STATE DETECT] Found county '{county_name}' → State: {detected_state}")
                return detected_state
            
            # Iowa I-29 শুধু mile marker 0-151 পর্যন্ত (Council Bluffs to Sioux City)
            # SD I-29 mile marker 0-253+ (Sioux Falls to ND border)
            if 'I-29' in text_upper and mile_marker > 151:
                print(f"[STATE DETECT] Mile marker {mile_marker} > 151 on I-29 → SD")
                return 'SD'
        
        # Parentheses থেকে county বের করুন
        county_match = re.search(r'\(([A-Za-z\s]+)\)', text)
        if county_match:
            county = county_match.group(1).upper().strip()
            if county in cls.COUNTY_TO_STATE:
                detected_state = cls.COUNTY_TO_STATE[county]
                print(f"[STATE DETECT] Found county in parens '{county}' → State: {detected_state}")
                return detected_state
        
        # Highway prefix থেকে state বের করুন (SD-11 → SD)
        state_match = re.search(r'\b([A-Z]{2})-\d+', text_upper)
        if state_match:
            state_code = state_match.group(1)
            if state_code in cls.STATE_BOUNDS:
                print(f"[STATE DETECT] Found state prefix '{state_code}'")
                return state_code
        
        return default_state

    @classmethod
    def _extract_ref(cls, highway: str) -> str:
        """Highway reference number বের করুন"""
        match = re.search(r'(\d+)', highway)
        return match.group(1) if match else highway

    @classmethod
    def _clean_highway_name(cls, highway: str) -> str:
        """Highway name clean করুন - শুধু নাম্বার রাখুন"""
        hw = highway.upper().strip()
        # Remove state prefix for interstate
        hw = re.sub(r'^(I|US|IA|SD|MN|NE|ND|KS)-?', '', hw)
        return hw

    # ════════════════════════════════════════════════════════════════
    # Main Junction Finding Method
    # ════════════════════════════════════════════════════════════════
    @classmethod
    @lru_cache(maxsize=1000)
    def find_junction(cls, hw1: str, hw2: str, state: str = 'SD') -> dict:
        """
        দুটি Highway এর intersection খুঁজুন
        """
        print(f"\n[JUNCTION SERVICE] 🔍 Finding: {hw1} ∩ {hw2} in {state}")
        
        # Method 1: Overpass API (সবচেয়ে নির্ভুল)
        result = cls._overpass_junction(hw1, hw2, state)
        if result.get('found'):
            print(f"[JUNCTION SERVICE] ✅ Found via Overpass!")
            return result
        
        # Method 2: Clean Nominatim Query
        result = cls._nominatim_junction_clean(hw1, hw2, state)
        if result.get('found'):
            print(f"[JUNCTION SERVICE] ✅ Found via Nominatim!")
            return result
        
        print(f"[JUNCTION SERVICE] ❌ Not found: {hw1} ∩ {hw2}")
        return {'found': False}

    # ════════════════════════════════════════════════════════════════
    # ✅ FIX 3: Better Overpass Query with regex for highway variations
    # ════════════════════════════════════════════════════════════════
    @classmethod
    def _overpass_junction(cls, hw1: str, hw2: str, state: str) -> dict:
        """Overpass API দিয়ে junction খুঁজুন"""
        bounds = cls.STATE_BOUNDS.get(state, cls.STATE_BOUNDS['SD'])
        
        ref1 = cls._extract_ref(hw1)
        ref2 = cls._extract_ref(hw2)
        
        # ✅ FIX: Better regex - handles "I 29", "I-29", "Interstate 29" variations
        # Highway type detect করুন
        hw1_type = 'I' if hw1.upper().startswith('I-') or hw1.upper().startswith('I ') else ''
        hw2_type = 'I' if hw2.upper().startswith('I-') or hw2.upper().startswith('I ') else ''
        
        # Build regex patterns
        if hw1_type == 'I':
            pattern1 = f"(I|Interstate)[ -]?{ref1}"
        else:
            pattern1 = f"(US|{state})?[ -]?{ref1}"
            
        if hw2_type == 'I':
            pattern2 = f"(I|Interstate)[ -]?{ref2}"
        else:
            pattern2 = f"(US|{state})?[ -]?{ref2}"
        
        query = f"""
        [out:json][timeout:30];
        (
          way["highway"~"motorway|trunk|primary|secondary"]["ref"~"{pattern1}",i]
            ({bounds['s']},{bounds['w']},{bounds['n']},{bounds['e']});
        )->.roads1;
        (
          way["highway"~"motorway|trunk|primary|secondary"]["ref"~"{pattern2}",i]
            ({bounds['s']},{bounds['w']},{bounds['n']},{bounds['e']});
        )->.roads2;
        node(w.roads1)(w.roads2);
        out body 1;
        """
        
        try:
            print(f"[OVERPASS] Querying: {pattern1} ∩ {pattern2} in {state}")
            
            response = requests.post(
                cls.OVERPASS_URL,
                data={'data': query},
                timeout=30,
                headers={'User-Agent': 'RightRoute/1.0'}
            )
            
            if response.status_code == 200:
                data = response.json()
                elements = data.get('elements', [])
                
                if elements:
                    node = elements[0]
                    lat, lon = node['lat'], node['lon']
                    
                    print(f"[OVERPASS] ✅ Found: {lat}, {lon}")
                    
                    return {
                        'found': True,
                        'latitude': lat,
                        'longitude': lon,
                        'display_name': f"{hw1} and {hw2}, {cls.STATE_NAMES.get(state, state)}",
                        'source': 'overpass_api',
                        'confidence': 'high'
                    }
                else:
                    print(f"[OVERPASS] No intersection found")
            else:
                print(f"[OVERPASS] Error: {response.status_code}")
                
        except Exception as e:
            print(f"[OVERPASS] Exception: {e}")
        
        return {'found': False}

    # ════════════════════════════════════════════════════════════════
    # ✅ FIX 2: Clean Nominatim Queries - NO "Junction:" prefix, NO "∩" symbol
    # ════════════════════════════════════════════════════════════════
    @classmethod
    def _nominatim_junction_clean(cls, hw1: str, hw2: str, state: str) -> dict:
        """
        ✅ FIXED: Clean Nominatim queries
        - "Junction:" prefix বাদ
        - "∩" symbol বাদ
        - শুধু "and" দিয়ে intersection query
        """
        state_name = cls.STATE_NAMES.get(state, state)
        bounds = cls.STATE_BOUNDS.get(state, cls.STATE_BOUNDS['SD'])
        
        # ✅ FIXED QUERIES - Clean format
        queries = [
            f"{hw1} and {hw2}, {state_name}",              # Best: "I-29 and I-90, South Dakota"
            f"{hw1} {hw2}, {state_name}",                   # Alt: "I-29 I-90, South Dakota"
            f"{hw1} at {hw2}, {state_name}",               # Alt: "I-29 at I-90, South Dakota"
            f"{hw1} intersection {hw2}, {state_name}",     # Alt: explicit intersection
        ]
        
        for query in queries:
            try:
                time.sleep(0.3)  # Rate limit
                
                print(f"[NOMINATIM] Trying: {query}")
                
                response = requests.get(
                    cls.NOMINATIM_URL,
                    params={
                        'q': query,
                        'format': 'json',
                        'limit': 5,
                        'countrycodes': 'us',
                        'addressdetails': 1
                    },
                    headers={'User-Agent': 'RightRoute/1.0'},
                    timeout=10
                )
                
                for result in response.json():
                    lat = float(result['lat'])
                    lon = float(result['lon'])
                    display = result.get('display_name', '')
                    
                    # ✅ Filter out false positives like "Junction Avenue"
                    if 'junction avenue' in display.lower():
                        print(f"[NOMINATIM] ⚠️ Skipping false positive: Junction Avenue")
                        continue
                    
                    # Bounds check
                    if bounds['s'] <= lat <= bounds['n'] and bounds['w'] <= lon <= bounds['e']:
                        print(f"[NOMINATIM] ✅ Found: {lat}, {lon}")
                        
                        return {
                            'found': True,
                            'latitude': lat,
                            'longitude': lon,
                            'display_name': f"{hw1} and {hw2}, {state_name}",
                            'source': 'nominatim',
                            'confidence': 'medium'
                        }
                        
            except Exception as e:
                print(f"[NOMINATIM] Error: {e}")
        
        return {'found': False}

    # ════════════════════════════════════════════════════════════════
    # Specific Interstate Junction Finder (for I-29/I-90 etc.)
    # ════════════════════════════════════════════════════════════════
    @classmethod
    def find_interstate_junction(cls, interstate1: str, interstate2: str, state: str = 'SD') -> dict:
        """
        Interstate-to-Interstate জংশন খুঁজুন (উদাহরণ: I-29/I-90)
        """
        bounds = cls.STATE_BOUNDS.get(state, cls.STATE_BOUNDS['SD'])
        
        ref1 = cls._extract_ref(interstate1)
        ref2 = cls._extract_ref(interstate2)
        
        # Overpass query specifically for interstate junctions
        query = f"""
        [out:json][timeout:30];
        (
          way["highway"="motorway"]["ref"~"I[ -]?{ref1}|Interstate {ref1}",i]
            ({bounds['s']},{bounds['w']},{bounds['n']},{bounds['e']});
        )->.i1;
        (
          way["highway"="motorway"]["ref"~"I[ -]?{ref2}|Interstate {ref2}",i]
            ({bounds['s']},{bounds['w']},{bounds['n']},{bounds['e']});
        )->.i2;
        node(w.i1)(w.i2);
        out body 1;
        """
        
        try:
            print(f"[OVERPASS] Finding interstate junction: I-{ref1} ∩ I-{ref2}")
            
            response = requests.post(
                cls.OVERPASS_URL,
                data={'data': query},
                timeout=30,
                headers={'User-Agent': 'RightRoute/1.0'}
            )
            
            if response.status_code == 200:
                data = response.json()
                elements = data.get('elements', [])
                
                if elements:
                    node = elements[0]
                    return {
                        'found': True,
                        'latitude': node['lat'],
                        'longitude': node['lon'],
                        'display_name': f"I-{ref1} and I-{ref2} Junction, {cls.STATE_NAMES.get(state, state)}",
                        'source': 'overpass_api',
                        'confidence': 'high'
                    }
                    
        except Exception as e:
            print(f"[OVERPASS] Interstate junction error: {e}")
        
        return {'found': False}

    # Alias for compatibility
    @classmethod
    def get_junction(cls, hw1: str, hw2: str, state: str = 'SD') -> dict:
        """Alias for find_junction"""
        return cls.find_junction(hw1, hw2, state)