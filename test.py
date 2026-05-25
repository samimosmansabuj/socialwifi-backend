import asyncio
import json
import os
import django
import websockets
from datetime import datetime
from asgiref.sync import sync_to_async
import math
import random
import folium
from folium.plugins import MarkerCluster
import webbrowser
import osmnx as ox

# Django setup
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from django.contrib.auth import get_user_model
from rest_framework_simplejwt.tokens import RefreshToken, AccessToken
from apps.navigation.models import SavedRoute

User = get_user_model()

# Bangladesh real locations
BANGLADESH_ROUTES = [
    {"name": "Dhaka", "lat": 23.8103, "lng": 90.4125},
    {"name": "Mirpur", "lat": 23.8147, "lng": 90.3675},
    {"name": "Gulshan", "lat": 23.7872, "lng": 90.4142},
    {"name": "Dhanmondi", "lat": 23.7612, "lng": 90.3792},
    {"name": "Motijheel", "lat": 23.7633, "lng": 90.4101},
    {"name": "Badda", "lat": 23.8069, "lng": 90.4303},
]

# WebSocket URL
WS_URL = "ws://10.10.7.19:8000/ws/location/"
# অথবা
API_URL = "http://10.10.7.19:8000/subscriptions/team/members/"

# ============================================
# Get user from token (sync_to_async)
# ============================================
@sync_to_async
def get_user_from_token(token_str):
    """Extract user from JWT access token."""
    try:
        access_token_obj = AccessToken(token_str)
        user_id = access_token_obj["user_id"]
        user = User.objects.get(id=user_id)
        print(f"✅ User found: {user.email} (ID: {user.id})")
        return user
    except Exception as e:
        print(f"❌ Error extracting user: {e}")
        return None

# ============================================
# Check location before WebSocket (sync_to_async)
# ============================================
@sync_to_async
def check_location_before(user):
    """Check user location before WebSocket update."""
    try:
        route = SavedRoute.objects.filter(user=user, name="Current Location").first()
        if route:
            print(f"\n📍 Location BEFORE WebSocket:")
            print(f"   Latitude: {route.latitude}")
            print(f"   Longitude: {route.longitude}")
        else:
            print(f"\n⚠️  No saved route found for user {user.email}")
    except Exception as e:
        print(f"❌ Error checking location: {e}")

# ============================================
# Calculate direction and speed
# ============================================
def get_direction(lat_diff, lng_diff):
    """Calculate direction from lat/lng differences."""
    if abs(lng_diff) < 0.0001 and abs(lat_diff) < 0.0001:
        return "🔴 Stationary"
    
    angle = math.atan2(lng_diff, lat_diff) * 180 / math.pi
    
    if angle >= -22.5 and angle < 22.5:
        return "⬆️  North"
    elif angle >= 22.5 and angle < 67.5:
        return "↗️  North-East"
    elif angle >= 67.5 and angle < 112.5:
        return "➡️  East"
    elif angle >= 112.5 and angle < 157.5:
        return "↘️  South-East"
    elif angle >= 157.5 or angle < -157.5:
        return "⬇️  South"
    elif angle >= -157.5 and angle < -112.5:
        return "↙️  South-West"
    elif angle >= -112.5 and angle < -67.5:
        return "⬅️  West"
    else:
        return "↖️  North-West"

def calculate_speed(lat1, lng1, lat2, lng2, time_seconds):
    """Calculate speed in km/h between two points."""
    # Haversine formula
    R = 6371  # Earth radius in km
    
    lat1_rad = math.radians(lat1)
    lat2_rad = math.radians(lat2)
    delta_lat = math.radians(lat2 - lat1)
    delta_lng = math.radians(lng2 - lng1)
    
    a = math.sin(delta_lat/2)**2 + math.cos(lat1_rad) * math.cos(lat2_rad) * math.sin(delta_lng/2)**2
    c = 2 * math.asin(math.sqrt(a))
    distance = R * c  # in km
    
    time_hours = time_seconds / 3600
    speed = distance / time_hours if time_hours > 0 else 0
    
    return distance, speed

