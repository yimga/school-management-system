"""
Phase 10 — 1.2: Backfill RuntimeDefaults.payload from SiteSettings (JSON-serializable fields only).
Run once after deploying RuntimeDefaults; get_effective_site_settings will overlay this on base.
"""
from django.core.management.base import BaseCommand


def _json_safe(value):
    if value is None:
        return None
    if isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, (list, tuple)):
        return [_json_safe(x) for x in value]
    if isinstance(value, dict):
        return {k: _json_safe(v) for k, v in value.items()}
    if hasattr(value, "pk"):
        return value.pk
    if hasattr(value, "url"):
        return getattr(value, "url", None) or str(value)
    return str(value)


class Command(BaseCommand):
    help = "Backfill platform_runtime.RuntimeDefaults from SiteSettings (Phase 10 — 1.2)."

    def handle(self, *args, **options):
        from apps.siteconfig.models import SiteSettings
        from apps.platform_runtime.models import RuntimeDefaults

        site = SiteSettings.get_solo()
        payload = {}
        for f in site._meta.get_fields():
            if getattr(f, "concrete", True) and hasattr(f, "name"):
                name = f.name
                if name in ("id",):
                    continue
                try:
                    val = getattr(site, name, None)
                    payload[name] = _json_safe(val)
                except Exception:
                    continue
        obj, created = RuntimeDefaults.objects.get_or_create(
            pk=1,
            defaults={"payload": payload},
        )
        if not created:
            obj.payload = payload
            obj.save(update_fields=["payload", "updated_at"])
        self.stdout.write(
            self.style.SUCCESS(f"RuntimeDefaults id=1 {'created' if created else 'updated'} with {len(payload)} keys.")
        )
