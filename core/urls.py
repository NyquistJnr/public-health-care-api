# core/urls.py
from django.urls import path
from .views import (
    CustomLoginView, 
    UserInviteView, 
    CustomTokenRefreshView,
    ForgotPasswordView,
    ResetPasswordView
)
from .view_facility import FacilityUserListView, PatientCreateView,FacilityUserStatsView, UserStatusToggleView
from .view_audit_log import AuditLogListView

urlpatterns = [
    path('login/', CustomLoginView.as_view(), name='token_obtain_pair'),
    path('refresh/', CustomTokenRefreshView.as_view(), name='token_refresh'),
    path('forgot-password/', ForgotPasswordView.as_view(), name='forgot_password'),
    path('reset-password/', ResetPasswordView.as_view(), name='reset_password'),
    path('invite/', UserInviteView.as_view(), name='user_invite'),
    path('facility-users/', FacilityUserListView.as_view(), name='facility_user_list'),
    path('patients/register/', PatientCreateView.as_view(), name='patient_register'),
    path('facility-users/stats/', FacilityUserStatsView.as_view(), name='facility_user_stats'),
    path('users/<uuid:user_id>/toggle-status/', UserStatusToggleView.as_view(), name='user_toggle_status'),
    path('audit-logs/', AuditLogListView.as_view(), name='audit_logs'),
]
