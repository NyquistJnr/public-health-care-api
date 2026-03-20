# core/management/commands/setup_rbac.py
from django.core.management.base import BaseCommand
from django.contrib.auth.models import Group, Permission
from django.contrib.contenttypes.models import ContentType
from core.models import User
from tenants.models import State
from django_tenants.utils import schema_context

class Command(BaseCommand):
    help = 'Creates default roles and permissions across all tenants.'

    def handle(self, *args, **kwargs):
        ROLES_AND_PERMISSIONS = {
            'ADMIN': [
                'add_facility', 'view_facility', 'change_facility', 'delete_facility'
            ],
            'FACILITY_IT_ADMIN': [
                'view_facility', 'change_facility',
                'add_user', 'change_user', 'view_user'
            ],
            'DOCTOR': [
                'view_facility',
                'view_patient_profile', 'view_patient_history',
                'add_medical_record', 'view_medical_record', 'change_own_medical_record',
                'add_prescription', 'view_prescription', 'cancel_prescription',
                'view_appointment', 'change_appointment_status', 'add_appointment_note',
                'add_lab_order', 'view_lab_result'
            ],
            'NURSE': [
                'view_facility',
                'view_patient_profile', 'view_patient_history',
                'view_medical_record', 'add_nursing_note',
                'view_prescription', 'dispense_prescription',
                'view_appointment', 'view_lab_result'
            ],
            'PATIENT': [
                'view_own_record', 'view_own_prescription', 'add_own_appointment', 'cancel_own_appointment'
            ]
        }

        for tenant in State.objects.exclude(schema_name='public'):
            self.stdout.write(f"\nConfiguring RBAC for: {tenant.name}...")
            
            with schema_context(tenant.schema_name):
                content_type = ContentType.objects.get_for_model(User)

                for role_name, perms in ROLES_AND_PERMISSIONS.items():
                    group, _ = Group.objects.get_or_create(name=role_name)
                    
                    for perm_code in perms:
                        permission = Permission.objects.filter(codename=perm_code).first()
                        
                        if not permission:
                            permission = Permission.objects.create(
                                codename=perm_code,
                                content_type=content_type,
                                name=f"Can {perm_code.replace('_', ' ')}"
                            )
                        
                        group.permissions.add(permission)
                    
                    self.stdout.write(self.style.SUCCESS(f"  ✅ Configured {role_name} with {len(perms)} permissions."))