# ============================================
# Connect to WebSocket and send location
# ============================================
async def websocket_location_test(access_token, user, start_location, end_location, route_name):
    """Connect to WebSocket and send animated location updates."""
    
    ws_url = f"ws://10.10.20.111:8888/ws/driver/?token={access_token}"
    
    try:
        async with websockets.connect(ws_url) as websocket:
            
            # Receive connection message
            msg = await asyncio.wait_for(websocket.recv(), timeout=5)
            conn_data = json.loads(msg)
            
            # Send initial location
            initial_location = {
                "type": "initialize_location",
                "lat": start_location["lat"],
                "lng": start_location["lng"]
            }
            await websocket.send(json.dumps(initial_location))
            
            await asyncio.wait_for(websocket.recv(), timeout=5)
            
            print(f"\n🚗 Route: {route_name}")
            print(f"   From: {start_location['name']} ({start_location['lat']:.4f}, {start_location['lng']:.4f})")
            print(f"   To: {end_location['name']} ({end_location['lat']:.4f}, {end_location['lng']:.4f})")
            print(f"\n📍 Live Tracking:\n")
            
            # Randomized path between two locations
            steps = 5
            time_per_step = 5  # Update every 5 seconds
            
            prev_lat = start_location["lat"]
            prev_lng = start_location["lng"]
            total_distance = 0
            
            for i in range(steps):
                await asyncio.sleep(time_per_step)
                
                # Randomize lat/lng increments
                lat_increment = random.uniform(0.0001, 0.001) * random.choice([-1, 1])
                lng_increment = random.uniform(0.0001, 0.001) * random.choice([-1, 1])
                
                current_lat = prev_lat + lat_increment
                current_lng = prev_lng + lng_increment
                
                live_location = {
                    "type": "live_tracking",
                    "lat": current_lat,
                    "lng": current_lng
                }
                
                # Calculate speed and direction
                distance, speed = calculate_speed(prev_lat, prev_lng, current_lat, current_lng, time_per_step)
                total_distance += distance
                direction = get_direction(lat_increment, lng_increment)
                
                # Replace ball with car (🚗)
                bar_length = 50
                filled = int(bar_length * ((i + 1) / steps))
                bar = "🚗" * filled + "○" * (bar_length - filled)
                
                print(f"   {bar}")
                print(f"   📍 Lat: {current_lat:.6f} | Lng: {current_lng:.6f}")
                print(f"   🚀 Speed: {speed:.2f} km/h | {direction}")
                print()
                
                await websocket.send(json.dumps(live_location))
                
                prev_lat = current_lat
                prev_lng = current_lng
                
                try:
                    await asyncio.wait_for(websocket.recv(), timeout=5)
                except asyncio.TimeoutError:
                    pass
            
            # Calculate average speed
            total_time = steps * time_per_step / 3600  # Convert to hours
            avg_speed = total_distance / total_time if total_time > 0 else 0
            
            print(f"   ✅ {route_name} - Journey completed!")
            print(f"   📊 Total Distance: {total_distance:.3f} km")
            print(f"   ⏱️  Average Speed: {avg_speed:.2f} km/h\n")
            
    except Exception as e:
        print(f"❌ Error: {e}")

