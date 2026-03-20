# tenants/models.py
import uuid
from django.db import models
from django_tenants.models import TenantMixin, DomainMixin

class State(TenantMixin):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=100)
    created_on = models.DateField(auto_now_add=True)
    auto_create_schema = True 

    def __str__(self):
        return self.name

class Domain(DomainMixin):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    pass
