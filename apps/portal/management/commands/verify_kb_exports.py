from __future__ import annotations

from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from apps.portal.models_kb import KBArticle


class Command(BaseCommand):
    help = "Verify published KB exports exist for ODT and/or DOCX outputs."

    def add_arguments(self, parser):
        parser.add_argument(
            "--formats",
            type=str,
            default="odt,docx",
            help="Comma-separated formats to verify: odt,docx",
        )
        parser.add_argument(
            "--export-dir",
            type=str,
            default="",
            help="Folder containing DOCX exports (default: MEDIA_ROOT/kb/generated).",
        )
        parser.add_argument(
            "--article-slug",
            type=str,
            default="",
            help="Limit verification to one article slug.",
        )
        parser.add_argument(
            "--strict",
            action="store_true",
            help="Fail with non-zero exit code if any export is missing.",
        )

    def handle(self, *args, **options):
        formats = self._parse_formats(options.get("formats", "odt,docx"))
        if not formats:
            raise CommandError("No valid formats selected. Use --formats odt,docx")

        slug = (options.get("article_slug") or "").strip()
        if slug:
            articles = KBArticle.objects.filter(slug=slug)
            if not articles.exists():
                raise CommandError(f"No article found with slug: {slug}")
        else:
            articles = (
                KBArticle.objects.filter(status="PUBLISHED")
                .exclude(content="")
                .exclude(content__isnull=True)
            )

        if not articles.exists():
            self.stdout.write(self.style.WARNING("No published KB articles found."))
            return

        export_dir = self._resolve_export_dir(options.get("export_dir"))
        missing: list[str] = []

        for article in articles:
            if "odt" in formats:
                odt_file = getattr(article, "odt_file", None)
                if not odt_file or not odt_file.name:
                    missing.append(f"{article.slug}: missing ODT attachment on KBArticle")
                elif not odt_file.storage.exists(odt_file.name):
                    missing.append(f"{article.slug}: ODT file missing in storage ({odt_file.name})")

            if "docx" in formats:
                docx_path = export_dir / f"{article.slug}.docx"
                if not docx_path.exists():
                    missing.append(f"{article.slug}: missing DOCX export ({docx_path})")

        if missing:
            self.stdout.write(self.style.WARNING("KB export verification found missing artifacts:"))
            for line in missing:
                self.stdout.write(f"- {line}")
            if options.get("strict"):
                raise CommandError(f"KB export verification failed with {len(missing)} issue(s).")
            return

        self.stdout.write(
            self.style.SUCCESS(
                f"KB export verification passed for {articles.count()} article(s) [{', '.join(formats)}]."
            )
        )

    def _parse_formats(self, raw_formats: str) -> list[str]:
        valid = []
        for item in (raw_formats or "").split(","):
            fmt = item.strip().lower()
            if fmt in {"odt", "docx"} and fmt not in valid:
                valid.append(fmt)
        return valid

    def _resolve_export_dir(self, raw_export_dir: str | None) -> Path:
        if raw_export_dir:
            return Path(raw_export_dir).expanduser().resolve()
        media_root = Path(getattr(settings, "MEDIA_ROOT", "") or settings.BASE_DIR / "media")
        return media_root / "kb" / "generated"
