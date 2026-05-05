from django.db import models
from core.models import BaseModel
from django.conf import settings

class Drug(BaseModel):
    facility = models.ForeignKey('facilities.Facility', on_delete=models.CASCADE, related_name='drugs')
    name = models.CharField(max_length=255)
    category = models.CharField(max_length=100, help_text="e.g., Analgesic, Antibiotic")
    unit = models.CharField(max_length=50, help_text="e.g., Tablets, Vials, mg")
    global_threshold = models.PositiveIntegerField(default=10, help_text="Level to trigger Low Stock warning")

    def __str__(self):
        return f"{self.name} ({self.unit})"

class DrugBatch(BaseModel):
    drug = models.ForeignKey(Drug, on_delete=models.CASCADE, related_name='batches')
    batch_number = models.CharField(max_length=100)
    initial_quantity = models.PositiveIntegerField()
    remaining_quantity = models.PositiveIntegerField()
    purchased_date = models.DateField()
    expiry_date = models.DateField()
    supplier = models.CharField(max_length=255)
    cost_price = models.DecimalField(max_digits=12, decimal_places=2)
    note = models.TextField(blank=True, null=True)

    def __str__(self):
        return f"{self.drug.name} - Batch {self.batch_number}"

class InventoryTransaction(BaseModel):
    TRANSACTION_TYPES = (
        ('REFILL', 'Refill'),
        ('DISPENSE', 'Dispense'),
        ('ADJUSTMENT', 'Adjustment'),
        ('EXPIRED', 'Expired'),
    )
    batch = models.ForeignKey(DrugBatch, on_delete=models.CASCADE, related_name='transactions')
    transaction_type = models.CharField(max_length=20, choices=TRANSACTION_TYPES)
    quantity = models.IntegerField(help_text="Positive for refills, negative for dispensing")
    performed_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True)

    def __str__(self):
        return f"{self.transaction_type}: {self.quantity} on {self.batch.batch_number}"
