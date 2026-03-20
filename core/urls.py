# core/urls.py
from django.urls import path
from .views import (
    CustomLoginView, 
    UserInviteView, 
    CustomTokenRefreshView,
    ForgotPasswordView,
    ResetPasswordView
)
from .view_facility import FacilityUserListView, PatientCreateView

urlpatterns = [
    path('login/', CustomLoginView.as_view(), name='token_obtain_pair'),
    path('refresh/', CustomTokenRefreshView.as_view(), name='token_refresh'),
    path('forgot-password/', ForgotPasswordView.as_view(), name='forgot_password'),
    path('reset-password/', ResetPasswordView.as_view(), name='reset_password'),
    path('invite/', UserInviteView.as_view(), name='user_invite'),
    path('facility-users/', FacilityUserListView.as_view(), name='facility_user_list'),
    path('patients/register/', PatientCreateView.as_view(), name='patient_register'),
]
