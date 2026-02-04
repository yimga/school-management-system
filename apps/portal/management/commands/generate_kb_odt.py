"""
Generate LibreOffice ODT documents for KB articles from their Markdown content.

Requires Pandoc: https://pandoc.org/ (e.g. apt-get install pandoc, brew install pandoc).
Optional: reference.odt in docs/templates/ or static/kb/ for consistent styling.
"""
import os
import shutil
import subprocess
import tempfile
from pathlib import Path

from django.core.files import File
from django.core.management.base import BaseCommand
from django.conf import settings

from apps.portal.models_kb import KBArticle


class Command(BaseCommand):
    help = "Convert KB articles (Markdown content) to LibreOffice ODT; set article.odt_file."

    def add_arguments(self, parser):
        parser.add_argument(
            "--all",
            action="store_true",
            help="Process all published articles with content (default: all if no --article-slug).",
        )
        parser.add_argument(
            "--article-slug",
            type=str,
            help="Process only this article slug.",
        )
        parser.add_argument(
            "--reference-doc",
            type=str,
            default="",
            help="Path to reference ODT for Pandoc (optional).",
        )
        parser.add_argument(
            "--toc",
            action="store_true",
            help="Add table of contents to ODT.",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Only report what would be converted.",
        )
        parser.add_argument(
            "--overwrite",
            action="store_true",
            help="Regenerate ODT even when odt_file already exists.",
        )

    def handle(self, *args, **options):
        if not self._pandoc_available():
            self.stdout.write(
                self.style.ERROR(
                    "Pandoc not found. Install it from https://pandoc.org/ "
                    "(e.g. apt-get install pandoc, brew install pandoc)."
                )
            )
            return

        reference_doc = options.get("reference_doc") or self._find_reference_doc()
        add_toc = options.get("toc", False)
        dry_run = options.get("dry_run", False)
        overwrite = options.get("overwrite", False)

        slug = options.get("article_slug")
        if slug:
            articles = KBArticle.objects.filter(slug=slug)
            if not articles.exists():
                self.stdout.write(self.style.ERROR(f"No article with slug: {slug}"))
                return
        else:
            articles = KBArticle.objects.filter(status="PUBLISHED").exclude(content="").exclude(content__isnull=True)

        if not articles.exists():
            self.stdout.write(self.style.WARNING("No articles to process."))
            return

        if dry_run:
            self.stdout.write(f"Would process {articles.count()} article(s).")
            for a in articles:
                self.stdout.write(f"  - {a.slug}: {a.title}")
            return

        success = 0
        errors = 0
        for article in articles:
            if article.odt_file and not overwrite:
                self.stdout.write(f"  [SKIP] {article.slug} (already has ODT; use --overwrite to regenerate)")
                continue
            try:
                self._generate_odt(article, reference_doc=reference_doc, add_toc=add_toc)
                success += 1
                self.stdout.write(self.style.SUCCESS(f"  [OK] {article.slug}"))
            except Exception as e:
                errors += 1
                self.stdout.write(self.style.ERROR(f"  [ERROR] {article.slug}: {e}"))

        self.stdout.write("")
        self.stdout.write(self.style.SUCCESS(f"Done. Generated: {success}, Errors: {errors}"))

    def _pandoc_available(self):
        return shutil.which("pandoc") is not None

    def _find_reference_doc(self):
        """Look for reference.odt in docs/templates/ or static/kb/."""
        base = Path(settings.BASE_DIR)
        for candidate in [
            base / "docs" / "templates" / "reference.odt",
            base / "static" / "kb" / "reference.odt",
        ]:
            if candidate.exists():
                return str(candidate)
        return None

    def _generate_odt(self, article, reference_doc=None, add_toc=False):
        if not (article.content or "").strip():
            raise ValueError("Article has no content")

        with tempfile.TemporaryDirectory() as tmp:
            md_path = os.path.join(tmp, "article.md")
            odt_path = os.path.join(tmp, "article.odt")

            with open(md_path, "w", encoding="utf-8") as f:
                f.write(article.content)

            cmd = [
                "pandoc",
                md_path,
                "-o",
                odt_path,
                "--from=markdown",
                "--to=odt",
                "--metadata",
                f"title={article.title}",
            ]
            if add_toc:
                cmd.extend(["--toc"])
            if reference_doc:
                cmd.extend(["--reference-doc", reference_doc])

            result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
            if result.returncode != 0:
                raise RuntimeError(result.stderr or result.stdout or "Pandoc failed")

            if not os.path.exists(odt_path):
                raise RuntimeError("Pandoc did not produce output file")

            # Delete old file if replacing (Django does not auto-delete)
            if article.odt_file:
                try:
                    article.odt_file.delete(save=False)
                except Exception:
                    pass

            # Save to storage with a stable name
            filename = f"{article.slug}.odt"
            with open(odt_path, "rb") as f:
                article.odt_file.save(filename, File(f), save=True)
