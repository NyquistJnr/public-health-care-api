from django.contrib import admin

from .models import Disease, SystemThreshold


@admin.register(Disease)
class DiseaseAdmin(admin.ModelAdmin):
    list_display = ('name', 'severity', 'is_active', 'updated_at')
    list_filter = ('severity', 'is_active')
    search_fields = ('name',)


@admin.register(SystemThreshold)
class SystemThresholdAdmin(admin.ModelAdmin):
    list_display = (
        'disease_compliance_threshold_percent', 'failed_login_attempts_threshold',
        'system_error_threshold', 'inactive_facility_threshold_days',
        'high_usage_threshold_users', 'updated_at'
    )

    def has_add_permission(self, request):
        return not SystemThreshold.objects.exists()

    def has_delete_permission(self, request, obj=None):
        return False
