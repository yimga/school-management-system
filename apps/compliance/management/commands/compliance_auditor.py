"""
Phase Compliance optional: Periodic compliance health checks (stub).

Run via Celery Beat or cron. Cross-tenant read-only checks: pending waiver requests,
RegionFeatureCompliance coverage, etc. Outputs a simple health score / checklist.
Usage: python manage.py compliance_auditor [--json]
"""
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "Run compliance health checks (pending waivers, region rules); output score/checklist."

    def add_arguments(self, parser):
        parser.add_argument("--json", action="store_true", help="Output JSON")

    def handle(self, *args, **options):
        out = []
        try:
            from apps.siteconfig.models import WaiverRequest
            pending = WaiverRequest.objects.filter(status=WaiverRequest.Status.PENDING).count()
            out.append({"check": "waiver_requests_pending", "value": pending, "ok": pending < 100})
        except Exception as e:
            out.append({"check": "waiver_requests_pending", "error": str(e), "ok": False})
        try:
            from apps.compliance.models import RegionFeatureCompliance
            rules = RegionFeatureCompliance.objects.count()
            out.append({"check": "region_feature_compliance_rules", "value": rules, "ok": True})
        except Exception as e:
            out.append({"check": "region_feature_compliance_rules", "error": str(e), "ok": False})
        ok_count = sum(1 for o in out if o.get("ok") is True)
        total = len(out)
        score = (ok_count / total * 100) if total else 100
        if options.get("json"):
            import json
            self.stdout.write(json.dumps({"score": score, "checks": out}))
        else:
            self.stdout.write("Compliance auditor (stub)")
            for o in out:
                self.stdout.write("  %s: %s" % (o.get("check", "?"), "ok" if o.get("ok") else o.get("error", o)))
            self.stdout.write("Score: %s%%" % round(score))
