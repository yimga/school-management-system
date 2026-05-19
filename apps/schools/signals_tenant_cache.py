"""Invalidate tenant host/subdomain resolution cache when domains change (AWS pillar)."""

from __future__ import annotations

from django.db.models.signals import post_delete, post_save
from django.dispatch import receiver

from apps.schools.models import School, SchoolDomain
from apps.schools.tenant_resolution_cache import invalidate_tenant_resolution_cache


@receiver(post_save, sender=SchoolDomain)
@receiver(post_delete, sender=SchoolDomain)
def invalidate_cache_on_school_domain_change(sender, instance, **kwargs) -> None:
    del sender, kwargs
    domain = (getattr(instance, "domain", None) or "").strip()
    if domain:
        invalidate_tenant_resolution_cache(host=domain)
    school = getattr(instance, "school", None)
    if school is not None:
        subdomain = (getattr(school, "subdomain", None) or "").strip()
        if subdomain:
            invalidate_tenant_resolution_cache(subdomain=subdomain)


@receiver(post_save, sender=School)
def invalidate_cache_on_school_host_fields(sender, instance, **kwargs) -> None:
    del sender, kwargs
    subdomain = (getattr(instance, "subdomain", None) or "").strip()
    custom = (getattr(instance, "custom_domain", None) or "").strip()
    if subdomain:
        invalidate_tenant_resolution_cache(subdomain=subdomain)
    if custom:
        invalidate_tenant_resolution_cache(host=custom)
