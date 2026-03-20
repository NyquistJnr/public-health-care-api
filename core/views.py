# core/views.py
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView
from rest_framework import generics
from rest_framework.permissions import AllowAny
from drf_spectacular.utils import extend_schema
from .serializers import EmailTokenObtainPairSerializer
from .models import User

@extend_schema(
    tags=["Authentication"],
    summary="Login",
    description="Authentication API"
)
class CustomLoginView(TokenObtainPairView):
    serializer_class = EmailTokenObtainPairSerializer


@extend_schema(
    tags=["Authentication"],
    summary="Sign Up",
    description="Creates an Account of any USER TYPE: DOCTOR, NURSE, PATIENT and ADMIN"
)
class UserSignUpView(generics.CreateAPIView):
    queryset = User.objects.all()
    permission_classes = [AllowAny]

@extend_schema(
    tags=["Authentication"],
    summary="Refresh Token",
    description="Generates a new access token using a valid refresh token"
)
class CustomTokenRefreshView(TokenRefreshView):
    pass
