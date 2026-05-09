"""CSP violation report endpoint.

Browsers POST a CSP violation report (per the Report-Only header's
``report-uri``) when a directive fires. This view ingests + logs each report
so operators can shrink the policy over time.

The endpoint is intentionally:

- CSRF-exempt (browsers don't send our CSRF cookie on a CSP report POST)
- Rate-limited (a single tab refresh can generate many reports)
- Body-size-capped (drop reports > 64 KiB to avoid log spam)
- PII-free in the log line (only directive + blocked-uri + document-uri)
"""

from __future__ import annotations

import json
import logging

from django.http import HttpResponse, HttpResponseBadRequest
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from apps.security.rate_limit import rate_limit


logger = logging.getLogger(__name__)


_MAX_BODY_BYTES = 64 * 1024


@csrf_exempt
@require_POST
@rate_limit(scope="csp_report", limit=200, window_seconds=60)
def csp_violation_report(request):
    """Receive a CSP violation report. Always returns 204 No Content on success."""
    body = (request.body or b"")[:_MAX_BODY_BYTES]
    try:
        payload = json.loads(body.decode("utf-8", errors="replace") or "{}")
    except (json.JSONDecodeError, ValueError):
        return HttpResponseBadRequest("invalid JSON")

    # Browsers wrap the report under "csp-report" (legacy) or send it directly
    # for Reporting API. Normalise both.
    report = payload.get("csp-report") if isinstance(payload, dict) else None
    if not isinstance(report, dict):
        report = payload if isinstance(payload, dict) else {}

    directive = str(report.get("violated-directive") or report.get("effective-directive") or "")[:120]
    blocked = str(report.get("blocked-uri") or "")[:200]
    doc_uri = str(report.get("document-uri") or "")[:200]
    src_file = str(report.get("source-file") or "")[:200]
    line_no = report.get("line-number") or 0

    logger.warning(
        "csp_violation directive=%s blocked=%s doc=%s src=%s line=%s",
        directive,
        blocked,
        doc_uri,
        src_file,
        line_no,
    )
    return HttpResponse(status=204)
