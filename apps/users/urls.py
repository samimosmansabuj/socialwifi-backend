from django.urls import path
from .views import (
    CheckEmailView, RegisterView, LoginView,
    RequestOTPView, OTPLonView, ChangePasswordView, DeleteAccountView,
    ChangeEmailView, MeView, LogoutView, OCRProcessView, GeocodeRouteAPIView
)

app_name = 'users'

urlpatterns = [
    # Authentication endpoints
    path('check-email/', CheckEmailView.as_view(), name='check_email'),
    path('register/', RegisterView.as_view(), name='register'),
    path('login/', LoginView.as_view(), name='login'),
    path('request-otp/', RequestOTPView.as_view(), name='request_otp'),
    path('verify-otp/', OTPLonView.as_view(), name='verify_otp'),
    path('change-password/', ChangePasswordView.as_view(), name='change_password'),
    path('change-email/', ChangeEmailView.as_view(), name='change_email'),
    path('delete-account/', DeleteAccountView.as_view(), name='delete_account'),
    path('me/', MeView.as_view(), name='me'),
    path('logout/', LogoutView.as_view(), name='logout'),
    
    # OCR endpoint
    path('api/process-ocr/', OCRProcessView.as_view(), name='process_ocr'),

    # Geocode route endpoint (adds per-waypoint geocoding/validation)
    path('geocode-route/', GeocodeRouteAPIView.as_view(), name='geocode_route'),
]