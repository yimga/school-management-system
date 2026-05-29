"""v4.00.45 — LMS connector adapter SOT (Wedge 2 item — Canvas / Moodle / Google Classroom).

Stdlib-only adapters that wrap each LMS's REST API behind a normalized
shape so RunMyCampus can list courses, list assignments, and push
grades regardless of upstream vendor.

Adapter contract
----------------
Each adapter exposes three callables:

    list_courses(token, base_url, *, limit=100) -> list[dict]
        Returns ``[{"id", "name", "code", "term"}]``.

    list_assignments(course_id, token, base_url, *, limit=100) -> list[dict]
        Returns ``[{"id", "name", "due", "points_possible"}]``.

    push_grade(course_id, assignment_id, user_id, score, token, base_url) -> dict
        Returns ``{"ok": bool, "status_code": int, "detail": str}``.

Stdlib HTTP (``urllib.request``) keeps the adapter free of new deps. All
adapters: 8s timeout, ``Authorization: Bearer <token>`` (Canvas/Google)
or ``Authorization: <token>`` (Moodle wstoken). Failures surface as
``{"error": "<reason>"}`` items inside the result, never as raised
exceptions — callers can show a partial result.
"""
from __future__ import annotations

import json
import logging
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

logger = logging.getLogger(__name__)

_TIMEOUT = 8.0


def _err_text(data: Any, code: int) -> str:
    """Normalize an error blob from any of the 3 LMS APIs to a flat string."""
    if isinstance(data, dict):
        err = data.get("error")
        if isinstance(err, dict):
            return err.get("message", "") or f"http_{code}"
        if isinstance(err, str):
            return err
    return f"http_{code}"


def _http_post_form(url: str, payload: dict[str, str]) -> tuple[int, Any]:
    """POST application/x-www-form-urlencoded — used by OAuth2 token endpoints."""
    data = urllib.parse.urlencode(payload).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        headers={"Content-Type": "application/x-www-form-urlencoded", "Accept": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=_TIMEOUT) as resp:  # noqa: S310 — trusted OAuth2 token endpoint
            body = resp.read().decode("utf-8", errors="replace")
            try:
                return resp.status, json.loads(body) if body else {}
            except (ValueError, TypeError):
                return resp.status, {"raw": body}
    except urllib.error.HTTPError as exc:
        try:
            body = exc.read().decode("utf-8", errors="replace")
            return exc.code, json.loads(body) if body else {"error": f"http_{exc.code}"}
        except Exception:  # noqa: BLE001
            return exc.code, {"error": f"http_{exc.code}"}
    except urllib.error.URLError as exc:
        return 0, {"error": f"urlopen_failed: {exc.reason}"}


# ---------------------------------------------------------------------------
# OAuth2 token-refresh helpers — Canvas + Google. Moodle uses wstoken (no refresh).
# ---------------------------------------------------------------------------

def canvas_refresh_token(refresh_token: str, client_id: str, client_secret: str, base_url: str) -> dict[str, Any]:
    """Canvas Instructure OAuth2 refresh.

    Returns ``{"ok", "access_token", "expires_in", "scope", "raw"}``.
    On failure: ``{"ok": False, "status_code": ..., "detail": ...}``.
    """
    if not refresh_token:
        return {"ok": False, "status_code": 400, "detail": "missing_refresh_token"}
    code, data = _http_post_form(
        f"{base_url.rstrip('/')}/login/oauth2/token",
        {
            "grant_type": "refresh_token",
            "refresh_token": refresh_token,
            "client_id": client_id,
            "client_secret": client_secret,
        },
    )
    if 200 <= code < 300 and isinstance(data, dict) and data.get("access_token"):
        return {
            "ok": True,
            "status_code": code,
            "access_token": data.get("access_token", ""),
            "expires_in": int(data.get("expires_in") or 0),
            "scope": data.get("scope") or "",
            "raw": data,
        }
    return {"ok": False, "status_code": code, "detail": _err_text(data, code)}


def google_refresh_token(refresh_token: str, client_id: str, client_secret: str) -> dict[str, Any]:
    """Google OAuth2 refresh."""
    if not refresh_token:
        return {"ok": False, "status_code": 400, "detail": "missing_refresh_token"}
    code, data = _http_post_form(
        "https://oauth2.googleapis.com/token",
        {
            "grant_type": "refresh_token",
            "refresh_token": refresh_token,
            "client_id": client_id,
            "client_secret": client_secret,
        },
    )
    if 200 <= code < 300 and isinstance(data, dict) and data.get("access_token"):
        return {
            "ok": True,
            "status_code": code,
            "access_token": data.get("access_token", ""),
            "expires_in": int(data.get("expires_in") or 0),
            "scope": data.get("scope") or "",
            "raw": data,
        }
    return {"ok": False, "status_code": code, "detail": _err_text(data, code)}