async def websocket_location_test_with_map(access_token, user, start_location, end_location, route_name):
    """Connect to WebSocket and send animated location updates with map visualization."""
    
    ws_url = f"ws://10.10.20.111:8888/ws/driver/?token={access_token}"
    
    # Create a folium map
    map_center = [(start_location["lat"] + end_location["lat"]) / 2, (start_location["lng"] + end_location["lng"]) / 2]
    folium_map = folium.Map(location=map_center, zoom_start=13)
    
    # Add start and end markers
    folium.Marker(
        location=[start_location["lat"], start_location["lng"]],
        popup=f"Start: {start_location['name']}",
        icon=folium.Icon(color="green", icon="play"),
    ).add_to(folium_map)
    
    folium.Marker(
        location=[end_location["lat"], end_location["lng"]],
        popup=f"End: {end_location['name']}",
        icon=folium.Icon(color="red", icon="stop"),
    ).add_to(folium_map)
    
    # Add a marker cluster for live tracking
    marker_cluster = MarkerCluster().add_to(folium_map)
    
    try:
        async with websockets.connect(ws_url) as websocket:
            
            # Receive connection message
            msg = await asyncio.wait_for(websocket.recv(), timeout=5)
            conn_data = json.loads(msg)
            
            # Send initial location
            initial_location = {
                "type": "initialize_location",
                "lat": start_location["lat"],
                "lng": start_location["lng"]
            }
            await websocket.send(json.dumps(initial_location))
            
            await asyncio.wait_for(websocket.recv(), timeout=5)
            
            print(f"\n🚗 Route: {route_name}")
            print(f"   From: {start_location['name']} ({start_location['lat']:.4f}, {start_location['lng']:.4f})")
            print(f"   To: {end_location['name']} ({end_location['lat']:.4f}, {end_location['lng']:.4f})")
            print(f"\n📍 Live Tracking:\n")
            
            # Randomized path between two locations
            steps = 20
            time_per_step = 5  # Update every 5 seconds
            
            prev_lat = start_location["lat"]
            prev_lng = start_location["lng"]
            total_distance = 0
            
            for i in range(steps):
                await asyncio.sleep(time_per_step)
                
                # Randomize lat/lng increments
                lat_increment = random.uniform(0.0001, 0.001) * random.choice([-1, 1])
                lng_increment = random.uniform(0.0001, 0.001) * random.choice([-1, 1])
                
                current_lat = prev_lat + lat_increment
                current_lng = prev_lng + lng_increment
                
                live_location = {
                    "type": "live_tracking",
                    "lat": current_lat,
                    "lng": current_lng
                }
                
                # Calculate speed and direction
                distance, speed = calculate_speed(prev_lat, prev_lng, current_lat, current_lng, time_per_step)
                total_distance += distance
                direction = get_direction(lat_increment, lng_increment)
                
                # Add live marker to map
                folium.Marker(
                    location=[current_lat, current_lng],
                    popup=f"Lat: {current_lat:.6f}, Lng: {current_lng:.6f}\nSpeed: {speed:.2f} km/h\nDirection: {direction}",
                    icon=folium.Icon(color="blue", icon="car"),
                ).add_to(marker_cluster)
                
                print(f"   📍 Lat: {current_lat:.6f} | Lng: {current_lng:.6f}")
                print(f"   🚀 Speed: {speed:.2f} km/h | {direction}")
                print()
                
                await websocket.send(json.dumps(live_location))
                
                prev_lat = current_lat
                prev_lng = current_lng
                
                try:
                    await asyncio.wait_for(websocket.recv(), timeout=5)
                except asyncio.TimeoutError:
                    pass
            
            # Save the map to an HTML file
            map_file = "live_tracking_map.html"
            folium_map.save(map_file)
            print(f"   ✅ Map saved to {map_file}")
            
            # Open the map in the default web browser
            webbrowser.open(map_file)
            
            print(f"   ✅ {route_name} - Journey completed!")
            print(f"   📊 Total Distance: {total_distance:.3f} km")
            
    except Exception as e:
        print(f"❌ Error: {e}")

