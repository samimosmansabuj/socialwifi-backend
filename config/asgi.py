import os
import django
from django.core.asgi import get_asgi_application
from channels.routing import ProtocolTypeRouter, URLRouter
from django.urls import re_path

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from apps.navigation.consumers import DriverConsumer
from apps.navigation.auth import JWTAuthMiddleware

application = ProtocolTypeRouter({
    "http": get_asgi_application(),
    "websocket": JWTAuthMiddleware(
        URLRouter([
            re_path(r"^ws/driver/$", DriverConsumer.as_asgi()),
            re_path(r"^ws/location/$", DriverConsumer.as_asgi()),  # 'ws/location/' পাথটি এখানে যোগ করা হয়েছে
        ])
    ),
})
