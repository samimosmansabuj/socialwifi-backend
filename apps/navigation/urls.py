from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import CreatePermitRoute, IntersactionBetweenTwoPointView, MaPpermitRouteView, RouteViewSet, RouteHistoryViewSet, WaypointViewSet, intersectionPoint, MapPointView

from .api_views import RouteCreateAPIView, RouteListAPIView, RouteRetrieveAPIView, PermitViewset, GetPermitStartingPoint

# DefaultRouter
router = DefaultRouter()
router.register(r'routes', RouteViewSet, basename='route')
router.register(r'route-history', RouteHistoryViewSet, basename='route-history')

app_name = 'navigation'


permit_route = DefaultRouter()
permit_route.register(r'permit', PermitViewset, basename='route-permit')


urlpatterns = [
    path('', include(router.urls)),

    path('waypoint/', WaypointViewSet.as_view(), name='waypoint'),
    path('waypoint/intersection/', intersectionPoint.as_view(), name='intersection-point'), # Only For API
    
    path('map/point/', MapPointView.as_view(), name='map-point'),
    path('map/point/intersection/', IntersactionBetweenTwoPointView.as_view(), name='map-point'),
    path('map/permit-route/', MaPpermitRouteView.as_view(), name='map-permit-route'),

    path('create-permit-route/', CreatePermitRoute.as_view(), name='create-permit-route'),
    
    path('create-route/', RouteCreateAPIView.as_view(), name='route-create'),
    path('route-list/', RouteListAPIView.as_view(), name='routes'),
    path('route-detail/<int:pk>/', RouteRetrieveAPIView.as_view(), name='route-detail'),
    path('route/<int:route_pk>/', include(permit_route.urls)),
    path('starting-point/route/<int:route_pk>/', GetPermitStartingPoint.as_view(), name="get-starting-point")
    # path('add-permit/', PermitCreateView.as_view(), name='add-permit'),
]
