"""Seed Phase 9 P0 workflow KB articles (teacher/parent/school_admin)."""

from __future__ import annotations

import uuid

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.db import DatabaseError

from apps.platform_runtime.structured_logging import log_exception_with_context
from apps.portal.models_kb import HelpAudience, KBArticle, KBCategory
from apps.portal.workflow_kb_corpus import ALL_WORKFLOW_KB_CORPUS

User = get_user_model()


class Command(BaseCommand):
    help = "Seed published KB how-tos for Phase 9 P0 workflows (teacher/parent/admin)."

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Print actions without writing.",
        )

    def handle(self, *args, **options):
        from django.conf import settings as dj_settings

        dry_run = bool(options.get("dry_run"))
        prior_auto_refresh = getattr(dj_settings, "KB_EMBEDDING_AUTO_REFRESH", True)
        dj_settings.KB_EMBEDDING_AUTO_REFRESH = False
        author = None
        try:
            author = User.objects.filter(is_superuser=True).first() or User.objects.first()
        except DatabaseError:
            log_exception_with_context(
                "seed_workflow_kb_corpus: resolve author failed",
                extra={"command": "seed_workflow_kb_corpus"},
            )

        try:
            created = 0
            updated = 0
            for row in ALL_WORKFLOW_KB_CORPUS:
                cat_slug = row["category_slug"]
                if dry_run:
                    self.stdout.write(f"  would ensure: {row['slug']} ({row['workflow_id']})")
                    continue
                category, _ = KBCategory.objects.get_or_create(
                    slug=cat_slug,
                    defaults={
                        "name": cat_slug.replace("-", " ").title(),
                        "description": "",
                        "icon": "bi-journal-text",
                        "display_order": 50,
                        "target_roles": [],
                    },
                )
                audience_raw = row.get("help_audience") or HelpAudience.TENANT
                if isinstance(audience_raw, str):
                    help_audience = getattr(
                        HelpAudience, audience_raw, HelpAudience.TENANT
                    )
                else:
                    help_audience = audience_raw
                defaults = {
                    "title": row["title"],
                    "summary": row["summary"],
                    "content": row["content"].strip(),
                    "category": category,
                    "status": "PUBLISHED",
                    "help_audience": help_audience,
                    "target_roles": list(row.get("target_roles") or []),
                    "tags": row.get("tags", ""),
                    "is_featured": True,
                    "is_global_article": True,
                    "author": author,
                }
                article, was_created = KBArticle.objects.update_or_create(
                    slug=row["slug"],
                    school__isnull=True,
                    defaults=defaults,
                )
                if not article.locale_group_id:
                    article.locale_group_id = str(uuid.uuid4())
                    article.save(update_fields=["locale_group_id"])
                if was_created:
                    created += 1
                else:
                    updated += 1

            if dry_run:
                self.stdout.write(
                    self.style.SUCCESS(
                        f"Dry run: {len(ALL_WORKFLOW_KB_CORPUS)} workflow articles."
                    )
                )
                return
            self.stdout.write(
                self.style.SUCCESS(
                    f"Workflow KB corpus: {created} created, {updated} updated "
                    f"({len(ALL_WORKFLOW_KB_CORPUS)} total)."
                )
            )
        finally:
            dj_settings.KB_EMBEDDING_AUTO_REFRESH = prior_auto_refresh
