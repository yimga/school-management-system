"""
Pass 13.C: ingest tenant policy / handbook documents into AIEmbeddingStore.

Walks a tenant's policies/handbook directory (configured per-school as
`school.settings["policy_doc_root"]`, or via the --path argument), chunks
each text-extractable file into ~1500-char windows, embeds each chunk via
the existing `services/embeddings.py` backend, and persists rows with
scope="policy" + metadata so the AI gateway can RAG-recall them.

Skips when the embedding backend is unavailable. Idempotent — chunks are
keyed by sha256(text), so re-running only adds genuinely new content.

  python manage.py ingest_policy_documents --school <uuid> --path /var/tenants/<slug>/policies
  python manage.py ingest_policy_documents --school <uuid> --dry-run

Currently supports .txt and .md natively. PDF parsing is delegated to
`pypdf` when installed; otherwise PDFs are reported and skipped.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

from django.core.management.base import BaseCommand


CHUNK_CHARS = 1500
CHUNK_OVERLAP = 200
SUPPORTED_EXTENSIONS = (".txt", ".md", ".pdf")


def _chunk(text: str) -> list[str]:
    text = text.strip()
    if not text:
        return []
    chunks: list[str] = []
    pos = 0
    while pos < len(text):
        chunks.append(text[pos : pos + CHUNK_CHARS])
        pos += CHUNK_CHARS - CHUNK_OVERLAP
    return chunks


def _hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _read_text_file(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return ""


def _read_pdf_file(path: Path) -> str:
    try:
        from pypdf import PdfReader
    except ImportError:
        return ""
    try:
        reader = PdfReader(str(path))
        return "\n".join((page.extract_text() or "") for page in reader.pages)
    except Exception:  # noqa: BLE001 - corrupt PDFs shouldn't crash ingestion
        return ""


class Command(BaseCommand):
    help = "Ingest tenant policy / handbook documents into AIEmbeddingStore for RAG."

    def add_arguments(self, parser):
        parser.add_argument("--school", required=True, help="School UUID.")
        parser.add_argument(
            "--path",
            default="",
            help="Directory to scan; defaults to school.settings.policy_doc_root.",
        )
        parser.add_argument(
            "--scope",
            default="policy",
            help="AIEmbeddingStore scope label (default: policy).",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Report only; do not embed or write.",
        )

    def handle(self, *args, **options):
        school_id = options["school"]
        scope = options["scope"]
        dry_run = bool(options["dry_run"])

        try:
            from apps.schools.models import School
        except ImportError:
            self.stderr.write(self.style.ERROR("apps.schools.models.School unavailable."))
            return

        school = School.objects.filter(id=school_id).first()
        if not school:
            self.stderr.write(self.style.ERROR(f"School {school_id} not found."))
            return

        path_arg = options.get("path") or ""
        if not path_arg:
            settings_dict = getattr(school, "settings", None) or {}
            path_arg = (settings_dict.get("policy_doc_root") or "").strip()
        if not path_arg:
            self.stderr.write(
                self.style.ERROR(
                    "No path supplied and school.settings.policy_doc_root is empty."
                )
            )
            return

        root = Path(path_arg)
        if not root.exists():
            self.stderr.write(self.style.ERROR(f"Path not found: {root}"))
            return

        try:
            from apps.siteconfig.models import AIEmbeddingStore
        except ImportError:
            self.stderr.write(
                self.style.ERROR("AIEmbeddingStore unavailable; cannot ingest.")
            )
            return

        try:
            from services.embeddings import get_embedding_provider

            embedder = get_embedding_provider() if not dry_run else None
        except ImportError:
            embedder = None
            if not dry_run:
                self.stderr.write(
                    self.style.WARNING(
                        "services.embeddings unavailable — running dry-only."
                    )
                )
                dry_run = True

        scanned = 0
        embedded = 0
        skipped = 0

        for path in sorted(root.rglob("*")):
            if not path.is_file():
                continue
            ext = path.suffix.lower()
            if ext not in SUPPORTED_EXTENSIONS:
                continue
            scanned += 1

            if ext in (".txt", ".md"):
                content = _read_text_file(path)
            elif ext == ".pdf":
                content = _read_pdf_file(path)
                if not content:
                    self.stderr.write(
                        f"  skipped (no text extracted): {path.name}"
                    )
                    continue
            else:
                continue

            for chunk in _chunk(content):
                text_hash = _hash(chunk)
                if AIEmbeddingStore.objects.filter(
                    school_id=school.id, scope=scope, text_hash=text_hash
                ).exists():
                    skipped += 1
                    continue
                if dry_run:
                    embedded += 1
                    continue
                vector = embedder.embed(chunk) if embedder else None
                if not vector:
                    skipped += 1
                    continue
                AIEmbeddingStore.objects.create(
                    school_id=school.id,
                    scope=scope,
                    text_hash=text_hash,
                    embedding=list(vector),
                    metadata={
                        "source_path": str(path.relative_to(root)),
                        "source_ext": ext,
                        "chunk_chars": len(chunk),
                    },
                )
                embedded += 1

        verb = "would embed" if dry_run else "embedded"
        self.stdout.write(
            self.style.SUCCESS(
                f"Policy ingestion: scanned {scanned} files; {verb} {embedded} chunks; "
                f"skipped {skipped} duplicates / unembeddable."
            )
        )
