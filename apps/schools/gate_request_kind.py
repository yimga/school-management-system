"""Shared request-kind helper for the tenant activation / conversion gates.

A gate may redirect a top-level PAGE navigation to the activation wizard, but it
must NEVER redirect a background fetch / XHR / subresource request: a ``fetch()``
that expects JSON cannot follow a 302 to an HTML wizard — it fails and the page
retries, producing a redirect STORM that 302s every data widget on the page and
leaves them hanging empty (the "tall empty void" regression observed on tenant
wizard pages, where dozens of ``/portal/...``, ``/-/version/``, copilot-rail and
offline-enqueue fetches were all redirected to ``/activation/first-action/``).

Only documents are gated.
"""

from __future__ import annotations

from typing import Any


def is_document_navigation(request: Any) -> bool:
    """True only for a top-level HTML page navigation (safe to gate-redirect).

    False for background fetch / XHR / subresource requests, which must pass
    through untouched. Detection order, most authoritative first:

    1. ``Sec-Fetch-Dest`` — modern browsers always send it. ``document`` is a
       top-level navigation; anything else (``empty`` for ``fetch()``, ``script``,
       ``style``, ``image`` …) is a subresource.
    2. ``X-Requested-With: XMLHttpRequest`` — legacy explicit XHR marker.
    3. ``Accept`` — a navigation requests ``text/html``; a fetch sends ``*/*`` or
       ``application/json``.

    Ambiguous cases bias to ``False`` (do NOT redirect) so a gate can never storm.
    """
    headers = getattr(request, "headers", None) or {}
    dest = headers.get("Sec-Fetch-Dest")
    if dest:
        return dest == "document"
    if headers.get("X-Requested-With") == "XMLHttpRequest":
        return False
    return "text/html" in (headers.get("Accept") or "")