async def websocket_location_test_with_live_map(access_token, user, start_location, end_location, route_name):
    """Connect to WebSocket and send animated location updates with live map visualization."""
    
    ws_url = f"ws://10.10.20.111:8888/ws/driver/?token={access_token}"
    
    # Create a folium map
    map_center = [(start_location["lat"] + end_location["lat"]) / 2, (start_location["lng"] + end_location["lng"]) / 2]
    folium_map = folium.Map(location=map_center, zoom_start=13)
    
    # Add start and end markers
    folium.Marker(
        location=[start_location["lat"], start_location["lng"]],
        popup=f"Start: {start_location['name']}",
        icon=folium.Icon(color="green", icon="play"),
    ).add_to(folium_map)
    
    folium.Marker(
        location=[end_location["lat"], end_location["lng"]],
        popup=f"End: {end_location['name']}",
        icon=folium.Icon(color="red", icon="stop"),
    ).add_to(folium_map)
    
    # Add a marker for the car (live tracking)
    car_marker = folium.Marker(
        location=[start_location["lat"], start_location["lng"]],
        popup="🚗 Car",
        icon=folium.Icon(color="blue", icon="car"),
    )
    car_marker.add_to(folium_map)
    
    # Save the initial map
    map_file = "live_tracking_map.html"
    folium_map.save(map_file)
    webbrowser.open(map_file)
    
    try:
        async with websockets.connect(ws_url) as websocket:
            
            # Receive connection message
            msg = await asyncio.wait_for(websocket.recv(), timeout=5)
            conn_data = json.loads(msg)
            
            # Send initial location
            initial_location = {
                "type": "initialize_location",
                "lat": start_location["lat"],
                "lng": start_location["lng"]
            }
            await websocket.send(json.dumps(initial_location))
            
            await asyncio.wait_for(websocket.recv(), timeout=5)
            
            print(f"\n🚗 Route: {route_name}")
            print(f"   From: {start_location['name']} ({start_location['lat']:.4f}, {start_location['lng']:.4f})")
            print(f"   To: {end_location['name']} ({end_location['lat']:.4f}, {end_location['lng']:.4f})")
            print(f"\n📍 Live Tracking:\n")
            
            # Randomized path between two locations
            steps = 20
            time_per_step = 5  # Update every 5 seconds
            
            prev_lat = start_location["lat"]
            prev_lng = start_location["lng"]
            total_distance = 0
            
            for i in range(steps):
                await asyncio.sleep(time_per_step)
                
                # Randomize lat/lng increments
                lat_increment = random.uniform(0.0001, 0.001) * random.choice([-1, 1])
                lng_increment = random.uniform(0.0001, 0.001) * random.choice([-1, 1])
                
                current_lat = prev_lat + lat_increment
                current_lng = prev_lng + lng_increment
                
                live_location = {
                    "type": "live_tracking",
                    "lat": current_lat,
                    "lng": current_lng
                }
                
                # Update car marker on the map
                car_marker.location = [current_lat, current_lng]
                car_marker.popup = f"🚗 Car\nLat: {current_lat:.6f}, Lng: {current_lng:.6f}"
                
                # Save updated map
                folium_map.save(map_file)
                
                print(f"   📍 Lat: {current_lat:.6f} | Lng: {current_lng:.6f}")
                
                await websocket.send(json.dumps(live_location))
                
                prev_lat = current_lat
                prev_lng = current_lng
                
                try:
                    await asyncio.wait_for(websocket.recv(), timeout=5)
                except asyncio.TimeoutError:
                    pass
            
            print(f"   ✅ {route_name} - Journey completed!")
            
    except Exception as e:
        print(f"❌ Error: {e}")

