from rest_framework import serializers
from django.db.models import Max
from .models import CreateRoute, AddPermit, Waypoint
# from .utils import extract_waypoints_from_document
from rest_framework.exceptions import ValidationError
import requests
import os
from django.db import transaction

class CreateRouteSerializer(serializers.ModelSerializer):
    class Meta:
        model = CreateRoute
        fields = ['id', 'name', 'description', 'status', 'is_completed', 'is_favorite']
        read_only_fields = ['status']

class WaypointSerializer(serializers.ModelSerializer):
    class Meta:
        model = Waypoint
        fields = '__all__'
        read_only_fields = ['id', 'permit', 'created_at']

class AddPermitSerializer(serializers.ModelSerializer):
    waypoints = WaypointSerializer(many=True, read_only=True)

    class Meta:
        model = AddPermit
        fields = [
            'id', 'route', 'order', 'name',
            'start_location_name', 'start_latitude', 'start_longitude', 'end_location_name', 'end_latitude', 'end_longitude',
            'permit_file', 'total_distance', 'waypoints'
        ]
        read_only_fields = ['id', 'route', 'order', 'total_distance', 'waypoints']
    
    def extract_route_data(self, permit_file):
        url = "http://10.10.20.43:8001/api/ocr/extract"

        permit_file.seek(0)
        payload = {
            "file": (
                permit_file.name,
                permit_file.read(),
                permit_file.content_type
            )
        }
        try:
            response = requests.post(
                url,
                files=payload,
                timeout=30
            )
            if response.status_code != 200:
                raise ValidationError(
                    "Documents Extract Failed!"
                )
            response_data = response.json()
            
            if not response_data.get('success') and not response_data.get('route_information'):
                raise ValidationError(
                    "Documents Extract Failed!"
                )
            return response_data.get('route_information')

        except requests.exceptions.Timeout:
            raise ValidationError(
                "OCR server timeout."
            )
        except requests.exceptions.ConnectionError:
            raise ValidationError(
                "Cannot connect to OCR server."
            )
        except Exception as e:
            raise ValidationError(str(e))
    
    def get_intersection_lat_lng(self, address_list: list):
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
                address_lat_lng = {
                    "name": address,
                    "lat": location['lat'],
                    "lng": location['lng']
                }
                address_list_lat_lng.append(address_lat_lng)
        return address_list_lat_lng
    
    def create(self, validated_data):
        route = validated_data.get('route')
        permit_file = validated_data.get('permit_file')
        if not permit_file:
            raise ValidationError("Permit Documents must be submited!")
        
        max_order_agg = AddPermit.objects.filter(route=route).aggregate(Max('order'))
        current_max = max_order_agg['order__max']
        validated_data['order'] = (current_max or 0) + 1
        
        with transaction.atomic():
            permit = super().create(validated_data)
            route_data = self.extract_route_data(permit_file)
            print("all intersection: ", route_data['intersection'][:-1])
            waypoints = self.get_intersection_lat_lng(route_data['intersection'][:-1])
            waypoint_objects = []
            for index, wp in enumerate(waypoints, start=1):
                last_wp = Waypoint.objects.filter(permit=permit).last()
                waypoint = Waypoint(
                    permit=permit,
                    order=index,
                    name=wp.get('name', f'Waypoint {index}'),
                    latitude=wp.get('lat'),
                    longitude=wp.get('lng')
                )
                waypoint_objects.append(waypoint)
            
            # Bulk create for database efficiency
            Waypoint.objects.bulk_create(waypoint_objects)
            return permit
    
    def update(self, instance, validated_data):
        permit_file = validated_data.get('permit_file', None)
        with transaction.atomic():
            instance = super().update(instance, validated_data)
            if permit_file:
                instance.waypoints.all().delete()
                route_data = self.extract_route_data(permit_file)
                if not route_data:
                    raise ValidationError("Failed to extract route data.")

                intersections = route_data.get('intersection', [])
                waypoints = self.get_intersection_lat_lng(intersections)
                if not waypoints:
                    raise ValidationError("No waypoint found.")

                waypoint_objects = []
                for index, wp in enumerate(waypoints, start=1):
                    waypoint = Waypoint(
                        permit=instance,
                        order=index,
                        name=wp.get('name', f'Waypoint {index}'),
                        latitude=wp.get('lat'),
                        longitude=wp.get('lng')
                    )
                    waypoint_objects.append(waypoint)
                Waypoint.objects.bulk_create(waypoint_objects)
            return instance


