from urllib import response

import requests
from django.shortcuts import render
from rest_framework import viewsets, status, views
from rest_framework.generics import GenericAPIView
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework.filters import SearchFilter, OrderingFilter
from django_filters.rest_framework import DjangoFilterBackend
from .models import Route, Waypoint, RouteHistory
from .serializers import (
    CreatePermitRouteSerializer, RouteDetailSerializer, RouteListSerializer, 
    RouteCreateUpdateSerializer, RouteHistorySerializer, WayPointSerializerNew
)
from django.utils import timezone
from django.db.models import Q
from django.views import View
import json
import os

class RouteViewSet(viewsets.ModelViewSet):
    """রুট পরিচালনার জন্য ViewSet"""
    
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_fields = ['is_completed', 'is_favorite']
    search_fields = ['name', 'description', 'start_location_name', 'end_location_name']
    ordering_fields = ['created_at', 'name', 'total_distance']
    ordering = ['-created_at']
    
    def get_queryset(self):
        """লগইন করা ইউজারের রুট শুধুমাত্র দেখাবে"""
        return Route.objects.filter(user=self.request.user)
    
    def get_serializer_class(self):
        """অ্যাকশন অনুযায়ী ভিন্ন সিরিয়ালাইজার ব্যবহার করুন"""
        if self.action == 'retrieve':
            return RouteDetailSerializer
        elif self.action in ['create', 'update', 'partial_update']:
            return RouteCreateUpdateSerializer
        return RouteListSerializer
    
    def perform_create(self, serializer):
        """রুট তৈরি করার সময় ইউজার যোগ করুন"""
        serializer.save(user=self.request.user)
    
    @action(detail=False, methods=['post'])
    def from_ocr(self, request):
        """OCR থেকে পাওয়া ডেটা দিয়ে রুট তৈরি করুন"""
        
        try:
            ocr_data = request.data
            
            # OCR থেকে পাওয়া লোকেশন পয়েন্ট
            waypoints = ocr_data.get('waypoints', [])
            
            if not waypoints or len(waypoints) < 2:
                return Response(
                    {"error": "কমপক্ষে ২টি লোকেশন প্রয়োজন"},
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            # শুরু এবং শেষ পয়েন্ট
            first_point = waypoints[0]
            last_point = waypoints[-1]
            
            # রুট ডেটা প্রস্তুত করুন
            route_data = {
                'name': ocr_data.get('name', f'Route {timezone.now().strftime("%Y-%m-%d")}'),
                'description': ocr_data.get('description', ''),
                'start_latitude': first_point['latitude'],
                'start_longitude': first_point['longitude'],
                'start_location_name': first_point['name'],
                'end_latitude': last_point['latitude'],
                'end_longitude': last_point['longitude'],
                'end_location_name': last_point['name'],
                'total_distance': self.calculate_total_distance(waypoints),
                'waypoints': waypoints,
            }
            
            serializer = self.get_serializer(data=route_data)
            if serializer.is_valid():
                self.perform_create(serializer)
                return Response(
                    {
                        "message": "রুট সফলভাবে তৈরি হয়েছে",
                        "route": serializer.data
                    },
                    status=status.HTTP_201_CREATED
                )
            
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        
        except Exception as e:
            return Response(
                {"error": str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
    
    @action(detail=True, methods=['post'])
    def duplicate(self, request, pk=None):
        """রুট ডুপ্লিকেট করুন"""
        
        try:
            original_route = self.get_object()
            
            # নতুন রুট তৈরি করুন
            new_route = Route.objects.create(
                user=request.user,
                name=f"{original_route.name} (Copy)",
                description=original_route.description,
                start_latitude=original_route.start_latitude,
                start_longitude=original_route.start_longitude,
                start_location_name=original_route.start_location_name,
                end_latitude=original_route.end_latitude,
                end_longitude=original_route.end_longitude,
                end_location_name=original_route.end_location_name,
                total_distance=original_route.total_distance,
            )
            
            # ওয়েপয়েন্ট কপি করুন
            for waypoint in original_route.waypoints.all():
                Waypoint.objects.create(
                    route=new_route,
                    name=waypoint.name,
                    latitude=waypoint.latitude,
                    longitude=waypoint.longitude,
                    order=waypoint.order,
                    description=waypoint.description,
                    distance_from_previous=waypoint.distance_from_previous,
                    estimated_time_minutes=waypoint.estimated_time_minutes,
                    icon=waypoint.icon,
                )
            
            new_route.waypoint_count = new_route.waypoints.count()
            new_route.save()
            
            serializer = self.get_serializer(new_route)
            return Response(
                {
                    "message": "রুট সফলভাবে ডুপ্লিকেট হয়েছে",
                    "route": serializer.data
                },
                status=status.HTTP_201_CREATED
            )
        
        except Exception as e:
            return Response(
                {"error": str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
    
    @action(detail=True, methods=['post'])
    def toggle_favorite(self, request, pk=None):
        """রুটটিকে প্রিয় হিসেবে চিহ্নিত করুন বা সরান"""
        
        route = self.get_object()
        route.is_favorite = not route.is_favorite
        route.save()
        
        return Response(
            {
                "message": f"রুটটি {'প্রিয়' if route.is_favorite else 'আর প্রিয় নয়'}",
                "is_favorite": route.is_favorite
            },
            status=status.HTTP_200_OK
        )
    
    @action(detail=True, methods=['post'])
    def start_tracking(self, request, pk=None):
        """রুট ট্র্যাকিং শুরু করুন"""
        
        try:
            route = self.get_object()
            
            # হিস্ট্রি তৈরি করুন
            history = RouteHistory.objects.create(
                route=route,
                user=request.user,
                status='in_progress'
            )
            
            return Response(
                {
                    "message": "রুট ট্র্যাকিং শুরু হয়েছে",
                    "history_id": history.id,
                    "started_at": history.started_at.isoformat()
                },
                status=status.HTTP_201_CREATED
            )
        
        except Exception as e:
            return Response(
                {"error": str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
    
    @staticmethod
    def calculate_total_distance(waypoints):
        """ওয়েপয়েন্টগুলির মধ্যে মোট দূরত্ব গণনা করুন"""
        import math
        
        total = 0
        for i in range(len(waypoints) - 1):
            lat1 = math.radians(waypoints[i]['latitude'])
            lon1 = math.radians(waypoints[i]['longitude'])
            lat2 = math.radians(waypoints[i+1]['latitude'])
            lon2 = math.radians(waypoints[i+1]['longitude'])
            
            dlat = lat2 - lat1
            dlon = lon2 - lon1
            a = math.sin(dlat/2)**2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon/2)**2
            c = 2 * math.asin(math.sqrt(a))
            total += 6371 * c  # Earth radius in km
        
        return round(total, 2)

class RouteHistoryViewSet(viewsets.ReadOnlyModelViewSet):
    """রুট হিস্ট্রি দেখার জন্য ViewSet"""
    
    permission_classes = [IsAuthenticated]
    serializer_class = RouteHistorySerializer
    filter_backends = [OrderingFilter]
    ordering = ['-started_at']
    
    def get_queryset(self):
        """লগইন করা ইউজারের হিস্ট্রি শুধুমাত্র দেখাবে"""
        return RouteHistory.objects.filter(user=self.request.user)










class WaypointViewSet(GenericAPIView):
    permission_classes = [AllowAny]
    serializer_class = WayPointSerializerNew

    def geocode_address(self, address):
        url = "https://maps.googleapis.com/maps/api/geocode/json"
        params = {
            "address": address,
            "key": os.getenv("google_map_api_key")
        }
        response = requests.get(url, params=params)
        data = response.json()
        print(data)

        if data["status"] == "OK":
            location = data["results"][0]["geometry"]["location"]
            return {
                "lat": location["lat"],
                "lng": location["lng"],
                "formatted_address": data["results"][0]["formatted_address"]
            }
        
        return None

    def post(self, request):
        try:
            seralizer = WayPointSerializerNew(data=request.data)
            seralizer.is_valid(raise_exception=True)
            result = self.geocode_address(seralizer.validated_data['address'])
            return Response(
                {
                    "success": True,
                    "waypoints": result
                },
                status=status.HTTP_200_OK
            )
        except Exception as e:
            return Response(
                {"error": str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

class intersectionPoint(GenericAPIView):
    permission_classes = [AllowAny]
    serializer_class = WayPointSerializerNew

    def get_intersection(self, address):
        url = "https://maps.googleapis.com/maps/api/geocode/json"
        params = {
            "address": address, # KS-179 and KS-44 Anthony Kansas
            "key": os.getenv("google_map_api_key")
        }
        response = requests.get(url, params=params)
        data = response.json()
        if data["status"] == "OK":
            location = data["results"][0]["geometry"]["location"]
            return {
                "lat": location["lat"],
                "lng": location["lng"],
                "formatted_address": data["results"][0]["formatted_address"]
            }
        return None

    def post(self, request):
        try:
            seralizer = WayPointSerializerNew(data=request.data)
            seralizer.is_valid(raise_exception=True)
            intersection_points = self.get_intersection(seralizer.validated_data['address'])
            return Response(
                {
                    "success": True,
                    "intersection_points": intersection_points
                },
                status=status.HTTP_200_OK
            )
        except Exception as e:
            return Response(
                {"error": str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )



class MapPointView(View):
    permission_classes = [AllowAny]

    def get(self, request):
        return render(request, 'map-point.html')

class MaPpermitRouteView(View):
    permission_classes = [AllowAny]

    def get(self, request):
        return render(request, 'map-permit-route.html')

# Create your permit route views here
class CreatePermitRoute(GenericAPIView):
    permission_classes = [AllowAny]
    serializer_class = CreatePermitRouteSerializer

    def extract_route_data(self, data):
        # permit_file = data.get('permit_file')
        # url = "http://10.10.7.98:8001/api/ocr/extract/"
        # payload = {
        #     "file": permit_file
        # }
        # response = requests.post(url, json=payload)
        # if response.status_code != 200:
        #     return None
        # response_data = response.json()

        response_data = {
            "success": True,
            "route_information": {
                "start_location": "Rock Rapids, Lyon County, Iowa",
                "end_location": "Hancock, Iowa",
                "route_segments": [
                    "IA-9, Rock Rapids, Iowa",
                    "US-75, Sioux Center, Iowa",
                    "IA-9, Rock Rapids, Iowa",
                    "US-59, Sanborn, Iowa",
                    "US-18, Sanborn, Iowa",
                    "IA-4, Emmetsburg, Iowa",
                    "IA-3, Pocahontas, Iowa",
                    "US-69, Belmond, Iowa",
                    "B62, Hancock, Iowa"
                ],
                "intersection": [
                    "IA-9 and US-75, Sioux Center, Iowa",
                    "US-75 and IA-9, Rock Rapids, Iowa",
                    "IA-9 and US-59, Sanborn, Iowa",
                    "US-59 and US-18, Sanborn, Iowa",
                    "US-18 and IA-4, Emmetsburg, Iowa",
                    "IA-4 and IA-3, Pocahontas, Iowa",
                    "IA-3 and US-69, Belmond, Iowa",
                    "US-69 and B62, Hancock, Iowa"
                ],
                "permit_type": "Oversize / Overweight Single Trip"
            }
        }
        if not response_data.get('success') and not response_data.get('route_information'):
            return None
        return response_data.get('route_information')

    def demo_extract_route_data(self):
        return {
            "start_location": "Rock Rapids, Lyon County, Iowa",
            "end_location": "Hancock, Iowa",
            "route_segments": [
                "IA-9, Rock Rapids, Iowa",
                "US-75, Sioux Center, Iowa",
                "IA-9, Rock Rapids, Iowa",
                "US-59, Sanborn, Iowa",
                "US-18, Sanborn, Iowa",
                "IA-4, Emmetsburg, Iowa",
                "IA-3, Pocahontas, Iowa",
                "US-69, Belmond, Iowa",
                "B62, Hancock, Iowa"
            ],
            "intersection": [
                "IA-9 and US-75, Sioux Center, Iowa",
                "US-75 and IA-9, Rock Rapids, Iowa",
                "IA-9 and US-59, Sanborn, Iowa",
                "US-59 and US-18, Sanborn, Iowa",
                "US-18 and IA-4, Emmetsburg, Iowa",
                "IA-4 and IA-3, Pocahontas, Iowa",
                "IA-3 and US-69, Belmond, Iowa",
                "US-69 and B62, Hancock, Iowa"
            ],
            # "intersection": [
            #     "KS-179 and KS-44 near Anthony, Kansas",
            #     "KS-44 and KS-2 near Harper, Kansas",
            #     "KS-2 and US-160 near Medicine Lodge, Kansas",
            #     "US-160 and KS-2 near Harper, Kansas",
            #     "KS-2 and KS-42 near Norwich, Kansas",
            #     "KS-42 and I-235 near Wichita, Kansas",
            #     "I-235 and I-135 near Wichita, Kansas",
            #     "I-135 and US-50 near Newton, Kansas",
            #     "US-50 and I-35 near Emporia, Kansas",
            #     "I-35 and I-435 near Kansas City, Kansas"
            # ],
            
            "permit_type": "Oversize / Overweight Single Trip"
        }

    def get_intersection_lat_lng(self, address_list: list):
        print(f"Getting Lat/Lng for addresses {len(address_list)}:", address_list)
        address_list = [
            "IA-9 and US-75, Sioux Center, Iowa",
            "US-75 and IA-9, Rock Rapids, Iowa",
            "IA-9 and US-59, Sanborn, Iowa",
            "US-59 and US-18, Sanborn, Iowa",
            "US-18 and IA-4, Emmetsburg, Iowa",
            "IA-4 and IA-3, Pocahontas, Iowa",
            "IA-3 and US-69, Belmond, Iowa",
            "US-69 and B62, Hancock, Iowa"
        ]
        address_list_lat_lng = []
        for address in address_list:
            url = "https://maps.googleapis.com/maps/api/geocode/json"
            params = {
                "address": address,
                "key": os.getenv("google_map_api_key")
            }
            response = requests.get(url, params=params)
            data = response.json()
            if data["status"] == "OK":
                location = data["results"][0]["geometry"]["location"]
                address_list_lat_lng.append(f"{location['lat']},{location['lng']}")
        return address_list_lat_lng

    def post(self, request):
        try:
            data = request.data
            # serializer = CreatePermitRouteSerializer(data=data)
            # serializer.is_valid(raise_exception=True)
            # permit_document = serializer.validated_data['permit_document']

            # route_data = self.extract_route_data(serializer.validated_data)
            # route_data = self.demo_extract_route_data()
            # print("Extracted Route Data:", route_data)

            # waypoints = self.get_intersection_lat_lng(route_data['intersection'])
            waypoints = ['37.1521327,-98.0393131', '37.2393188,-98.03934989999999', '37.2831739,-98.01936839999999', '37.4591939,-97.7899252', '37.6336974,-97.4333948', '37.6769172,-97.4020811', '38.0315724,-97.3265117', '38.4107659,-96.13573989999999']
            print("Waypoints with Lat/Lng:", waypoints)


            return Response(
                {
                    "success": True,
                    "message": "Permit route created successfully",
                    "data": {
                        "start_location": '37.15220130000001,-98.0301635',
                        "end_location": '39.059472,-94.6280881',
                        "waypoints": waypoints,
                        "permit_type": data.get('permit_type', 'Unknown'),
                    },
                },
                status=status.HTTP_201_CREATED
            )
        except Exception as e:
            return Response(
                {"error": str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


from shapely.geometry import LineString
import time
# Intersaction Between Two Point View Using Overpass API
class IntersactionBetweenTwoPointView(View):
    permission_classes = [AllowAny]

    def find_intersection(self, road1_name, road2_name):
        road1 = self.get_road_geometry(road1_name)
        road2 = self.get_road_geometry(road2_name)

        for r1 in road1:
            line1 = LineString(r1)

            for r2 in road2:
                line2 = LineString(r2)

                inter = line1.intersection(line2)

                if not inter.is_empty:
                    return {
                        "lat": inter.y,
                        "lng": inter.x
                    }
        return None

    def get_road_geometry(self, road_name):
        url = "https://overpass-api.de/api/interpreter"

        # One----------
        query = f"""
        [out:json][timeout:60];
        area["name"="Iowa"]->.searchArea;
        way["highway"]["ref"~"{road_name}"](area.searchArea);
        out geom;
        """

        # Three----------
        # query = f"""
        # [out:json][timeout:60];
        # area["name"="Iowa"]->.searchArea;
        # (
        # way["highway"]["ref"~"{road_name}"](area.searchArea);
        # way["highway"]["name"~"{road_name}"](area.searchArea);
        # );
        # out geom;
        # """

        try:
            time.sleep(5)  # To avoid hitting API rate limits
            response = requests.get(url, params={'data': query}, timeout=60)
            time.sleep(5)  # To avoid hitting API rate limits
            response.raise_for_status()
            data = response.json()
        except requests.exceptions.Timeout:
            print("Timeout! Reduce query size.")
            return []
        except requests.exceptions.RequestException as e:
            print("Request failed:", e)
            return []

        # try:
        #     time.sleep(5)  # To avoid hitting API rate limits
        #     response = requests.get(url, params={'data': query}, timeout=60)
        #     time.sleep(5)  # To avoid hitting API rate limits
        #     if response.status_code != 200:
        #         print("Error:", response.text)
        #         return []
        #     data = response.json()
        # except Exception as e:
        #     print("Request Failed:", e)
        #     return []
        
        roads = []
        for element in data.get('elements', []):
            coords = [(pt['lon'], pt['lat']) for pt in element['geometry']]
            roads.append(coords)
        print("Road Geometry for", road_name, ":", roads)
        time.sleep(5)  # To avoid hitting API rate limits
        return roads


    # def get_two_roads(self, road1, road2):
    #     url = "https://overpass-api.de/api/interpreter"

    #     query = f"""
    #     [out:json][timeout:25];
    #     area["name"="Rock Rapids, Iowa"]->.searchArea;
    #     (
    #     way["highway"]["ref"="{road1}"](area.searchArea);
    #     way["highway"]["ref"="{road2}"](area.searchArea);
    #     );
    #     out geom;
    #     """

    #     try:
    #         response = requests.get(url, params={'data': query}, timeout=30)

    #         if response.status_code != 200:
    #             print("Error:", response.text)
    #             return [], []
    #         data = response.json()
    #     except Exception as e:
    #         print("Request Failed:", e)
    #         return [], []

    #     road1_list = []
    #     road2_list = []
    #     for el in data.get('elements', []):
    #         coords = [(pt['lon'], pt['lat']) for pt in el['geometry']]

    #         if el.get("tags", {}).get("ref") == road1:
    #             road1_list.append(coords)
    #         elif el.get("tags", {}).get("ref") == road2:
    #             road2_list.append(coords)
    #     return road1_list, road2_list
    
    # def find_intersection(self, road1, road2):
    #     r1_list, r2_list = self.get_two_roads(road1, road2)

    #     for r1 in r1_list:
    #         line1 = LineString(r1)

    #         for r2 in r2_list:
    #             line2 = LineString(r2)

    #             inter = line1.intersection(line2)

    #             if not inter.is_empty:
    #                 return {"lat": inter.y, "lng": inter.x}

    #     return None

    def get(self, request):
        # road = self.get_road_geometry("IA-9")
        road = self.find_intersection("IA-9", "US-75")
        print("Road Geometry:", road)
        return render(request, 'intersection-point.html', {"lat": None, "lng": None})