async def websocket_location_test_with_route(access_token, user, start_location, end_location, route_name):
    """Connect to WebSocket and send animated location updates along the selected route."""
    
    ws_url = f"ws://10.10.20.111:8888/ws/driver/?token={access_token}"
    
    try:
        async with websockets.connect(ws_url) as websocket:
            
            # Receive connection message
            await asyncio.wait_for(websocket.recv(), timeout=5)
            
            # Send initial location
            initial_location = {
                "type": "initialize_location",
                "lat": start_location["lat"],
                "lng": start_location["lng"]
            }
            await websocket.send(json.dumps(initial_location))
            
            await asyncio.wait_for(websocket.recv(), timeout=5)
            
            print(f"\n🚗 Route: {route_name}")
            print(f"   From: {start_location['name']} ({start_location['lat']:.4f}, {start_location['lng']:.4f})")
            print(f"   To: {end_location['name']} ({end_location['lat']:.4f}, {end_location['lng']:.4f})")
            print(f"\n📍 Live Tracking:\n")
            
            # Generate points along the selected route
            steps = 20
            lat_diff = (end_location["lat"] - start_location["lat"]) / steps
            lng_diff = (end_location["lng"] - start_location["lng"]) / steps
            
            current_lat = start_location["lat"]
            current_lng = start_location["lng"]
            total_distance = 0
            time_per_step = 5  # Update every 5 seconds
            
            for i in range(steps):
                await asyncio.sleep(time_per_step)
                
                current_lat += lat_diff
                current_lng += lng_diff
                
                # Calculate speed and direction
                distance, speed = calculate_speed(
                    current_lat - lat_diff, current_lng - lng_diff, current_lat, current_lng, time_per_step
                )
                total_distance += distance
                direction = get_direction(lat_diff, lng_diff)
                
                # Display clean output
                print(f"   📍 Location: ({current_lat:.6f}, {current_lng:.6f})")
                print(f"   🚀 Speed: {speed:.2f} km/h | 🧭 Direction: {direction}")
                print("-" * 50)
                
                await websocket.send(json.dumps({
                    "type": "live_tracking",
                    "lat": current_lat,
                    "lng": current_lng
                }))
                
                try:
                    await asyncio.wait_for(websocket.recv(), timeout=5)
                except asyncio.TimeoutError:
                    pass
            
            print(f"   ✅ {route_name} - Journey completed!")
            print(f"   📊 Total Distance: {total_distance:.3f} km")
            
    except Exception as e:
        print(f"❌ Error: {e}")

async def get_real_route_path(start_location, end_location):
    """Get real road path between start and end locations using OSMnx."""
    # Define start and end points
    start_point = (start_location["lat"], start_location["lng"])
    end_point = (end_location["lat"], end_location["lng"])
    
    # Get the graph for the area
    graph = ox.graph_from_point(start_point, dist=2000, network_type="drive")
    
    # Find the nearest nodes to the start and end points
    start_node = ox.distance.nearest_nodes(graph, start_point[1], start_point[0])
    end_node = ox.distance.nearest_nodes(graph, end_point[1], end_point[0])
    
    # Get the shortest path between the nodes
    route = ox.shortest_path(graph, start_node, end_node, weight="length")
    
    # Extract latitude and longitude for the route
    route_coords = [(graph.nodes[node]["y"], graph.nodes[node]["x"]) for node in route]
    return route_coords, graph

async def websocket_location_test_with_real_route(access_token, user, start_location, end_location, route_name):
    """Connect to WebSocket and send animated location updates along the real route."""
    
    # Get the real route path
    route_coords, graph = await get_real_route_path(start_location, end_location)
    
    # Create a folium map
    map_center = [(start_location["lat"] + end_location["lat"]) / 2, (start_location["lng"] + end_location["lng"]) / 2]
    folium_map = folium.Map(location=map_center, zoom_start=13)
    
    # Add start and end markers
    folium.Marker(
        location=[start_location["lat"], start_location["lng"]],
        popup=f"Start: {start_location['name']}",
        icon=folium.Icon(color="green", icon="play"),
    ).add_to(folium_map)
    
    folium.Marker(
        location=[end_location["lat"], end_location["lng"]],
        popup=f"End: {end_location['name']}",
        icon=folium.Icon(color="red", icon="stop"),
    ).add_to(folium_map)
    
    # Add the real route path as a polyline
    folium.PolyLine(
        locations=route_coords,
        color="blue",
        weight=5,
        opacity=0.8,
    ).add_to(folium_map)
    
    # Add a marker for the car (live tracking)
    car_marker = folium.Marker(
        location=route_coords[0],
        popup="🚗 Car",
        icon=folium.Icon(color="blue", icon="car"),
    )
    car_marker.add_to(folium_map)
    
    # Save the initial map
    map_file = "real_route_map.html"
    folium_map.save(map_file)
    webbrowser.open(map_file)
    
    # Simulate car movement along the route
    for coord in route_coords:
        await asyncio.sleep(5)  # Update every 5 seconds
        car_marker.location = coord
        folium_map.save(map_file)
        print(f"   📍 Lat: {coord[0]:.6f} | Lng: {coord[1]:.6f}")

