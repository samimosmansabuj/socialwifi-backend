import json
from channels.generic.websocket import AsyncWebsocketConsumer
from channels.db import database_sync_to_async
from django.contrib.auth import get_user_model

User = get_user_model()

class DriverConsumer(AsyncWebsocketConsumer):
    """WebSocket Consumer for real-time driver location tracking."""
    
    async def connect(self):
        """Handle WebSocket connection."""
        self.user = self.scope["user"]
        self.room_group_name = None  # ডিফল্ট ভ্যালু সেট করা হলো
        
        print(f"[WS Connect] User: {self.user}, Is Anonymous: {self.user.is_anonymous}")
        
        # Check if user is authenticated
        if self.user.is_anonymous:
            print(f"[WS] Anonymous user rejected")
            await self.close(code=4001)
            return
        
        # Create a group name for this driver
        self.room_group_name = f'driver_{self.user.id}'
        
        # Add to group
        await self.channel_layer.group_add(
            self.room_group_name,
            self.channel_name
        )
        
        # Accept the WebSocket connection
        await self.accept()
        
        print(f"[WS] Connected - User {self.user.email} ({self.user.id})")
        
        # Send initialization message to client
        await self.send(text_data=json.dumps({
            "type": "connection_established",
            "message": "Connected. Please send your location with type='initialize_location'.",
            "user_id": self.user.id,
            "email": self.user.email
        }))

    async def disconnect(self, close_code):
        """Handle WebSocket disconnection."""
        print(f"[WS Disconnect] User: {self.user}, Code: {close_code}")
        
        # শুধুমাত্র room_group_name সেট থাকলে group থেকে সরানো হবে
        if self.room_group_name:
            await self.channel_layer.group_discard(
                self.room_group_name,
                self.channel_name
            )
            # Mark user as offline (optional)
            await self.update_user_offline()

    async def receive(self, text_data):
        """Receive message from WebSocket."""
        try:
            data = json.loads(text_data)
            print(f"[WS Receive] Data: {data}")
        except json.JSONDecodeError:
            await self.send(text_data=json.dumps({"error": "Invalid JSON"}))
            return
        
        message_type = data.get('type')
        
        # Initialize location on first connect
        if message_type == 'initialize_location':
            lat = data.get('lat')
            lng = data.get('lng')
            
            print(f"[WS] Init Location: lat={lat}, lng={lng}")
            
            if lat is None or lng is None:
                await self.send(text_data=json.dumps({
                    "status": "error",
                    "message": "lat and lng are required"
                }))
                return
            
            # Update location in database
            await self.update_user_location(lat, lng)
            
            # Send confirmation
            await self.send(text_data=json.dumps({
                "status": "success",
                "message": "Initial location updated",
                "lat": lat,
                "lng": lng
            }))
        
        # Live tracking updates
        elif message_type == 'live_tracking':
            lat = data.get('lat')
            lng = data.get('lng')
            
            print(f"[WS] Live Tracking: lat={lat}, lng={lng}")
            
            if lat is None or lng is None:
                await self.send(text_data=json.dumps({
                    "status": "error",
                    "message": "lat and lng are required"
                }))
                return
            
            # Update location
            await self.update_user_location(lat, lng)
            
            # Broadcast to all users in this driver's group
            await self.channel_layer.group_send(
                self.room_group_name,
                {
                    'type': 'location_update',
                    'lat': lat,
                    'lng': lng,
                    'user_id': self.user.id,
                    'email': self.user.email
                }
            )
        
        else:
            print(f"[WS] Unknown message type: {message_type}")
            await self.send(text_data=json.dumps({
                "error": f"Unknown message type: {message_type}"
            }))

    async def location_update(self, event):
        """Broadcast location update to group."""
        await self.send(text_data=json.dumps({
            "type": "location_update",
            "user_id": event['user_id'],
            "email": event['email'],
            "lat": event['lat'],
            "lng": event['lng']
        }))

    @database_sync_to_async
    def update_user_location(self, lat, lng):
        """Update user location in database."""
        try:
            user = User.objects.get(id=self.user.id)
            print(f"[DB] Found user: {user.email}")
            
            from .models import SavedRoute
            route, created = SavedRoute.objects.get_or_create(
                user=user,
                name="Current Location"
            )
            print(f"[DB] Route object: {route}, Created: {created}")
            
            # Update latitude and longitude
            route.latitude = lat
            route.longitude = lng
            route.save()
            
            print(f"[DB SUCCESS] User {user.email}: lat={lat}, lng={lng}")
            
        except Exception as e:
            print(f"[DB ERROR] {type(e).__name__}: {e}")
            import traceback
            traceback.print_exc()

    @database_sync_to_async
    def update_user_offline(self):
        """Mark user as offline (optional)."""
        try:
            user = User.objects.get(id=self.user.id)
            print(f"[Offline] User {user.email} disconnected")
        except User.DoesNotExist:
            print(f"[Offline] User not found: {self.user.id}")