import os
from django.core.management.base import BaseCommand
from django.db import transaction
from tenants.models import State, Domain
from core.models import User
from django_tenants.utils import schema_context
from dotenv import load_dotenv

class Command(BaseCommand):
    help = 'Seeds the database with the public router and initial state tenants.'

    def handle(self, *args, **kwargs):
        load_dotenv()
        base_domain = os.environ.get('BASE_DOMAIN', 'localhost')
        self.stdout.write("Checking public tenant...")
        
        if not State.objects.filter(schema_name='public').exists():
            try:
                with transaction.atomic():
                    public_tenant = State(
                        schema_name='public',
                        name='National Health Router',
                    )
                    public_tenant.save()

                    Domain.objects.create(
                        domain=base_domain,
                        tenant=public_tenant,
                        is_primary=True
                    )
                self.stdout.write(self.style.SUCCESS(f"✅ Created Public Tenant with domain: {base_domain}"))
            except Exception as e:
                self.stdout.write(self.style.ERROR(f"❌ Error creating Public Tenant: {e}"))
                return
        else:
            self.stdout.write(self.style.SUCCESS("✅ Public tenant already exists. Skipping."))

        self.stdout.write("\nChecking state tenants...")
        states = ['Lagos', 'Kano', 'Rivers', 'FCT Abuja', 'Plateau', 'Kaduna', 'Oyo', 'Enugu', 'Anambra', 'Borno']

        for state_name in states:
            formatted_name = state_name.lower().replace(' ', '_')
            domain_url = f"{formatted_name}.{base_domain}"

            if State.objects.filter(schema_name=formatted_name).exists():
                self.stdout.write(self.style.WARNING(f"⚠️ Tenant '{state_name}' already exists. Skipping."))
                continue

            try:
                with transaction.atomic():
                    tenant = State(schema_name=formatted_name, name=state_name)
                    tenant.save() 

                    Domain.objects.create(
                        domain=domain_url,
                        tenant=tenant,
                        is_primary=True
                    )

                    with schema_context(tenant.schema_name):
                        admin_email = f"admin@{formatted_name}.health.gov.ng"
                        
                        User.objects.create_user(
                            username=admin_email, 
                            email=admin_email,
                            password='SecurePassword123!',
                            first_name=state_name,
                            last_name='Admin',
                            role='ADMIN',
                            is_staff=True
                        )
                        
                self.stdout.write(self.style.SUCCESS(f"✅ Successfully created state: {state_name} with admin: {admin_email}"))
            
            except Exception as e:
                self.stdout.write(self.style.ERROR(f"❌ Error creating {state_name}: {e}"))
