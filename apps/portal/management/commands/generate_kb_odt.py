"""
Generate LibreOffice ODT documents for KB articles from their Markdown content.

Engines:
- LibreOffice headless (default when available) for MD -> HTML -> ODT.
- Pandoc for direct MD -> ODT with optional reference.odt.
"""
import os
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

from django.core.files import File
from django.core.files.base import ContentFile
from django.core.management.base import BaseCommand
from django.conf import settings

from apps.portal.document_conversion import convert_html_to_odt, find_soffice
from apps.portal.models_kb import KBArticle

# Optional: markdown library for higher quality HTML conversion
try:
    import markdown
    MARKDOWN_AVAILABLE = True
except ImportError:
    MARKDOWN_AVAILABLE = False


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
            "--engine",
            type=str,
            default="auto",
            choices=["auto", "libreoffice", "pandoc"],
            help="Conversion engine to use (auto prefers LibreOffice when available).",
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
        engine = self._resolve_engine(options.get("engine", "auto"))
        if not engine:
            return

        reference_doc = options.get("reference_doc") or self._find_reference_doc()
        add_toc = options.get("toc", False)
        dry_run = options.get("dry_run", False)
        overwrite = options.get("overwrite", False)

        if engine == "libreoffice":
            if add_toc:
                self.stdout.write(self.style.WARNING("Note: --toc is only supported with Pandoc; ignored for LibreOffice."))
            if reference_doc:
                self.stdout.write(self.style.WARNING("Note: --reference-doc is only supported with Pandoc; ignored for LibreOffice."))

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
                self._generate_odt(
                    article,
                    reference_doc=reference_doc,
                    add_toc=add_toc,
                    engine=engine,
                )
                success += 1
                self.stdout.write(self.style.SUCCESS(f"  [OK] {article.slug}"))
            except Exception as e:
                errors += 1
                self.stdout.write(self.style.ERROR(f"  [ERROR] {article.slug}: {e}"))

        self.stdout.write("")
        self.stdout.write(self.style.SUCCESS(f"Done. Generated: {success}, Errors: {errors}"))

    def _pandoc_available(self):
        return shutil.which("pandoc") is not None

    def _libreoffice_available(self):
        return find_soffice() is not None

    def _resolve_engine(self, engine: str | None) -> str | None:
        engine = (engine or "auto").lower().strip()
        if engine == "auto":
            if self._libreoffice_available():
                return "libreoffice"
            if self._pandoc_available():
                return "pandoc"
            self.stdout.write(
                self.style.ERROR(
                    "Neither LibreOffice nor Pandoc is available. Install LibreOffice (soffice) "
                    "or Pandoc to generate ODT files."
                )
            )
            return None
        if engine == "libreoffice":
            if not self._libreoffice_available():
                self.stdout.write(
                    self.style.ERROR(
                        "LibreOffice not found. Install it (soffice/libreoffice) or use --engine pandoc."
                    )
                )
                return None
            return "libreoffice"
        if engine == "pandoc":
            if not self._pandoc_available():
                self.stdout.write(
                    self.style.ERROR(
                        "Pandoc not found. Install it from https://pandoc.org/ or use --engine libreoffice."
                    )
                )
                return None
            return "pandoc"
        self.stdout.write(self.style.ERROR(f"Unknown engine: {engine}"))
        return None

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

    def _generate_odt(self, article, reference_doc=None, add_toc=False, engine="pandoc"):
        if not (article.content or "").strip():
            raise ValueError("Article has no content")

        # Delete old file if replacing (Django does not auto-delete)
        if article.odt_file:
            try:
                article.odt_file.delete(save=False)
            except Exception:
                pass

        filename = f"{article.slug}.odt"

        if engine == "libreoffice":
            html_content = self._markdown_to_html(article.content)
            odt_bytes = convert_html_to_odt(html_content, title=article.title)
            article.odt_file.save(filename, ContentFile(odt_bytes), save=True)
            return

        # Pandoc engine (default)
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

            with open(odt_path, "rb") as f:
                article.odt_file.save(filename, File(f), save=True)

    def _markdown_to_html(self, content: str) -> str:
        if MARKDOWN_AVAILABLE:
            try:
                md = markdown.Markdown(extensions=[
                    "fenced_code",
                    "tables",
                    "codehilite",
                    "nl2br",
                    "sane_lists",
                ])
                return md.convert(content)
            except Exception:
                pass
        return self._simple_markdown_to_html(content)

    def _simple_markdown_to_html(self, content: str) -> str:
        html = content

        # Headers
        html = re.sub(r"^# (.+)$", r"<h1>\\1</h1>", html, flags=re.MULTILINE)
        html = re.sub(r"^## (.+)$", r"<h2>\\1</h2>", html, flags=re.MULTILINE)
        html = re.sub(r"^### (.+)$", r"<h3>\\1</h3>", html, flags=re.MULTILINE)
        html = re.sub(r"^#### (.+)$", r"<h4>\\1</h4>", html, flags=re.MULTILINE)

        # Bold and italic
        html = re.sub(r"\\*\\*(.+?)\\*\\*", r"<strong>\\1</strong>", html)
        html = re.sub(r"\\*(.+?)\\*", r"<em>\\1</em>", html)

        # Code blocks and inline code
        html = re.sub(r"```(\\w+)?\\n(.*?)```", r"<pre><code class=\"language-\\1\">\\2</code></pre>", html, flags=re.DOTALL)
        html = re.sub(r"`(.+?)`", r"<code>\\1</code>", html)

        # Links
        html = re.sub(r"\\[(.+?)\\]\\((.+?)\\)", r"<a href=\"\\2\">\\1</a>", html)

        # Lists
        html = re.sub(r"^\\* (.+)$", r"<li>\\1</li>", html, flags=re.MULTILINE)
        html = re.sub(r"^- (.+)$", r"<li>\\1</li>", html, flags=re.MULTILINE)
        html = re.sub(r"^\\d+\\. (.+)$", r"<li>\\1</li>", html, flags=re.MULTILINE)
        html = re.sub(r"(<li>.*?</li>)", r"<ul>\\1</ul>", html, flags=re.DOTALL)

        # Paragraphs
        lines = html.split("\\n")
        result = []
        for line in lines:
            line = line.strip()
            if line and not line.startswith("<"):
                result.append(f"<p>{line}</p>")
            else:
                result.append(line)
        return "\\n".join(result)
