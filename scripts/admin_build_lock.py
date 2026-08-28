"""Shared reader for the admin approval build lock. NOT a gate -- a helper.

WHY THIS EXISTS
    Three admin gates asserted that `static/js/service-worker.js` contains an EXACT
    service-worker version string taken from `var/admin-approval-build-lock.json`
    (or, worse, from a private copy of it). CLAUDE.md's deploy checklist requires
    bumping `CACHE_VERSION` on every wave that ships CSS or JS, so those gates went
    red on every wave **by construction** -- which is precisely why none of them was
    ever wired into CI. A gate that cannot be wired is not a gate.

    The invariant they were reaching for is not equality. It is:

        the shipped service worker is at least the approved build's version

    i.e. the approved admin build is present, and later waves are allowed to ship on
    top of it. That is monotonic, so it survives the next bump, and it is the same
    question `verify_service_worker_version.py --check-monotonic` already asks
    correctly for the platform as a whole.

    Keeping the parsing here rather than copying it into each gate also means the
    lock has ONE reader. `sweep_django_admin_platformwide_layout.py` had drifted to
    its own hardcoded pins, nine days behind the lock, and nobody could see the two
    disagreeing because neither was running.

WHAT IT DELIBERATELY DOES NOT DO
    It never rewrites the lock. The lock records that a specific admin build was
    *approved*; making a gate green by editing it would assert an approval that
    nobody gave.

Stdlib only, so a deps-free boundary job can use it.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LOCK_PATH = ROOT / "var" / "admin-approval-build-lock.json"
SERVICE_WORKER = ROOT / "static" / "js" / "service-worker.js"

#: `sms-vMAJOR.MINOR.PATCH[-slug]-YYYY-MM-DD`
_SW_VERSION = re.compile(r"sms-v(\d+)\.(\d+)\.(\d+)")
_SW_DECLARATION = re.compile(r'const\s+CACHE_VERSION\s*=\s*"(?P<value>[^"]+)"\s*;')

#: A seal documents the contract a rule set implements, so it lives WITH those rules.
#: The v22 build is a tenant-sidebar build and its seal belongs in the sidebar sheet;
#: a gate that looks in only the terminal canvas file is asking the wrong file.
SEAL_SEARCH_PATHS = (
    "static/css/rmc-admin-sidebar-v3.css",
    "static/css/rmc-admin-emergency-full-canvas-v17.css",
    "static/css/rmc-admin-django-canvas-contract.css",
    "static/css/rmc-admin-approval-surface-v15.css",
)


def load() -> dict:
    return json.loads(LOCK_PATH.read_text(encoding="utf-8"))


def parse_version(text: str) -> tuple[int, int, int] | None:
    """Extract the numeric triple from a `sms-v…` string, or None."""
    match = _SW_VERSION.search(text or "")
    if not match:
        return None
    return tuple(int(part) for part in match.groups())  # type: ignore[return-value]


def shipped_version(service_worker_text: str | None = None) -> str:
    """The live `CACHE_VERSION` value, read from its declaration, not the whole file.

    Reading the declaration matters: the file's own header comments quote older
    version strings, so a substring search over the raw text can 'find' a version
    that is no longer shipping.
    """
    text = (
        service_worker_text
        if service_worker_text is not None
        else SERVICE_WORKER.read_text(encoding="utf-8")
    )
    match = _SW_DECLARATION.search(text)
    return match.group("value") if match else ""


def sw_at_least(required: str, service_worker_text: str | None = None) -> tuple[bool, str]:
    """Is the shipped service worker at least ``required``? Returns (ok, explanation)."""
    shipped = shipped_version(service_worker_text)
    if not shipped:
        return False, "CACHE_VERSION declaration not found in service-worker.js"
    want = parse_version(required)
    have = parse_version(shipped)
    if want is None:
        return False, f"approved build lock has an unparseable sw_version: {required!r}"
    if have is None:
        return False, f"shipped CACHE_VERSION is unparseable: {shipped!r}"
    if have < want:
        return (
            False,
            f"service worker {shipped} is OLDER than the approved admin build "
            f"{required} - the approved build is not shipping",
        )
    return True, f"service worker {shipped} >= approved build {required}"


def seal_present(seal: str) -> tuple[bool, str]:
    """Is the approved build's seal documented in any admin stylesheet?"""
    for relative in SEAL_SEARCH_PATHS:
        path = ROOT / relative
        if not path.is_file():
            continue
        if seal in path.read_text(encoding="utf-8", errors="replace"):
            return True, relative
    return False, ""
