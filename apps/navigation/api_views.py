from rest_framework import generics, viewsets, views
from django.shortcuts import get_object_or_404
from .models import CreateRoute, AddPermit, ROUTE_STATUS, Waypoint
from .api_serializers import CreateRouteSerializer, AddPermitSerializer, WaypointSerializer
from rest_framework.parsers import MultiPartParser, FormParser
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.decorators import action
from rest_framework import status

class RouteCreateAPIView(generics.CreateAPIView):
    serializer_class = CreateRouteSerializer
    permission_classes = [AllowAny]

class RouteListAPIView(generics.ListAPIView):
    queryset = CreateRoute.objects.filter(status=ROUTE_STATUS.DRAFT)
    serializer_class = CreateRouteSerializer
    permission_classes = [AllowAny]

class RouteRetrieveAPIView(generics.RetrieveAPIView):
    queryset = CreateRoute.objects.all()
    serializer_class = CreateRouteSerializer
    permission_classes = [AllowAny]

class PermitViewset(viewsets.ModelViewSet):
    queryset = AddPermit.objects.all()
    serializer_class = AddPermitSerializer
    permission_classes = [AllowAny]
    parser_classes = (MultiPartParser, FormParser)
    
    def get_route(self):
        route_pk = self.kwargs.get("route_pk", None)
        if route_pk is None:
            raise Exception("Route id not found.")
        route = get_object_or_404(CreateRoute, pk=route_pk)
        if not route:
            raise Exception("Route not found with this id.")
        return route
    
    def get_queryset(self):
        route = self.get_route()
        return AddPermit.objects.filter(route=route)
    
    def list(self, request, *args, **kwargs):
        route = self.get_route()
        permits = self.get_queryset()
        serializer = self.get_serializer(permits, many=True)
        return Response(
            {
                "success": True,
                "data": {
                    "route_name": route.name,
                    "route_description": route.description,
                    "route_status": route.status,
                    "route_is_completed": route.is_completed,
                    "is_permit": len(serializer.data) > 0,
                    "permit": serializer.data
                }
            }
        )
    
    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        serializer.save(route=self.get_route())
        return Response(
            {
                "success": True,
                "data": serializer.data
            }, status=status.HTTP_201_CREATED
        )
    
    def destroy(self, request, *args, **kwargs):
        try:
            super().destroy(request, *args, **kwargs)
            return Response(
                {
                    "success": True,
                    "message": "Deleted!"
                }, status=status.HTTP_200_OK
            )
        except Exception as e:
            return Response(
                {
                    "success": False,
                    "message": str(e)
                }, status=status.HTTP_400_BAD_REQUEST
            )

    @action(detail=False, methods=['post'], url_path='drive-start')
    def drive_start(self, request, *args, **kwargs):
        route = self.get_route()
        route.status = ROUTE_STATUS.START
        route.save(update_fields=["status"])
        return Response(
            {
                "success": True,
                "message": "Drive Stared!"
            }
        )
    
    @action(detail=False, methods=['post'], url_path='drive-stop')
    def drive_stop(self, request, *args, **kwargs):
        route = self.get_route()
        route.status = ROUTE_STATUS.STOP
        route.save(update_fields=["status"])
        return Response(
            {
                "success": True,
                "message": "Drive Stoped!"
            }
        )
    
    @action(detail=True, methods=['post'], url_path='add-waypoint')
    def add_waypoint(self, request, route_pk=None, pk=None):
        permit = self.get_object()
        last_waypoint = permit.waypoints.order_by('order').last()
        next_order = last_waypoint.order + 1 if last_waypoint else 1
        serializer = WaypointSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        serializer.save(
            permit=permit,
            order=next_order
        )
        return Response({
            "success": True,
            "message": "Waypoint added successfully.",
            "data": serializer.data
        }, status=status.HTTP_201_CREATED)
    
    @action(detail=True, methods=['GET', 'patch'], url_path='update-waypoint/(?P<waypoint_id>[^/.]+)')
    def update_waypoint(self, request, route_pk=None, pk=None, waypoint_id=None):
        permit = self.get_object()
        waypoint = get_object_or_404(Waypoint, pk=waypoint_id, permit=permit)
        
        if request.method == "GET":
            return Response(
                {
                    "success": True,
                    "data": WaypointSerializer(waypoint).data
                }
            )
        
        serializer = WaypointSerializer(waypoint, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response({
            "success": True,
            "message": "Waypoint updated successfully.",
            "data": serializer.data
        })

    @action(detail=True, methods=['delete'], url_path='remove-waypoint/(?P<waypoint_id>[^/.]+)')
    def remove_waypoint(self, request, route_pk=None, pk=None, waypoint_id=None):
        permit = self.get_object()
        waypoint = get_object_or_404(Waypoint, pk=waypoint_id, permit=permit)
        waypoint.delete()
        remaining_waypoints = permit.waypoints.order_by('order')
        for index, wp in enumerate(remaining_waypoints, start=1):
            wp.order = index
        Waypoint.objects.bulk_update(
            remaining_waypoints,
            ['order']
        )
        return Response({
            "success": True,
            "message": "Waypoint removed successfully."
        })
    

class GetPermitStartingPoint(views.APIView):
    def get_route(self):
        route_pk = self.kwargs.get("route_pk", None)
        if route_pk is None:
            raise Exception("Route id not found.")
        route = get_object_or_404(CreateRoute, pk=route_pk)
        if not route:
            raise Exception("Route not found with this id.")
        return route
    
    def get_last_permit(self):
        route = self.get_route()
        permit = route.permits.all().last()
        return permit
    
    def get(self, request, *args, **kwargs):
        try:
            last_permit = self.get_last_permit()
            if last_permit:
                response = {
                    "start_location_name": last_permit.end_location_name,
                    "start_latitude": last_permit.end_latitude,
                    "start_longitude": last_permit.end_longitude
                }
            else:
                response = None
            return Response(
                {
                    "status": True,
                    "data": response
                }, status=status.HTTP_200_OK
            )
        except Exception as e:
            return Response(
                {
                    "status": False,
                    "message": str(e)
                }, status=status.HTTP_400_BAD_REQUEST
            )
