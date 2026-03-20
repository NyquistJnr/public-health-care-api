# core/views.py
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView
from rest_framework import generics
from rest_framework.permissions import AllowAny
from django.contrib.auth.tokens import PasswordResetTokenGenerator
from django.utils.http import urlsafe_base64_encode, urlsafe_base64_decode
from drf_spectacular.utils import extend_schema
from django.utils.encoding import force_bytes, force_str
from django.core.mail import send_mail
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView
from .serializers import (
    EmailTokenObtainPairSerializer, 
    ForgotPasswordSerializer, 
    ResetPasswordSerializer
)
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

@extend_schema(
    tags=["Authentication"],
    summary="Forgot Password",
    description="Accepts an email and sends a secure reset token if the user exists.",
    request=ForgotPasswordSerializer
)
class ForgotPasswordView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        serializer = ForgotPasswordSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        
        email = serializer.validated_data['email']
        user = User.objects.filter(email=email).first()

        if user:
            uidb64 = urlsafe_base64_encode(force_bytes(user.pk))
            token = PasswordResetTokenGenerator().make_token(user)
            
            subject = "Password Reset Request"
            message = f"Hello {user.first_name},\n\nYour password reset details:\n\nUID: {uidb64}\nToken: {token}\n\nIf you did not request this, please ignore this email."
            
            send_mail(
                subject,
                message,
                "noreply@health.gov.ng",
                [user.email],
                fail_silently=True,
            )

        return Response({"detail": "If an account with that email exists, a reset token has been sent."}, status=status.HTTP_200_OK)


@extend_schema(
    tags=["Authentication"],
    summary="Reset Password",
    description="Accepts the UID, token, and new passwords to securely reset the account password.",
    request=ResetPasswordSerializer
)
class ResetPasswordView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        serializer = ResetPasswordSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        
        uidb64 = serializer.validated_data['uidb64']
        token = serializer.validated_data['token']
        new_password = serializer.validated_data['new_password']

        try:
            uid = force_str(urlsafe_base64_decode(uidb64))
            user = User.objects.get(pk=uid)
        except (TypeError, ValueError, OverflowError, User.DoesNotExist):
            user = None

        if user is not None and PasswordResetTokenGenerator().check_token(user, token):
            user.set_password(new_password)
            user.save()
            return Response({"detail": "Password successfully reset."}, status=status.HTTP_200_OK)
        else:
            return Response({"detail": "Invalid or expired reset token."}, status=status.HTTP_400_BAD_REQUEST)