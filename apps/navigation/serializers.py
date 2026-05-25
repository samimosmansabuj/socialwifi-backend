from rest_framework import serializers
from .models import Route, Waypoint, RouteHistory
from django.contrib.auth import get_user_model

User = get_user_model()

class WayPointSerializerNew(serializers.Serializer):
    address = serializers.CharField()

class CreatePermitRouteSerializer(serializers.Serializer):
    address = serializers.CharField(max_length=255)
    start_location_name = serializers.CharField(max_length=255, required=False)
    start_latitude = serializers.FloatField(required=False)
    start_longitude = serializers.FloatField(required=False)

    end_location_name = serializers.CharField(max_length=255, required=False)
    end_latitude = serializers.FloatField(required=False)
    end_longitude = serializers.FloatField(required=False)

    permit_document = serializers.FileField(required=False)

class WaypointSerializer(serializers.ModelSerializer):
    """ওয়েপয়েন্ট সিরিয়ালাইজার"""
    
    class Meta:
        model = Waypoint
        fields = [
            'id', 'name', 'latitude', 'longitude', 'order', 
            'description', 'distance_from_previous', 'estimated_time_minutes', 
            'icon', 'created_at'
        ]
        read_only_fields = ['id', 'created_at']


class RouteDetailSerializer(serializers.ModelSerializer):
    """রুটের বিস্তারিত সিরিয়ালাইজার (ওয়েপয়েন্ট সহ)"""
    
    waypoints = WaypointSerializer(many=True, read_only=True)
    user_email = serializers.CharField(source='user.email', read_only=True)
    
    class Meta:
        model = Route
        fields = [
            'id', 'user_email', 'name', 'description', 
            'start_latitude', 'start_longitude', 'start_location_name',
            'end_latitude', 'end_longitude', 'end_location_name',
            'total_distance', 'waypoint_count', 'source_file',
            'is_completed', 'is_favorite', 'waypoints',
            'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'user_email', 'created_at', 'updated_at', 'waypoint_count']


class RouteListSerializer(serializers.ModelSerializer):
    """রুটের লিস্ট সিরিয়ালাইজার (সংক্ষিপ্ত)"""
    
    user_email = serializers.CharField(source='user.email', read_only=True)
    
    class Meta:
        model = Route
        fields = [
            'id', 'user_email', 'name', 'start_location_name', 
            'end_location_name', 'total_distance', 'waypoint_count',
            'is_completed', 'is_favorite', 'created_at'
        ]
        read_only_fields = fields


class RouteCreateUpdateSerializer(serializers.ModelSerializer):
    """রুট তৈরি এবং আপডেটের সিরিয়ালাইজার"""
    
    waypoints = WaypointSerializer(many=True, required=False)
    
    class Meta:
        model = Route
        fields = [
            'id', 'name', 'description', 
            'start_latitude', 'start_longitude', 'start_location_name',
            'end_latitude', 'end_longitude', 'end_location_name',
            'total_distance', 'is_completed', 'is_favorite', 
            'waypoints', 'source_file'
        ]
    
    def create(self, validated_data):
        waypoints_data = validated_data.pop('waypoints', [])
        route = Route.objects.create(**validated_data)
        
        # ওয়েপয়েন্ট তৈরি করুন
        for waypoint_data in waypoints_data:
            Waypoint.objects.create(route=route, **waypoint_data)
        
        route.waypoint_count = route.waypoints.count()
        route.save()
        return route
    
    def update(self, instance, validated_data):
        waypoints_data = validated_data.pop('waypoints', None)
        
        # রুট আপডেট করুন
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        instance.save()
        
        # ওয়েপয়েন্ট আপডেট করুন
        if waypoints_data is not None:
            instance.waypoints.all().delete()
            for waypoint_data in waypoints_data:
                Waypoint.objects.create(route=instance, **waypoint_data)
            instance.waypoint_count = instance.waypoints.count()
            instance.save()
        
        return instance


class RouteHistorySerializer(serializers.ModelSerializer):
    """রুট হিস্ট্রি সিরিয়ালাইজার"""
    
    route_name = serializers.CharField(source='route.name', read_only=True)
    user_email = serializers.CharField(source='user.email', read_only=True)
    
    class Meta:
        model = RouteHistory
        fields = [
            'id', 'route_name', 'user_email', 'started_at', 
            'completed_at', 'total_time_spent', 'total_distance_traveled',
            'status', 'notes'
        ]
        read_only_fields = ['id', 'route_name', 'user_email', 'started_at']
