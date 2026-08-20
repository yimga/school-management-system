"""Move FILES between the appliance and the cloud (G3), on their own schedule.

Files are deliberately not part of ``run_sync_cycle``. A delta cycle should finish in
seconds; a scanned report card on a village link takes minutes, and putting the two on
one schedule means every data cycle inherits the slowest file on the box — and a failed
upload fails the cycle. So this is its own command, run as often as the link can afford:

    python manage.py edge_sync_files                 # one bounded pass
    python manage.py edge_sync_files --pull-only     # receive only (a fresh box)
    python manage.py edge_sync_files --push-only     # send only (a box with evidence)
    python manage.py edge_sync_files --passes 4      # keep going while there is budget

Each pass is bounded by ``RMC_SYNC_FILE_BUDGET_BYTES`` and ``RMC_SYNC_FILE_MAX_PER_PASS``
and then stops. Stopping mid-queue is normal: offsets are durable, so the next pass
resumes exactly where this one left off, mid-file if need be.
"""
from __future__ import annotations

import os

from django.conf import settings
from django.core.management.base import BaseCommand
from django.urls import NoReverseMatch, reverse


class Command(BaseCommand):
    help = "Sync FileField attachments between this box and the cloud (resumable)."

    def add_arguments(self, parser):
        parser.add_argument("--school", default="", help="School id or subdomain (default: the only one)")
        parser.add_argument("--pull-only", action="store_true", help="Only receive files")
        parser.add_argument("--push-only", action="store_true", help="Only send files")
        parser.add_argument("--passes", type=int, default=1, help="Bounded passes to run")

    def handle(self, *args, **options):
        from apps.sync_engine.file_sync import file_sync_enabled, run_file_sync_pass

        if not file_sync_enabled():
            self.stdout.write(self.style.WARNING("file sync is disabled on this deployment"))
            return
        school = self._resolve_school(options.get("school") or "")
        if school is None:
            self.stderr.write(self.style.ERROR("no school resolved on this box"))
            return

        base = self._operator_base()
        token = (os.getenv("RMC_EDGE_CREDENTIAL") or "").strip()
        manifest_endpoint = base + self._path(
            "api:sync-file-manifest", "/api/v1/sync/files/manifest/"
        )
        chunk_endpoint = base + self._path("api:sync-file-chunk", "/api/v1/sync/files/chunk/")

        pull = not options.get("push_only")
        push = not options.get("pull_only")
        total = {"downloaded": 0, "uploaded": 0, "bytes": 0, "failed": 0}
        for index in range(max(1, int(options.get("passes") or 1))):
            result = run_file_sync_pass(
                school,
                manifest_endpoint=manifest_endpoint,
                chunk_endpoint=chunk_endpoint,
                token=token,
                push=push,
                pull=pull,
            )
            for key in total:
                total[key] += int(result.get(key) or 0)
            style = self.style.SUCCESS if result.get("ok") else self.style.WARNING
            self.stdout.write(style(f"pass {index + 1}: {result.get('message')}"))
            for err in (result.get("errors") or [])[:5]:
                self.stderr.write(self.style.WARNING(f"  {err}"))
            if not result.get("enqueued") and not result.get("downloaded") and not result.get("uploaded"):
                # Nothing moved and nothing queued: further passes would repeat the same
                # manifest round trip for no benefit.
                break
        self.stdout.write(
            f"files: {total['downloaded']} down, {total['uploaded']} up, "
            f"{total['bytes']} byte(s), {total['failed']} failed"
        )

    def _resolve_school(self, hint):
        from apps.schools.models import School

        qs = School.objects.all()
        if hint:
            return (
                qs.filter(subdomain=hint).first()
                or qs.filter(slug=hint).first()
                or qs.filter(pk=hint).first()
            )
        return qs.first() if qs.count() == 1 else None

    @staticmethod
    def _operator_base():
        base = (getattr(settings, "RMC_EDGE_OPERATOR_BASE", "") or "").strip()
        if not base:
            base = (getattr(settings, "RMC_HUB_BASE_URL", "") or "").strip()
        return base.rstrip("/")

    @staticmethod
    def _path(url_name, fallback):
        try:
            return reverse(url_name)
        except NoReverseMatch:
            return fallback
