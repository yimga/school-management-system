"""Stdlib HTTPS helpers for payment gateway adapters (charge / status probes)."""

from __future__ import annotations

import json
from typing import Any


def http_post_json(
    url: str,
    headers: dict[str, str],
    payload: dict[str, Any],
    *,
    timeout: float = 12.0,
) -> tuple[int, dict[str, Any] | None]:
    """POST JSON body; returns (status_code, parsed_json_or_None). Never logs secrets."""
    import urllib.error
    import urllib.request

    body = json.dumps(payload).encode("utf-8")
    req_headers = {"Content-Type": "application/json", **headers}
    req = urllib.request.Request(url, data=body, headers=req_headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310
            status = int(getattr(resp, "status", 0) or resp.getcode() or 0)
            raw = resp.read(65536) or b""
            try:
                parsed = json.loads(raw.decode("utf-8", errors="replace") or "{}")
            except json.JSONDecodeError:
                parsed = None
            return status, parsed if isinstance(parsed, dict) else None
    except urllib.error.HTTPError as exc:
        raw = exc.read(65536) if hasattr(exc, "read") else b""
        try:
            parsed = json.loads(raw.decode("utf-8", errors="replace") or "{}")
        except json.JSONDecodeError:
            parsed = None
        return int(getattr(exc, "code", 0) or 0), parsed if isinstance(parsed, dict) else None
    except Exception:
        return 0, None


def http_get_json(
    url: str,
    headers: dict[str, str],
    *,
    timeout: float = 12.0,
) -> tuple[int, dict[str, Any] | None]:
    """GET JSON response; returns (status_code, parsed_json_or_None)."""
    import urllib.error
    import urllib.request

    req = urllib.request.Request(url, headers=headers, method="GET")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310
            status = int(getattr(resp, "status", 0) or resp.getcode() or 0)
            raw = resp.read(65536) or b""
            try:
                parsed = json.loads(raw.decode("utf-8", errors="replace") or "{}")
            except json.JSONDecodeError:
                parsed = None
            return status, parsed if isinstance(parsed, dict) else None
    except urllib.error.HTTPError as exc:
        return int(getattr(exc, "code", 0) or 0), None
    except Exception:
        return 0, None
