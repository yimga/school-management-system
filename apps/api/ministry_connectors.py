"""
Ministry connector scaffolding.

Default mode is safe dry-run (`mock`). Live mode can be enabled when
credentials and official endpoints are available.
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from typing import Any


def _env(name: str) -> str:
    return (os.getenv(name) or "").strip()


def _missing(required: list[str]) -> list[str]:
    return [key for key in required if not _env(key)]


def _mode() -> str:
    value = _env("MINISTRY_CONNECTOR_MODE").lower()
    return value if value in {"mock", "live"} else "mock"


def ministry_runtime_status() -> dict[str, Any]:
    mode = _mode()
    cart_required = ["CARTESCOLAIRE_API_BASE_URL", "CARTESCOLAIRE_API_TOKEN"]
    dgi_required = ["DGI_API_BASE_URL", "DGI_CLIENT_ID", "DGI_CLIENT_SECRET"]

    cart_missing = _missing(cart_required) if mode == "live" else []
    dgi_missing = _missing(dgi_required) if mode == "live" else []

    return {
        "mode": mode,
        "cartescolaire": {
            "ready": mode == "mock" or not cart_missing,
            "missing": cart_missing,
        },
        "dgi": {
            "ready": mode == "mock" or not dgi_missing,
            "missing": dgi_missing,
        },
    }


def _post_json(
    url: str, payload: dict[str, Any], headers: dict[str, str], timeout: int = 12
) -> tuple[bool, int, dict]:
    body = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url=url, data=body, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as response:
            raw = response.read().decode("utf-8", errors="ignore")
            parsed = json.loads(raw) if raw else {}
            return True, getattr(response, "status", 200), parsed
    except urllib.error.HTTPError as exc:
        try:
            raw = exc.read().decode("utf-8", errors="ignore")
            parsed = json.loads(raw) if raw else {}
        except (ValueError, TypeError, UnicodeDecodeError, json.JSONDecodeError):
            parsed = {"detail": str(exc)}
        return False, getattr(exc, "code", 500), parsed
    except (OSError, ConnectionError, TimeoutError, ValueError, TypeError) as exc:
        return False, 500, {"detail": str(exc)}


def submit_cartescolaire(payload: dict[str, Any]) -> dict[str, Any]:
    status = ministry_runtime_status()
    mode = status["mode"]
    readiness = status["cartescolaire"]

    if mode == "mock":
        return {
            "attempted": False,
            "success": False,
            "mode": "mock",
            "message": "Dry-run mode. No external request sent.",
            "missing": [],
        }
    if not readiness["ready"]:
        return {
            "attempted": False,
            "success": False,
            "mode": "live",
            "message": "Live mode configured but credentials are incomplete.",
            "missing": readiness["missing"],
        }

    base = _env("CARTESCOLAIRE_API_BASE_URL").rstrip("/")
    path = _env("CARTESCOLAIRE_API_PATH") or "/registry/import"
    token = _env("CARTESCOLAIRE_API_TOKEN")
    url = f"{base}{path}"
    ok, code, data = _post_json(
        url=url,
        payload=payload,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {token}",
        },
    )
    return {
        "attempted": True,
        "success": ok,
        "mode": "live",
        "status_code": code,
        "response": data,
        "missing": [],
    }


def submit_dgi(payload: dict[str, Any]) -> dict[str, Any]:
    status = ministry_runtime_status()
    mode = status["mode"]
    readiness = status["dgi"]

    if mode == "mock":
        return {
            "attempted": False,
            "success": False,
            "mode": "mock",
            "message": "Dry-run mode. No external request sent.",
            "missing": [],
        }
    if not readiness["ready"]:
        return {
            "attempted": False,
            "success": False,
            "mode": "live",
            "message": "Live mode configured but credentials are incomplete.",
            "missing": readiness["missing"],
        }

    base = _env("DGI_API_BASE_URL").rstrip("/")
    path = _env("DGI_API_PATH") or "/einvoice/sync"
    client_id = _env("DGI_CLIENT_ID")
    client_secret = _env("DGI_CLIENT_SECRET")
    url = f"{base}{path}"
    ok, code, data = _post_json(
        url=url,
        payload=payload,
        headers={
            "Content-Type": "application/json",
            "X-Client-Id": client_id,
            "X-Client-Secret": client_secret,
        },
    )
    return {
        "attempted": True,
        "success": ok,
        "mode": "live",
        "status_code": code,
        "response": data,
        "missing": [],
    }