def refresh_token(provider: str, **kwargs: Any) -> dict[str, Any]:
    """Dispatch helper. Moodle returns "unsupported" — wstoken doesn't expire."""
    if provider == "canvas":
        return canvas_refresh_token(**kwargs)
    if provider == "google_classroom":
        return google_refresh_token(**kwargs)
    if provider == "moodle":
        return {"ok": False, "status_code": 501, "detail": "moodle_wstoken_no_refresh"}
    return {"ok": False, "status_code": 404, "detail": f"unknown_provider: {provider}"}


def _http_get_json(url: str, headers: dict[str, str]) -> tuple[int, Any]:
    req = urllib.request.Request(url, headers=headers, method="GET")
    try:
        with urllib.request.urlopen(req, timeout=_TIMEOUT) as resp:  # noqa: S310 — trusted LMS REST endpoint
            body = resp.read().decode("utf-8", errors="replace")
            try:
                return resp.status, json.loads(body) if body else {}
            except (ValueError, TypeError):
                return resp.status, {"raw": body}
    except urllib.error.HTTPError as exc:
        return exc.code, {"error": f"http_{exc.code}"}
    except urllib.error.URLError as exc:
        return 0, {"error": f"urlopen_failed: {exc.reason}"}


def _http_post_json(url: str, headers: dict[str, str], payload: dict[str, Any] | None) -> tuple[int, Any]:
    data = json.dumps(payload or {}).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers={**headers, "Content-Type": "application/json"}, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=_TIMEOUT) as resp:  # noqa: S310 — trusted LMS REST endpoint
            body = resp.read().decode("utf-8", errors="replace")
            try:
                return resp.status, json.loads(body) if body else {}
            except (ValueError, TypeError):
                return resp.status, {"raw": body}
    except urllib.error.HTTPError as exc:
        return exc.code, {"error": f"http_{exc.code}"}
    except urllib.error.URLError as exc:
        return 0, {"error": f"urlopen_failed: {exc.reason}"}


# ---------------------------------------------------------------------------
# Canvas LMS adapter — REST API v1.
# ---------------------------------------------------------------------------

def canvas_list_courses(token: str, base_url: str, *, limit: int = 100) -> list[dict[str, Any]]:
    headers = {"Authorization": f"Bearer {token}", "Accept": "application/json+canvas-string-ids"}
    url = f"{base_url.rstrip('/')}/api/v1/courses?per_page={int(limit)}&include[]=term"
    code, data = _http_get_json(url, headers)
    if code != 200 or not isinstance(data, list):
        return [{"error": (data or {}).get("error", f"http_{code}")}]
    out = []
    for c in data:
        out.append({
            "id": str(c.get("id", "")),
            "name": c.get("name", ""),
            "code": c.get("course_code", ""),
            "term": (c.get("term") or {}).get("name", ""),
        })
    return out


def canvas_list_assignments(course_id: str, token: str, base_url: str, *, limit: int = 100) -> list[dict[str, Any]]:
    headers = {"Authorization": f"Bearer {token}", "Accept": "application/json"}
    url = f"{base_url.rstrip('/')}/api/v1/courses/{urllib.parse.quote(str(course_id))}/assignments?per_page={int(limit)}"
    code, data = _http_get_json(url, headers)
    if code != 200 or not isinstance(data, list):
        return [{"error": (data or {}).get("error", f"http_{code}")}]
    out = []
    for a in data:
        out.append({
            "id": str(a.get("id", "")),
            "name": a.get("name", ""),
            "due": a.get("due_at", ""),
            "points_possible": a.get("points_possible", 0),
        })
    return out


def canvas_push_grade(course_id: str, assignment_id: str, user_id: str, score: float, token: str, base_url: str) -> dict[str, Any]:
    headers = {"Authorization": f"Bearer {token}", "Accept": "application/json"}
    url = (
        f"{base_url.rstrip('/')}/api/v1/courses/{urllib.parse.quote(str(course_id))}"
        f"/assignments/{urllib.parse.quote(str(assignment_id))}/submissions/{urllib.parse.quote(str(user_id))}"
    )
    code, data = _http_put_json(url, headers, {"submission": {"posted_grade": float(score)}})  # money-float-allow: lms-score-not-money
    return {"ok": 200 <= code < 300, "status_code": code, "detail": (data or {}).get("error", "")}


