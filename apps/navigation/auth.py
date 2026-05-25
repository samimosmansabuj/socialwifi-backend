import urllib.parse
from channels.db import database_sync_to_async
from channels.middleware import BaseMiddleware
from django.contrib.auth import get_user_model
from django.contrib.auth.models import AnonymousUser
from rest_framework_simplejwt.tokens import AccessToken
from rest_framework_simplejwt.exceptions import InvalidToken, TokenError

User = get_user_model()

class JWTAuthMiddleware(BaseMiddleware):
    """JWT Authentication Middleware for WebSocket."""
    
    async def __call__(self, scope, receive, send):
        query_string = scope.get("query_string", b"").decode()
        token = None
        
        print(f"\n[Auth] Query: {query_string}")
        
        if query_string:
            try:
                params = urllib.parse.parse_qs(query_string)
                token = params.get("token", [None])[0]
                print(f"[Auth] Token: {token[:30] if token else 'None'}...")
            except Exception as e:
                print(f"[Auth] Parse error: {e}")
        
        if token:
            user = await self.get_user_from_token(token)
            scope["user"] = user
        else:
            scope["user"] = AnonymousUser()
        
        return await super().__call__(scope, receive, send)
    
    @database_sync_to_async
    def get_user_from_token(self, token):
        """Decode JWT and return user."""
        try:
            access_token = AccessToken(token)
            user_id = access_token["user_id"]
            user = User.objects.get(id=user_id)
            print(f"[Auth] User: {user.email} (ID: {user_id})")
            return user
        except Exception as e:
            print(f"[Auth] Error: {e}")
            return AnonymousUser()