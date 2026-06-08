"""Semantic search over student records (Wave 5).

Wraps the existing `siteconfig.AIEmbeddingStore` with two operations:

  * `index_student(student)` — computes an embedding for the student's
    summary card (name + grade + recent risk + recent grade outlook)
    and upserts into AIEmbeddingStore with scope='student' and
    metadata={'student_id': str, 'school_id': str}.
  * `search_students(query, school_id, top_k)` — embeds the query,
    cosine-scans the stored embeddings (scope='student',
    school_id=school_id), returns ranked (student_id, score) list.

The embedding store sits in the public schema so the school_id is
stored as a UUID column we filter on directly. We do NOT join to the
StudentProfile table inside the search call — the caller does that
after ranking so tenant isolation is enforced on the caller side too.

A note on PGVector: the existing migration uses JSONField for
embeddings (works without pgvector). When pgvector is installed,
switch the field to `VectorField(dimensions=N)` and replace the
Python cosine loop with `<-> ` distance ordering. The function
contract here doesn't change.
"""

from __future__ import annotations

import hashlib
import logging
import math
import uuid
from typing import Any

from django.conf import settings
from django.db import connection
from django.db.models import Q
from django.utils import timezone

from services.embeddings import embedding_provider_descriptor, get_embedding_provider

logger = logging.getLogger("apps.analytics.semantic_search")

_STUDENT_SCOPE = "student"


def _pgvector_enabled() -> bool:
    """Wave 9: gated on operator setting + Postgres + extension present.

    Defaults to False so existing JSON path stays the contract. Operator
    flips after running `migrate_embeddings_to_pgvector`.
    """
    return (
        bool(getattr(settings, "PGVECTOR_ENABLED", False))
        and connection.vendor == "postgresql"
    )


def _pgvector_search(
    q_vec: list[float], *, school_id, top_k: int, embedding_model: str = "",
) -> list[dict]:
    """Cosine-rank via pgvector `<=>` operator. Returns up to top_k rows.

    Uses raw SQL because the JSONField column and the vector column
    coexist during/after migration; the manager doesn't know about
    `embedding_vec` (the migration is operator-applied via mgmt
    command, not in the Django chain).
    """
    placeholder = "[" + ",".join(f"{float(x):.8f}" for x in q_vec) + "]"
    with connection.cursor() as cur:
        cur.execute(
            """
            SELECT metadata, 1.0 - (embedding_vec <=> %s::vector) AS score
            FROM siteconfig_aiembeddingstore
            WHERE scope = %s
              AND school_id = %s
              AND lifecycle_status = 'active'
              AND (retention_until IS NULL OR retention_until > CURRENT_TIMESTAMP)
              AND (embedding_model = '' OR embedding_model = %s)
              AND embedding_vec IS NOT NULL
            ORDER BY embedding_vec <=> %s::vector
            LIMIT %s
            """,
            [
                placeholder,
                _STUDENT_SCOPE,
                str(school_id),
                embedding_model,
                placeholder,
                top_k,
            ],
        )
        rows = cur.fetchall()
    ranked = []
    for metadata, score in rows:
        if isinstance(metadata, str):
            import json as _json
            try:
                metadata = _json.loads(metadata)
            except (TypeError, ValueError):
                metadata = {}
        ranked.append({
            "student_id": (metadata or {}).get("student_id"),
            "score": float(score),
            "summary": (metadata or {}).get("summary", ""),
        })
    return ranked


def _summarise_student(student) -> str:
    """Build the text representation we embed.

    Includes only stable, low-PII attributes — name + grade level +
    classroom + recent risk score / band. The embedding sits in a
    public schema so we avoid sensitive PII (DOB, phone, etc.) by
    construction; an embedding leak of a name+grade is far less
    damaging than a leak of full PII.
    """
    parts: list[str] = []
    full_name = f"{student.first_name} {student.last_name}".strip()
    if full_name:
        parts.append(f"{full_name}. Student")
    classroom = getattr(student, "classroom", None)
    if classroom is not None and getattr(classroom, "name", None):
        parts.append(f"class {classroom.name}")
    code = getattr(student, "student_code", None)
    if code:
        parts.append(f"code {code}")
    # Recent risk band (cheap join — single row per student).
    try:
        latest_rf = student.risk_factors.order_by("-computed_at").first()
        if latest_rf is not None:
            parts.append(
                f"recent risk score {float(latest_rf.score):.1f} band {latest_rf.band}"
            )
    except (AttributeError, ValueError):
        pass
    return ". ".join(parts) + "." if parts else f"Student {student.pk}"


