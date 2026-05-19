"""
Regional payment rail catalog (G-22).

Canonical orchestration lives in ``apps.finance`` (PaymentRail, RegionPaymentProfile).
This app exposes read-only references for marketplace/docs without duplicating rails.
"""

from django.db import models


class RegionalPaymentRailCatalog(models.Model):
    """ISO2 country → primary/backup rail codes (see apps.finance.payment_region_catalog)."""

    country_code = models.CharField(max_length=3, unique=True, db_index=True)
    primary_rail_code = models.CharField(max_length=64)
    primary_rail_label = models.CharField(max_length=120)
    backup_rail_code = models.CharField(max_length=64, blank=True)
    backup_rail_label = models.CharField(max_length=120, blank=True)
    is_active = models.BooleanField(default=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Regional payment rail catalog entry"
        verbose_name_plural = "Regional payment rail catalog entries"

    def __str__(self) -> str:
        return f"{self.country_code}: {self.primary_rail_label}"
