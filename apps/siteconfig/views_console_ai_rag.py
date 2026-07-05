"""Admin-triggered policy / handbook RAG ingestion.

Mirrors `ingest_policy_documents` management command but is callable
from the operator console without shell access. Staff/superuser only;
respects the tenant's effective AI policy (skips when AI is disabled
for the school).

POST `/console/ai/rag/ingest/` body (JSON):

  {
    "school_id": "<uuid>",
    "path": "/var/tenants/<slug>/policies",   // optional; falls back to school.settings.policy_doc_root
    "scope": "policy",                         // optional
    "dry_run": true                            // optional
  }

Response:

  {"success": true, "scanned": N, "embedded": N, "skipped": N, "dry_run": bool}
"""

from __future__ import annotations

import hashlib
import json
import logging
from pathlib import Path
from typing import Any

from django.contrib.admin.views.decorators import staff_member_required
from apps.schools.control_plane import require_control_plane_access
from django.http import HttpRequest, JsonResponse
from django.views.decorators.csrf import csrf_protect
from django.views.decorators.http import require_POST

logger = logging.getLogger(__name__)

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
    except Exception:  # noqa: BLE001
        return ""


def _err(message: str, status: int = 400) -> JsonResponse:
    return JsonResponse({"success": False, "error": message}, status=status)


@require_POST
@csrf_protect
@require_control_plane_access
def ingest_policy_docs(request: HttpRequest) -> JsonResponse:
    """Operator-triggered RAG ingest for one tenant."""
    try:
        payload: dict[str, Any] = json.loads(request.body or b"{}")
    except json.JSONDecodeError:
        return _err("Invalid JSON body.")

    school_id = (payload.get("school_id") or "").strip()
    if not school_id:
        return _err("school_id is required.")

    scope = (payload.get("scope") or "policy").strip() or "policy"
    dry_run = bool(payload.get("dry_run"))
    path_arg = (payload.get("path") or "").strip()

    try:
        from apps.schools.models import School
    except ImportError:
        return _err("apps.schools.models.School unavailable.", status=500)

    school = School.objects.filter(id=school_id).first()
    if not school:
        return _err(f"School {school_id} not found.", status=404)

    if not path_arg:
        settings_dict = getattr(school, "settings", None) or {}
        path_arg = (settings_dict.get("policy_doc_root") or "").strip()
    if not path_arg:
        return _err(
            "No path supplied and school.settings.policy_doc_root is empty."
        )

    root = Path(path_arg)
    if not root.exists() or not root.is_dir():
        return _err(f"Path not found or not a directory: {root}", status=404)

    try:
        from apps.siteconfig.models import AIEmbeddingStore
    except ImportError:
        return _err("AIEmbeddingStore unavailable.", status=500)

    embedder = None
    if not dry_run:
        try:
            from services.embeddings import get_embedding_provider

            embedder = get_embedding_provider()
        except ImportError:
            logger.warning(
                "RAG ingest: services.embeddings unavailable; switching to dry_run"
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
                skipped += 1
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
                    "ingested_by": request.user.pk,
                },
            )
            embedded += 1

    try:
        from apps.compliance.non_repudiation import record_action

        record_action(
            action="AI_RAG_INGEST_TRIGGERED",
            resource="ai_rag_ingest",
            actor_id=getattr(request.user, "id", None),
            school_id=school.id,
            payload_summary={
                "scope": scope,
                "scanned": scanned,
                "embedded": embedded,
                "skipped": skipped,
                "dry_run": dry_run,
            },
        )
    except Exception:  # noqa: BLE001 - audit is best-effort
        pass

    return JsonResponse(
        {
            "success": True,
            "school_id": str(school.id),
            "scope": scope,
            "scanned": scanned,
            "embedded": embedded,
            "skipped": skipped,
            "dry_run": dry_run,
        }
    )