def index_student(student) -> bool:
    """Compute + upsert the embedding for one student. Returns True
    on success, False otherwise (network / provider unavailable)."""
    from apps.siteconfig.models import AIEmbeddingStore

    text = _summarise_student(student)
    if not text:
        return False
    provider = get_embedding_provider()
    embedding = provider.embed(text)
    if not embedding:
        return False
    text_hash = hashlib.sha256(text.encode("utf-8")).hexdigest()
    school_id = getattr(student, "school_id", None)
    # tenant-isolation-allow: AIEmbeddingStore is platform-wide by design; school_id stored as the partition column.
    AIEmbeddingStore.objects.update_or_create(
        scope=_STUDENT_SCOPE,
        school_id=school_id,
        text_hash=text_hash,
        defaults={
            "embedding": embedding,
            "embedding_model": embedding_provider_descriptor(provider),
            "embedding_dimensions": len(embedding),
            "document_id": f"student:{student.pk}",
            "lifecycle_status": "active",
            "retention_until": None,
            "source_updated_at": timezone.now(),
            "metadata": {
                "student_id": str(student.pk),
                "school_id": str(school_id) if school_id else "",
                "summary": text[:500],
            },
        },
    )
    return True


def _cosine(a: list[float], b: list[float]) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a)) or 1.0
    nb = math.sqrt(sum(y * y for y in b)) or 1.0
    return dot / (na * nb)


def search_students(
    query: str, *, school_id: Any, top_k: int = 10,
) -> list[dict]:
    """Rank stored student embeddings by cosine similarity to `query`.

    Returns up to `top_k` items: `[{student_id, score, summary}, ...]`.
    Empty list when embedding fails or no rows exist for the school.
    """
    from apps.siteconfig.models import AIEmbeddingStore

    provider = get_embedding_provider()
    q_vec = provider.embed(query)
    if not q_vec:
        return []
    # Wave 9: pgvector path when extension is enabled — O(log n) index scan
    # instead of O(n) Python cosine loop.
    if _pgvector_enabled():
        try:
            return _pgvector_search(
                q_vec,
                school_id=school_id,
                top_k=top_k,
                embedding_model=embedding_provider_descriptor(provider),
            )
        except Exception as exc:  # noqa: BLE001 — fall back to JSON path on any DB error
            logger.warning(
                "semantic_search: pgvector path failed (%s); falling back to JSON.",
                exc,
            )
    try:
        school_id = uuid.UUID(str(school_id))
    except (TypeError, ValueError, AttributeError):
        return []
    # tenant-isolation-allow: AIEmbeddingStore filtered by school_id below — explicit single-tenant scope.
    model_id = embedding_provider_descriptor(provider)
    rows = AIEmbeddingStore.objects.filter(
        scope=_STUDENT_SCOPE, school_id=school_id,
        lifecycle_status="active",
    ).filter(
        Q(retention_until__isnull=True) | Q(retention_until__gt=timezone.now())
    ).filter(
        Q(embedding_model="") | Q(embedding_model=model_id)
    ).values("embedding", "metadata")
    ranked = []
    for row in rows:
        stored_vector = row.get("embedding") or []
        if not stored_vector or len(stored_vector) != len(q_vec):
            continue
        score = _cosine(q_vec, stored_vector)
        if score < 0:
            continue
        meta = row.get("metadata") or {}
        ranked.append({
            "student_id": meta.get("student_id"),
            "score": score,
            "summary": meta.get("summary", ""),
        })
    ranked.sort(key=lambda r: r["score"], reverse=True)
    return ranked[:max(0, top_k)]