# ---------------------------------------------------------------------------
# Moodle adapter — Web Service REST endpoint (wstoken).
# ---------------------------------------------------------------------------

def _moodle_call(base_url: str, token: str, wsfunction: str, params: dict[str, Any]) -> tuple[int, Any]:
    headers = {"Accept": "application/json"}
    qs = {"wstoken": token, "moodlewsrestformat": "json", "wsfunction": wsfunction, **params}
    url = f"{base_url.rstrip('/')}/webservice/rest/server.php?{urllib.parse.urlencode(qs)}"
    return _http_get_json(url, headers)


def moodle_list_courses(token: str, base_url: str, *, limit: int = 100) -> list[dict[str, Any]]:
    code, data = _moodle_call(base_url, token, "core_course_get_courses", {})
    if code != 200 or not isinstance(data, list):
        return [{"error": (data or {}).get("error", f"http_{code}")}]
    out = []
    for c in data[: int(limit)]:
        out.append({
            "id": str(c.get("id", "")),
            "name": c.get("fullname", ""),
            "code": c.get("shortname", ""),
            "term": "",
        })
    return out


def moodle_list_assignments(course_id: str, token: str, base_url: str, *, limit: int = 100) -> list[dict[str, Any]]:
    code, data = _moodle_call(base_url, token, "mod_assign_get_assignments", {"courseids[0]": str(course_id)})
    if code != 200 or not isinstance(data, dict):
        return [{"error": (data or {}).get("error", f"http_{code}")}]
    out = []
    for course in data.get("courses", []):
        for a in course.get("assignments", [])[: int(limit)]:
            out.append({
                "id": str(a.get("id", "")),
                "name": a.get("name", ""),
                "due": a.get("duedate", ""),
                "points_possible": a.get("grade", 0),
            })
    return out


def moodle_push_grade(course_id: str, assignment_id: str, user_id: str, score: float, token: str, base_url: str) -> dict[str, Any]:
    qs = {
        "assignmentid": str(assignment_id),
        "userid": str(user_id),
        "grade": str(float(score)),  # money-float-allow: lms-score-not-money
        "attemptnumber": "-1",
        "addattempt": "0",
        "workflowstate": "graded",
        "applytoall": "1",
    }
    code, data = _moodle_call(base_url, token, "mod_assign_save_grade", qs)
    return {"ok": 200 <= code < 300, "status_code": code, "detail": (data or {}).get("error", "")}


# ---------------------------------------------------------------------------
# Google Classroom adapter — Classroom REST v1.
# ---------------------------------------------------------------------------

def google_list_courses(token: str, base_url: str = "", *, limit: int = 100) -> list[dict[str, Any]]:
    headers = {"Authorization": f"Bearer {token}", "Accept": "application/json"}
    url = f"https://classroom.googleapis.com/v1/courses?pageSize={int(limit)}"
    code, data = _http_get_json(url, headers)
    if code != 200 or not isinstance(data, dict):
        return [{"error": _err_text(data, code)}]
    out = []
    for c in data.get("courses", []):
        out.append({
            "id": str(c.get("id", "")),
            "name": c.get("name", ""),
            "code": c.get("section", ""),
            "term": c.get("descriptionHeading", ""),
        })
    return out


def google_list_assignments(course_id: str, token: str, base_url: str = "", *, limit: int = 100) -> list[dict[str, Any]]:
    headers = {"Authorization": f"Bearer {token}", "Accept": "application/json"}
    url = (
        f"https://classroom.googleapis.com/v1/courses/{urllib.parse.quote(str(course_id))}"
        f"/courseWork?pageSize={int(limit)}"
    )
    code, data = _http_get_json(url, headers)
    if code != 200 or not isinstance(data, dict):
        return [{"error": _err_text(data, code)}]
    out = []
    for a in data.get("courseWork", []):
        due = a.get("dueDate") or {}
        due_str = "-".join(str(x) for x in [due.get("year"), due.get("month"), due.get("day")] if x is not None) if due else ""
        out.append({
            "id": str(a.get("id", "")),
            "name": a.get("title", ""),
            "due": due_str,
            "points_possible": a.get("maxPoints", 0),
        })
    return out


