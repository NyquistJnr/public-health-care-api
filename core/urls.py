# core/urls.py
from django.urls import path
from .views import (
    CustomLoginView, UserInviteView, StateAdminUserInviteView,
    CustomTokenRefreshView, ForgotPasswordView, ResetPasswordView,
    UserProfileView   
)
from .view_facility import (
    FacilityUserListView, PatientCreateView, FacilityUserStatsView, PatientChildrenListView,
    UserStatusToggleView, SpecificFacilityUserListView, PatientListView, PatientDetailView,
    PatientRecentAppointmentListView
)

from .view_audit_log import (
    AuditLogListView, NotificationListView, NotificationMarkReadView
)
from .view_stats import (
    DashboardStatsView, UserActivityTrendView, ModuleUsageStatsView,
    TopActiveFacilitiesView, FacilityUsageTableView,
    FailedLoginsByUserView, FailedLoginsByFacilityView, FailedLoginsUnknownEmailsView
)
from .view_alerts import ActiveAlertsView

from .view_qstash_webhook import QStashWebhookView

from .view_clinical_stats import (
    ClinicalStatsView, PatientVisitTrendView, ClinicalActivityView, DiseaseOverviewView
)

auth_patterns = [
    path('login/', CustomLoginView.as_view(), name='token_obtain_pair'),
    path('refresh/', CustomTokenRefreshView.as_view(), name='token_refresh'),
    path('forgot-password/', ForgotPasswordView.as_view(), name='forgot_password'),
    path('reset-password/', ResetPasswordView.as_view(), name='reset_password'),
    path('profile/', UserProfileView.as_view(), name='user_profile'),
]

user_management_patterns = [
    path('invite/', UserInviteView.as_view(), name='user_invite'),
    path('state-admin/invite/', StateAdminUserInviteView.as_view(), name='state_admin_user_invite'),
    path('facility-users/', FacilityUserListView.as_view(), name='facility_user_list'),
    path('facility-users/stats/', FacilityUserStatsView.as_view(), name='facility_user_stats'),
    path('facilities/<uuid:facility_id>/users/', SpecificFacilityUserListView.as_view(), name='specific_facility_users'),
    path('<uuid:user_id>/toggle-status/', UserStatusToggleView.as_view(), name='user_toggle_status'),
]

patient_patterns = [
    path('', PatientListView.as_view(), name='patient_list'),
    path('<uuid:pk>/', PatientDetailView.as_view(), name='patient_detail'),
    path('<uuid:patient_id>/children/', PatientChildrenListView.as_view(), name='patient_children'),
    path('register/', PatientCreateView.as_view(), name='patient_register'),
]

system_patterns = [
    path('audit-logs/', AuditLogListView.as_view(), name='audit_logs'),
    path('notifications/', NotificationListView.as_view(), name='notifications'),
    path('notifications/<uuid:pk>/mark-read/', NotificationMarkReadView.as_view(), name='notification_mark_read'),
    path('qstash-webhook/', QStashWebhookView.as_view(), name='qstash_webhook'),
]

stats_patterns = [
    path('overview/', DashboardStatsView.as_view(), name='stats_overview'),
    path('user-activity-trend/', UserActivityTrendView.as_view(), name='stats_user_activity_trend'),
    path('module-usage/', ModuleUsageStatsView.as_view(), name='stats_module_usage'),
    path('top-active-facilities/', TopActiveFacilitiesView.as_view(), name='stats_top_active_facilities'),
    path('facility-usage-table/', FacilityUsageTableView.as_view(), name='stats_facility_usage_table'),
    path('failed-logins-by-user/', FailedLoginsByUserView.as_view(), name='stats_failed_logins_by_user'),
    path('failed-logins-by-facility/', FailedLoginsByFacilityView.as_view(), name='stats_failed_logins_by_facility'),
    path('failed-logins-unknown-emails/', FailedLoginsUnknownEmailsView.as_view(), name='stats_failed_logins_unknown_emails'),
]

clinical_stats_patterns = [
    path('clinical-stats/', ClinicalStatsView.as_view(), name='clinical_stats'),
    path('patient-visit-trend/', PatientVisitTrendView.as_view(), name='clinical_stats_visit_trend'),
    path('clinical-activity/', ClinicalActivityView.as_view(), name='clinical_stats_activity'),
    path('disease-overview/', DiseaseOverviewView.as_view(), name='clinical_stats_disease_overview'),
]

from .view_reports import DailyActivityReportView, ComprehensiveModuleReportView, ModuleCompletionPercentageReportView

reports_patterns = [
    path('daily-activity/', DailyActivityReportView.as_view(), name='reports_daily_activity'),
    path('comprehensive-modules/', ComprehensiveModuleReportView.as_view(), name='reports_comprehensive_modules'),
    path('module-completion-percentages/', ModuleCompletionPercentageReportView.as_view(), name='reports_module_completion_percentages'),
]

alerts_patterns = [
    path('active/', ActiveAlertsView.as_view(), name='alerts_active'),
]

urlpatterns = (
    auth_patterns + user_management_patterns + patient_patterns + system_patterns
    + stats_patterns + clinical_stats_patterns + alerts_patterns + reports_patterns
)
