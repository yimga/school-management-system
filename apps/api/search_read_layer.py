"""
Search read layer: OpenSearch when configured, else None (caller uses DB).
Single entry point for optional OpenSearch; no direct OpenSearch imports in callers.
See docs/architecture/storage_and_search.md.
"""
from __future__ import annotations

import logging
from typing import Any, Optional

from django.conf import settings

logger = logging.getLogger(__name__)

OPENSEARCH_DSN = getattr(settings, "OPENSEARCH_DSN", None) or None
OPENSEARCH_SEARCH_FAILURES = (
    AttributeError,
    OSError,
    RuntimeError,
    TypeError,
    ValueError,
)


def search(
    q: str,
    search_type: Optional[str] = None,
    school_id: Optional[Any] = None,
    limit: int = 20,
) -> Optional[dict[str, Any]]:
    """
    If OpenSearch is configured, run search and return {query, count, results}; else return None.
    Caller (e.g. GlobalSearchAPI) should use DB when None is returned.
    """
    if not OPENSEARCH_DSN:
        return None
    if not _opensearch_available():
        return None
    try:
        return _search_opensearch(q, search_type=search_type, school_id=school_id, limit=limit)
    except OPENSEARCH_SEARCH_FAILURES as e:
        logger.warning("OpenSearch search failed: %s", e)
        return None


def _opensearch_available() -> bool:
    try:
        import opensearchpy  # noqa: F401
        return True
    except ImportError:
        return False


def _search_opensearch(
    q: str,
    search_type: Optional[str] = None,
    school_id: Optional[Any] = None,
    limit: int = 20,
) -> dict[str, Any]:
    from opensearchpy import OpenSearch
    client = OpenSearch(hosts=[OPENSEARCH_DSN], use_ssl=OPENSEARCH_DSN.startswith("https"))
    body = {"query": {"multi_match": {"query": q, "fields": ["*"]}}, "size": limit}
    if school_id:
        body["query"] = {"bool": {"must": [{"term": {"school_id": str(school_id)}}, body["query"]]}}
    res = client.search(index="runmycampus-search", body=body)
    hits = res.get("hits", {}).get("hits", [])
    results = [h.get("_source", {}) for h in hits]
    return {"query": q, "count": len(results), "results": results}