def google_push_grade(course_id: str, assignment_id: str, user_id: str, score: float, token: str, base_url: str = "") -> dict[str, Any]:
    headers = {"Authorization": f"Bearer {token}", "Accept": "application/json"}
    # Google Classroom requires finding the student-submission by user, then PATCH.
    list_url = (
        f"https://classroom.googleapis.com/v1/courses/{urllib.parse.quote(str(course_id))}"
        f"/courseWork/{urllib.parse.quote(str(assignment_id))}/studentSubmissions?userId={urllib.parse.quote(str(user_id))}"
    )
    code, data = _http_get_json(list_url, headers)
    if code != 200 or not isinstance(data, dict):
        return {"ok": False, "status_code": code, "detail": "list_submissions_failed"}
    submissions = data.get("studentSubmissions") or []
    if not submissions:
        return {"ok": False, "status_code": 404, "detail": "submission_not_found"}
    sub_id = submissions[0].get("id", "")
    patch_url = (
        f"https://classroom.googleapis.com/v1/courses/{urllib.parse.quote(str(course_id))}"
        f"/courseWork/{urllib.parse.quote(str(assignment_id))}/studentSubmissions/{urllib.parse.quote(str(sub_id))}"
        "?updateMask=assignedGrade,draftGrade"
    )
    code2, data2 = _http_patch_json(
        patch_url,
        headers,
        {"assignedGrade": float(score), "draftGrade": float(score)},  # money-float-allow: lms-score-not-money
    )
    return {"ok": 200 <= code2 < 300, "status_code": code2, "detail": (data2 or {}).get("error", {}).get("message", "")}


# ---------------------------------------------------------------------------
# Shared HTTP helpers — PUT + PATCH (urllib doesn't expose them directly).
# ---------------------------------------------------------------------------

def _http_put_json(url: str, headers: dict[str, str], payload: dict[str, Any] | None) -> tuple[int, Any]:
    data = json.dumps(payload or {}).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers={**headers, "Content-Type": "application/json"}, method="PUT")
    try:
        with urllib.request.urlopen(req, timeout=_TIMEOUT) as resp:  # noqa: S310 — trusted LMS REST endpoint
            body = resp.read().decode("utf-8", errors="replace")
            try:
                return resp.status, json.loads(body) if body else {}
            except (ValueError, TypeError):
                return resp.status, {"raw": body}
    except urllib.error.HTTPError as exc:
        return exc.code, {"error": f"http_{exc.code}"}
    except urllib.error.URLError as exc:
        return 0, {"error": f"urlopen_failed: {exc.reason}"}


def _http_patch_json(url: str, headers: dict[str, str], payload: dict[str, Any] | None) -> tuple[int, Any]:
    data = json.dumps(payload or {}).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers={**headers, "Content-Type": "application/json"}, method="PATCH")
    try:
        with urllib.request.urlopen(req, timeout=_TIMEOUT) as resp:  # noqa: S310 — trusted LMS REST endpoint
            body = resp.read().decode("utf-8", errors="replace")
            try:
                return resp.status, json.loads(body) if body else {}
            except (ValueError, TypeError):
                return resp.status, {"raw": body}
    except urllib.error.HTTPError as exc:
        return exc.code, {"error": f"http_{exc.code}"}
    except urllib.error.URLError as exc:
        return 0, {"error": f"urlopen_failed: {exc.reason}"}


# ---------------------------------------------------------------------------
# Adapter dispatch
# ---------------------------------------------------------------------------

ADAPTERS: dict[str, dict[str, Any]] = {
    "canvas": {
        "list_courses": canvas_list_courses,
        "list_assignments": canvas_list_assignments,
        "push_grade": canvas_push_grade,
    },
    "moodle": {
        "list_courses": moodle_list_courses,
        "list_assignments": moodle_list_assignments,
        "push_grade": moodle_push_grade,
    },
    "google_classroom": {
        "list_courses": google_list_courses,
        "list_assignments": google_list_assignments,
        "push_grade": google_push_grade,
    },
}


def supported_providers() -> list[str]:
    return sorted(ADAPTERS.keys())


def dispatch(provider: str, op: str, **kwargs: Any) -> Any:
    """Lookup-and-call helper. Returns ``[{"error": ...}]`` on unknown provider/op."""
    p = ADAPTERS.get(provider)
    if not p:
        return [{"error": f"unknown_provider: {provider}"}]
    fn = p.get(op)
    if not fn:
        return [{"error": f"unknown_op: {op}"}]
    return fn(**kwargs)
