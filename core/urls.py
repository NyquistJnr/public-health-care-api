# core/urls.py
from django.urls import path
from .views import (
    CustomLoginView, 
    UserSignUpView, 
    CustomTokenRefreshView,
    ForgotPasswordView,
    ResetPasswordView
)

urlpatterns = [
    path('login/', CustomLoginView.as_view(), name='token_obtain_pair'),
    path('signup/', UserSignUpView.as_view(), name='user_signup'),
    path('refresh/', CustomTokenRefreshView.as_view(), name='token_refresh'),
    path('forgot-password/', ForgotPasswordView.as_view(), name='forgot_password'),
    path('reset-password/', ResetPasswordView.as_view(), name='reset_password'),
]