# ============================================
# Connect to WebSocket and send location along custom route
# ============================================
async def websocket_location_test_with_custom_route(access_token, user, route_coords, route_name):
    """Connect to WebSocket and send animated location updates along the custom route."""
    
    # Create a folium map
    map_center = route_coords[0]
    folium_map = folium.Map(location=map_center, zoom_start=13)
    
    # Add start and end markers
    folium.Marker(
        location=route_coords[0],
        popup="Start",
        icon=folium.Icon(color="green", icon="play"),
    ).add_to(folium_map)
    
    folium.Marker(
        location=route_coords[-1],
        popup="End",
        icon=folium.Icon(color="red", icon="stop"),
    ).add_to(folium_map)
    
    # Add the custom route path as a polyline
    folium.PolyLine(
        locations=route_coords,
        color="blue",
        weight=5,
        opacity=0.8,
    ).add_to(folium_map)
    
    # Add a marker for the car (live tracking)
    car_marker = folium.Marker(
        location=route_coords[0],
        popup="🚗 Car",
        icon=folium.Icon(color="blue", icon="car"),
    )
    car_marker.add_to(folium_map)
    
    # Save the initial map
    map_file = "custom_route_map.html"
    folium_map.save(map_file)
    webbrowser.open(map_file)
    
    # Simulate car movement along the route
    for coord in route_coords:
        await asyncio.sleep(5)  # Update every 5 seconds
        car_marker.location = coord
        folium_map.save(map_file)
        print(f"   📍 Lat: {coord[0]:.6f} | Lng: {coord[1]:.6f}")

# ============================================
# Main function
# ============================================
async def main():
    ACCESS_TOKEN = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJ0b2tlbl90eXBlIjoiYWNjZXNzIiwiZXhwIjoxNzkzODMwOTQxLCJpYXQiOjE3Njc5MTA5NDEsImp0aSI6IjQ1OGM4ZjJhOWQ0NjQyMWVhNDNkNTE3OWM0NjE1NTVlIiwidXNlcl9pZCI6IjEifQ.EvSooUMdzB-f4E6S-0l-R1KT97DHHGZDscpu1ZdXlhM"
    
    print("=" * 70)
    print("🚀 WebSocket Live Location Tracking - Bangladesh Routes")
    print("=" * 70)
    
    # Get user
    print("\n1️⃣  Authenticating user...")
    user = await get_user_from_token(ACCESS_TOKEN)
    
    if not user:
        print("❌ Cannot proceed")
        return
    
    try:
        # Single route tracking
        current_route = BANGLADESH_ROUTES[0]  # Dhaka
        next_route = BANGLADESH_ROUTES[1]     # Mirpur
        
        print(f"\n2️⃣  Sending live location updates...")
        print(f"🔌 Connected to WebSocket")
        
        # Send location updates with route visualization
        await websocket_location_test_with_route(
            ACCESS_TOKEN, 
            user, 
            current_route, 
            next_route,
            f"{current_route['name']} → {next_route['name']}"
        )
        
        print(f"\n{'='*70}")
        print("✅ Test completed successfully!")
        print(f"{'='*70}")
        
    except KeyboardInterrupt:
        print(f"\n\n{'='*70}")
        print("⛔ Tracking stopped by user (Ctrl+C)")
        print(f"{'='*70}")

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n⛔ Test terminated")