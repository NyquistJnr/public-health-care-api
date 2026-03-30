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
    ResetPasswordSerializer,
    UserInviteSerializer,
    StateAdminUserInviteSerializer,
    UserProfileSerializer
)
from .models import User
from django.http import JsonResponse
from rest_framework.permissions import IsAuthenticated

@extend_schema(
    tags=["Authentication"],
    summary="Login",
    description="Authentication API"
)
class CustomLoginView(TokenObtainPairView):
    serializer_class = EmailTokenObtainPairSerializer

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
    serializer_class = ForgotPasswordSerializer

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
    serializer_class = ResetPasswordSerializer

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

@extend_schema(tags=["User Management"], summary="Invite New User")
class UserInviteView(generics.CreateAPIView):
    queryset = User.objects.all()
    serializer_class = UserInviteSerializer
    # permission_classes = [HasRequiredPermission]

    def perform_create(self, serializer):
        inviter_facility = self.request.user.facility
        user = serializer.save(created_by=self.request.user, facility=inviter_facility)
        uidb64 = urlsafe_base64_encode(force_bytes(user.pk))
        token = PasswordResetTokenGenerator().make_token(user)
        
        subject = "Welcome to the Public Health Care System"
        message = f"Hello {user.first_name},\n\nAn administrator has created an account for you.\n\nTo set your password and activate your account, use the following details in your app:\n\nUID: {uidb64}\nToken: {token}\n\nRole: {user.role}"
        
        send_mail(
            subject,
            message,
            "noreply@health.gov.ng",
            [user.email],
            fail_silently=True,
        )

@extend_schema(tags=["User Management"], summary="State Admin Invite New User to Facility")
class StateAdminUserInviteView(generics.CreateAPIView):
    queryset = User.objects.all()
    serializer_class = StateAdminUserInviteSerializer
    # permission_classes = [HasRequiredPermission]
    
    def perform_create(self, serializer):
        user = serializer.save(created_by=self.request.user)
        uidb64 = urlsafe_base64_encode(force_bytes(user.pk))
        token = PasswordResetTokenGenerator().make_token(user)
        
        subject = "Welcome to the Public Health Care System"
        message = f"Hello {user.first_name},\n\nAn administrator has created an account for you.\n\nTo set your password and activate your account, use the following details in your app:\n\nUID: {uidb64}\nToken: {token}\n\nRole: {user.role}"
        
        send_mail(
            subject,
            message,
            "noreply@health.gov.ng",
            [user.email],
            fail_silently=True,
        )

@extend_schema(tags=["User Profile"], summary="Get or Update Logged-in User Profile")
class UserProfileView(generics.RetrieveUpdateAPIView):
    serializer_class = UserProfileSerializer
    permission_classes = [IsAuthenticated] 

    def get_object(self):
        """
        Instead of looking for an ID in the URL, this tells the view to 
        always return the exact user who owns the current JWT token.
        """
        return self.request.user

def global_404(request, exception=None):
    """Catches bad URLs and returns standard JSON instead of HTML."""
    return JsonResponse({
        "status": "error",
        "message": "The requested endpoint was not found.",
        "data": None,
        "errors": {"detail": "Not found."}
    }, status=404)

def global_500(request):
    """Catches critical server crashes and returns standard JSON instead of HTML."""
    return JsonResponse({
        "status": "error",
        "message": "An internal server error occurred.",
        "data": None,
        "errors": {"detail": "Server Error."}
    }, status=500)
