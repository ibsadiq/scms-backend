# core/models.py
from django.db import models
import random


class GlobalIDRegistry(models.Model):
    """
    Lives in public schema.
    Tracks every student/teacher ID globally — prevents duplicates across tenants
    and records which school currently holds each person.
    """
    entity_type    = models.CharField(max_length=20, db_index=True)   # 'student' | 'teacher'
    unique_id      = models.CharField(max_length=50, unique=True, db_index=True)

    # Identity snapshot — filled by tenant on save, used for cross-school lookup
    first_name     = models.CharField(max_length=150, blank=True)
    last_name      = models.CharField(max_length=150, blank=True)
    date_of_birth  = models.DateField(null=True, blank=True)
    national_id    = models.CharField(max_length=100, blank=True, null=True, unique=True)

    # Which school currently holds this person (schema_name). Empty = "in transit".
    current_schema = models.CharField(max_length=63, blank=True, db_index=True)

    created_at     = models.DateTimeField(auto_now_add=True)
    updated_at     = models.DateTimeField(auto_now=True)

    class Meta:
        app_label = 'core'
        indexes = [
            models.Index(fields=['entity_type', 'unique_id']),
            models.Index(fields=['entity_type', 'current_schema']),
        ]

    def __str__(self):
        return f"{self.unique_id} ({self.first_name} {self.last_name}) @ {self.current_schema or 'in transit'}"

    @classmethod
    def generate_unique_id(cls, entity_type, code_length=8):
        """
        Generate a globally unique ID.
        Format: STU-A7K9X2M4 or TCH-B3N8Y6P1
        """
        from django.db import transaction

        prefix = 'STU' if entity_type == 'student' else 'TCH'
        # Exclude ambiguous chars: 0, O, I, 1, l
        chars = 'ABCDEFGHJKLMNPQRSTUVWXYZ23456789'

        for _ in range(10):
            code      = ''.join(random.SystemRandom().choice(chars) for _ in range(code_length))
            unique_id = f"{prefix}-{code}"
            try:
                with transaction.atomic():
                    cls.objects.create(entity_type=entity_type, unique_id=unique_id)
                    return unique_id
            except Exception:
                continue

        # Extremely rare fallback
        import time
        unique_id = f"{prefix}-{code}{str(int(time.time()))[-6:]}"
        cls.objects.create(entity_type=entity_type, unique_id=unique_id)
        return unique_id

    @classmethod
    def verify_unique(cls, unique_id):
        return cls.objects.filter(unique_id=unique_id).exists()

    @classmethod
    def sync(cls, unique_id, first_name='', last_name='', date_of_birth=None,
             current_schema='', national_id=None):
        """Update identity snapshot and current location for an existing registry entry."""
        from django.utils import timezone
        update_fields = dict(
            first_name=first_name or '',
            last_name=last_name or '',
            date_of_birth=date_of_birth,
            current_schema=current_schema,
            updated_at=timezone.now(),
        )
        if national_id:
            update_fields['national_id'] = national_id
        cls.objects.filter(unique_id=unique_id).update(**update_fields)


class TransferLog(models.Model):
    """
    Immutable audit trail for every student/teacher transfer between schools.
    Lives in the public schema.
    """
    entity_id      = models.CharField(max_length=50, db_index=True)   # STU-XXXXX / TCH-XXXXX
    entity_type    = models.CharField(max_length=20)                   # 'student' | 'teacher'
    from_schema    = models.CharField(max_length=63, blank=True)       # empty if first enrollment
    to_schema      = models.CharField(max_length=63)
    person_name    = models.CharField(max_length=300, blank=True)      # snapshot at time of transfer
    notes          = models.TextField(blank=True)
    transferred_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        app_label = 'core'
        ordering  = ['-transferred_at']
        indexes   = [
            models.Index(fields=['entity_id', 'transferred_at']),
        ]

    def __str__(self):
        return f"{self.entity_id}: {self.from_schema or '—'} → {self.to_schema} ({self.transferred_at:%Y-%m-%d})"
