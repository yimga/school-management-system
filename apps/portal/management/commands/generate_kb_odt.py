"""
Generate KB documents (ODT and/or DOCX) from article Markdown content.

- ODT is saved on KBArticle.odt_file (optional if format selected).
- ODT/DOCX artifacts can be exported to a filesystem folder for distribution.
"""
from pathlib import Path

from django.conf import settings
from django.core.files.base import ContentFile
from django.core.management.base import BaseCommand

from apps.portal.document_generation import markdown_to_document
from apps.portal.models_kb import KBArticle


class Command(BaseCommand):
    help = "Convert KB articles to ODT/DOCX from Markdown content."

    def add_arguments(self, parser):
        parser.add_argument(
            "--all",
            action="store_true",
            help="Process all published articles with content (default when no --article-slug).",
        )
        parser.add_argument(
            "--article-slug",
            type=str,
            help="Process only one article by slug.",
        )
        parser.add_argument(
            "--engine",
            type=str,
            default="auto",
            choices=["auto", "pandoc", "libreoffice"],
            help="Conversion engine.",
        )
        parser.add_argument(
            "--formats",
            type=str,
            default="odt,docx",
            help="Comma-separated target formats: odt,docx",
        )
        parser.add_argument(
            "--reference-doc",
            type=str,
            default="",
            help="Reference ODT path for ODT generation (Pandoc engine).",
        )
        parser.add_argument(
            "--reference-docx",
            type=str,
            default="",
            help="Reference DOCX path for DOCX generation (Pandoc engine).",
        )
        parser.add_argument(
            "--toc",
            action="store_true",
            help="Add table of contents (Pandoc engine).",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Show actions without converting files.",
        )
        parser.add_argument(
            "--overwrite",
            action="store_true",
            help="Regenerate even when ODT is already attached.",
        )
        parser.add_argument(
            "--export-dir",
            type=str,
            default="",
            help="Optional folder for writing generated .odt/.docx artifacts.",
        )

    def handle(self, *args, **options):
        formats = self._parse_formats(options.get("formats", "odt,docx"))
        if not formats:
            self.stdout.write(self.style.ERROR("No valid formats selected. Use --formats odt,docx"))
            return

        reference_odt = options.get("reference_doc") or self._find_reference_doc("odt")
        reference_docx = options.get("reference_docx") or self._find_reference_doc("docx")
        export_dir = self._resolve_export_dir(options.get("export_dir"))

        slug = (options.get("article_slug") or "").strip()
        if slug:
            articles = KBArticle.objects.filter(slug=slug)
            if not articles.exists():
                self.stdout.write(self.style.ERROR(f"No article found with slug: {slug}"))
                return
        else:
            articles = KBArticle.objects.filter(status="PUBLISHED").exclude(content="").exclude(content__isnull=True)

        if not articles.exists():
            self.stdout.write(self.style.WARNING("No KB articles to process."))
            return

        dry_run = bool(options.get("dry_run"))
        overwrite = bool(options.get("overwrite"))

        if dry_run:
            self.stdout.write(
                f"Would process {articles.count()} article(s) -> formats: {', '.join(formats)}"
            )
            for article in articles:
                self.stdout.write(f"  - {article.slug}: {article.title}")
            if export_dir:
                self.stdout.write(f"  Export dir: {export_dir}")
            return

        if export_dir:
            export_dir.mkdir(parents=True, exist_ok=True)

        stats = {
            "odt_generated": 0,
            "odt_skipped": 0,
            "docx_generated": 0,
            "docx_skipped": 0,
            "errors": 0,
        }

        for article in articles:
            try:
                self._generate_for_article(
                    article=article,
                    formats=formats,
                    engine=options.get("engine", "auto"),
                    toc=bool(options.get("toc")),
                    overwrite=overwrite,
                    export_dir=export_dir,
                    reference_odt=reference_odt,
                    reference_docx=reference_docx,
                    stats=stats,
                )
                self.stdout.write(self.style.SUCCESS(f"  [OK] {article.slug}"))
            except Exception as exc:
                stats["errors"] += 1
                self.stdout.write(self.style.ERROR(f"  [ERROR] {article.slug}: {exc}"))

        self.stdout.write("")
        self.stdout.write(self.style.SUCCESS("KB document conversion completed."))
        self.stdout.write(f"  ODT generated: {stats['odt_generated']}")
        self.stdout.write(f"  ODT skipped:   {stats['odt_skipped']}")
        self.stdout.write(f"  DOCX generated:{stats['docx_generated']}")
        self.stdout.write(f"  DOCX skipped:  {stats['docx_skipped']}")
        self.stdout.write(f"  Errors:        {stats['errors']}")

    def _generate_for_article(
        self,
        *,
        article,
        formats,
        engine,
        toc,
        overwrite,
        export_dir: Path | None,
        reference_odt: str | None,
        reference_docx: str | None,
        stats: dict,
    ):
        content = (article.content or "").strip()
        if not content:
            raise ValueError("article has no Markdown content")

        if "odt" in formats:
            if article.odt_file and not overwrite:
                stats["odt_skipped"] += 1
            else:
                odt_bytes = markdown_to_document(
                    content,
                    output_format="odt",
                    title=article.title,
                    reference_doc=reference_odt,
                    engine=engine,
                    toc=toc,
                )
                if article.odt_file:
                    try:
                        article.odt_file.delete(save=False)
                    except Exception:
                        pass
                article.odt_file.save(f"{article.slug}.odt", ContentFile(odt_bytes), save=True)
                stats["odt_generated"] += 1
                if export_dir:
                    (export_dir / f"{article.slug}.odt").write_bytes(odt_bytes)

        if "docx" in formats:
            docx_path = (export_dir / f"{article.slug}.docx") if export_dir else None
            if docx_path and docx_path.exists() and not overwrite:
                stats["docx_skipped"] += 1
            else:
                docx_bytes = markdown_to_document(
                    content,
                    output_format="docx",
                    title=article.title,
                    reference_doc=reference_docx,
                    engine=engine,
                    toc=toc,
                )
                stats["docx_generated"] += 1
                if export_dir:
                    docx_path.write_bytes(docx_bytes)

    def _parse_formats(self, raw_formats: str) -> list[str]:
        valid = []
        for item in (raw_formats or "").split(","):
            fmt = item.strip().lower()
            if fmt in {"odt", "docx"} and fmt not in valid:
                valid.append(fmt)
        return valid

    def _resolve_export_dir(self, raw_export_dir: str | None) -> Path | None:
        if raw_export_dir:
            return Path(raw_export_dir).expanduser().resolve()
        media_root = Path(getattr(settings, "MEDIA_ROOT", "") or settings.BASE_DIR / "media")
        return media_root / "kb" / "generated"

    def _find_reference_doc(self, extension: str) -> str | None:
        base = Path(settings.BASE_DIR)
        candidates = [
            base / "docs" / "templates" / f"reference.{extension}",
            base / "static" / "kb" / f"reference.{extension}",
        ]
        for candidate in candidates:
            if candidate.exists():
                return str(candidate)
        return None
