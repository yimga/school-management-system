"""
Ingest policy bundles, blueprint packs, workflow packs, report templates, and help/config
docs into the AI embedding store for RAG (setup assistant, policy explain, admin copilot).
Run after catalog changes or on schedule. Scoped by tenant where applicable.
"""
from __future__ import annotations

import logging

from django.core.management.base import BaseCommand

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "Index policy bundles, blueprint packs, workflow packs, report templates, and docs into AI embedding store."

    def add_arguments(self, parser):
        parser.add_argument(
            "--scope",
            type=str,
            default=None,
            help="Only index this scope: policy, blueprint, workflow, report, help, config.",
        )
        parser.add_argument(
            "--school-id",
            type=str,
            default=None,
            help="Only index for this school (UUID); default: all.",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Do not write to store; only log what would be indexed.",
        )

    def handle(self, *args, **options):
        from services.ai_memory import AIMemoryService, get_embedding_for_text

        if not get_embedding_for_text("test", max_tokens=10):
            self.stdout.write(self.style.ERROR("Embedding provider unavailable. Set AI_EMBEDDING_*."))
            return

        scopes = [options["scope"]] if options["scope"] else ["policy", "blueprint", "workflow", "report", "help", "config"]
        school_id = options.get("school_id")
        dry_run = options.get("dry_run", False)
        indexed = 0

        if "policy" in scopes:
            indexed += self._index_policy_bundles(school_id, dry_run)
        if "blueprint" in scopes:
            indexed += self._index_blueprint_packs(school_id, dry_run)
        if "workflow" in scopes:
            indexed += self._index_workflow_packs(school_id, dry_run)
        if "report" in scopes:
            indexed += self._index_report_templates(school_id, dry_run)
        if "help" in scopes or "config" in scopes:
            indexed += self._index_static_docs(scopes, dry_run)

        self.stdout.write(self.style.SUCCESS(f"Indexed {indexed} chunks (dry_run={dry_run})."))

    def _index_policy_bundles(self, school_id, dry_run):
        try:
            from apps.policies.models import PolicyBundle
            qs = PolicyBundle.objects.filter(is_active=True)
            if school_id:
                qs = qs.filter(school_id=school_id)
            count = 0
            for b in qs:
                text = f"{b.name or b.code or 'Policy'}\n{b.description or ''}\n{b.migration_notes or ''}\nSections: {', '.join((b.policy_snapshot or {}).keys())}"
                text = text.strip()[:8000]
                if not text:
                    continue
                cid = f"policy_bundle:{b.id}"
                if not dry_run:
                    if AIMemoryService.store(str(b.school_id) if b.school_id else None, cid, "policy", text, {"source": "PolicyBundle", "id": b.id, "name": b.name}):
                        count += 1
                else:
                    count += 1
            return count
        except Exception as e:
            logger.warning("index policy_bundles: %s", e)
            return 0

    def _index_blueprint_packs(self, school_id, dry_run):
        try:
            from apps.policies.models import BlueprintPack
            qs = BlueprintPack.objects.filter(is_active=True)
            count = 0
            for b in qs:
                text = f"{b.name}\n{b.description or ''}\nCategory: {b.category or ''}\nFamily: {b.family or ''}\nSections: {', '.join((b.policy_snapshot or {}).keys())}"
                text = text.strip()[:8000]
                if not text:
                    continue
                cid = f"blueprint_pack:{b.id}"
                if not dry_run:
                    if AIMemoryService.store(None, cid, "blueprint", text, {"source": "BlueprintPack", "id": b.id, "slug": b.slug, "name": b.name}):
                        count += 1
                else:
                    count += 1
            return count
        except Exception as e:
            logger.warning("index blueprint_packs: %s", e)
            return 0

    def _index_workflow_packs(self, school_id, dry_run):
        try:
            from apps.siteconfig.models_workflow import WorkflowPack
            qs = WorkflowPack.objects.filter(is_active=True)
            count = 0
            for w in qs:
                text = f"{w.name}\n{w.description or ''}\nCode: {w.code}\nFamily: {w.family or ''}"
                text = text.strip()[:8000]
                if not text:
                    continue
                cid = f"workflow_pack:{w.id}"
                if not dry_run:
                    if AIMemoryService.store(None, cid, "workflow", text, {"source": "WorkflowPack", "id": w.id, "code": w.code, "name": w.name}):
                        count += 1
                else:
                    count += 1
            return count
        except Exception as e:
            logger.warning("index workflow_packs: %s", e)
            return 0

    def _index_report_templates(self, school_id, dry_run):
        try:
            from apps.siteconfig.models import ReportTemplate
            qs = ReportTemplate.objects.all()
            if school_id:
                if hasattr(ReportTemplate, "school_id"):
                    qs = qs.filter(school_id=school_id)
            count = 0
            for r in qs:
                name = getattr(r, "name", None) or getattr(r, "code", None) or "Report"
                desc = getattr(r, "description", None) or ""
                text = f"{name}\n{desc}".strip()[:8000]
                if not text:
                    continue
                cid = f"report_template:{getattr(r, 'id', id(r))}"
                sid = str(getattr(r, "school_id", None)) if getattr(r, "school_id", None) else None
                if not dry_run:
                    if AIMemoryService.store(sid, cid, "report", text, {"source": "ReportTemplate", "name": name}):
                        count += 1
                else:
                    count += 1
            return count
        except Exception as e:
            logger.warning("index report_templates: %s", e)
            return 0

    def _index_static_docs(self, scopes, dry_run):
        count = 0
        help_texts = [
            ("help:setup", "help", "Setup Studio: configure school settings, features, and workflows. Use the checklist to complete onboarding."),
            ("help:config", "config", "Control Plane: manage tenants, billing, and platform configuration. Admin only."),
            ("help:workflows", "help", "Workflows: automate actions based on triggers (e.g. attendance, fees). Create and assign workflow packs."),
            ("help:policies", "help", "Policies: grading, attendance, finance, and compliance. Apply blueprint packs for your region."),
        ]
        for cid, scope, text in help_texts:
            if scope not in scopes:
                continue
            if not dry_run:
                if AIMemoryService.store(None, cid, scope, text, {"source": "static", "id": cid}):
                    count += 1
            else:
                count += 1
        return count
