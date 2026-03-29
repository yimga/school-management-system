"""
KB/FAQ context for support AI (Ollama via gateway).

Builds a short text block from published tenant-facing articles so ``support_suggest``
can ground replies in local documentation without sending full KB HTML to the model.
"""

from __future__ import annotations

import logging
import re
from typing import TYPE_CHECKING, Any

from django.conf import settings

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)

_MAX_SNIPPETS = 4
_MAX_CHARS_PER_SNIPPET = 400
_MAX_BLOCK_CHARS = 2000


def _keywords(text: str, *, limit: int = 8) -> list[str]:
    words = re.findall(r"[a-zA-Z]{3,}", (text or "").lower())
    seen: set[str] = set()
    out: list[str] = []
    for w in words:
        if w in seen:
            continue
        seen.add(w)
        out.append(w)
        if len(out) >= limit:
            break
    return out


def _tenant_schema_name(school: Any) -> str | None:
    if school is None:
        return None
    try:
        client = school.tenant_client
    except Exception:
        return None
    name = (getattr(client, "schema_name", None) or "").strip()
    return name or None


def build_kb_context_block(subject: str, body: str, school: Any) -> str:
    """
    Return a plain-text context block for the support_suggest prompt, or "".
    Requires django-tenants schema context (tenant KB lives in tenant schema).
    """
    if not getattr(settings, "SUPPORT_AI_KB_CONTEXT", True):
        return ""
    schema = _tenant_schema_name(school)
    if not schema:
        return ""
    tokens = _keywords(f"{subject} {body}")
    if not tokens:
        return ""

    try:
        from django_tenants.utils import schema_context
    except ImportError:
        return ""

    try:
        with schema_context(schema):
            from django.db.models import Q

            from apps.portal.models_kb import FAQ, HelpAudience, KBArticle

            audience_q = Q(help_audience__in=[HelpAudience.TENANT, HelpAudience.BOTH])
            token_q = Q()
            for t in tokens[:6]:
                token_q |= (
                    Q(title__icontains=t)
                    | Q(summary__icontains=t)
                    | Q(tags__icontains=t)
                )

            lines: list[str] = []
            kb_qs = (
                KBArticle.objects.filter(status="PUBLISHED")
                .filter(audience_q)
                .filter(token_q)
                .distinct()
                .order_by("-is_featured", "-view_count")[:_MAX_SNIPPETS]
            )
            for art in kb_qs:
                snippet = (art.summary or "")[:_MAX_CHARS_PER_SNIPPET].replace("\n", " ").strip()
                if snippet:
                    lines.append(f"- KB: {art.title}: {snippet}")

            faq_token_q = Q()
            for t in tokens[:6]:
                faq_token_q |= (
                    Q(question__icontains=t)
                    | Q(answer__icontains=t)
                    | Q(tags__icontains=t)
                )
            faq_qs = (
                FAQ.objects.filter(status="APPROVED")
                .filter(audience_q)
                .filter(faq_token_q)
                .distinct()
                .order_by("-view_count")[: max(0, _MAX_SNIPPETS - len(lines))]
            )
            for faq in faq_qs:
                ans = (faq.answer or "")[:_MAX_CHARS_PER_SNIPPET].replace("\n", " ").strip()
                if ans:
                    lines.append(f"- FAQ: {faq.question[:120]}: {ans}")

            if not lines:
                return ""

            block = "Relevant help excerpts (ground truth; cite when useful):\n" + "\n".join(
                lines
            )
            return block[:_MAX_BLOCK_CHARS]
    except Exception as exc:
        logger.debug("support KB context skipped: %s", exc)
        return ""
