from django.db import models
from core.models import BaseModel
from django.conf import settings

class InventoryItem(BaseModel):
    CATEGORY_CHOICES = (
        ('DRUG', 'Drug / Medication'),
        ('LAB_EQUIPMENT', 'Laboratory Equipment'),
        ('CONSUMABLE', 'General Consumable')
    )
    DRUG_CLASS_CHOICES = (
        ('NORMAL', 'Normal Medication'),
        ('IMMUNIZATION', 'Immunization / Vaccine'),
    )

    facility = models.ForeignKey('facilities.Facility', on_delete=models.CASCADE, related_name='inventory_items')
    name = models.CharField(max_length=255)
    inventory_category = models.CharField(max_length=20, choices=CATEGORY_CHOICES, default='DRUG')
    drug_classification = models.CharField(max_length=20, choices=DRUG_CLASS_CHOICES, null=True, blank=True)
    item_type = models.CharField(max_length=50, help_text="e.g., Tablets, Vials, Pieces, Packs")
    global_threshold = models.PositiveIntegerField(default=10, help_text="Level to trigger Low Stock warning")
    schedule_rules = models.JSONField(
        blank=True, 
        null=True, 
        help_text="JSON defining the dosage intervals. Leave null if not applicable."
    )

    def __str__(self):
        return f"{self.name} ({self.get_inventory_category_display()})"


class ItemBatch(BaseModel):
    """Formerly DrugBatch. Now holds data for any inventory item."""
    item = models.ForeignKey(InventoryItem, on_delete=models.CASCADE, related_name='batches')
    batch_number = models.CharField(max_length=100)
    initial_quantity = models.PositiveIntegerField()
    remaining_quantity = models.PositiveIntegerField()
    purchased_date = models.DateField()
    expiry_date = models.DateField(null=True, blank=True) 
    supplier = models.CharField(max_length=255)
    cost_price = models.DecimalField(max_digits=12, decimal_places=2)
    note = models.TextField(blank=True, null=True)

    def __str__(self):
        return f"{self.item.name} - Batch {self.batch_number}"


class InventoryTransaction(BaseModel):
    TRANSACTION_TYPES = (
        ('REFILL', 'Refill'),
        ('DISPENSE', 'Dispense'),
        ('ADJUSTMENT', 'Adjustment'),
        ('EXPIRED', 'Expired'),
    )
    batch = models.ForeignKey(ItemBatch, on_delete=models.CASCADE, related_name='transactions')
    transaction_type = models.CharField(max_length=20, choices=TRANSACTION_TYPES)
    quantity = models.IntegerField(help_text="Positive for refills, negative for dispensing")
    performed_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True)

    def __str__(self):
        return f"{self.transaction_type}: {self.quantity} on {self.batch.batch_number}"
