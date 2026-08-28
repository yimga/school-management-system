#!/usr/bin/env python3
"""Static fail-closed contract for the shared Django Admin sidebar v3.

Supersedes ``verify_operator_admin_sidebar_v2.py`` and
``verify_tenant_admin_sidebar_v2.py``, which asserted two SEPARATE per-scope
asset bundles. v3 collapses those into one owner served to both the operator and
the tenant admin shells, so the old gates could only ever fail once the assets
they policed stopped existing -- and they did, silently, in the pre-push runner
and in ``architectural-boundaries.yml``.

What this gate holds, and why each line is here rather than in a test:

* **One asset owner.** ``base_site.html`` loads exactly one v3 CSS and one v3 JS,
  and none of the four retired v2 files. Two bundles is how the operator and
  tenant sidebars drifted apart in the first place.
* **Both scopes mount the shared body.** The tenant and operator templates carry
  their own ``data-rmc-admin-sidebar-scope`` and include the same partial, so
  scope is DATA, not a forked template.
* **The concurrency contract is real.** The server does compare-and-swap under a
  row lock and answers 409; the client queues semantic OPERATIONS with a base
  revision rather than a whole-state snapshot. A snapshot is what let a stale
  offline tab overwrite newer server state.
* **The build moves together.** Cache-bust id, build id and the service-worker
  version agree, and the worker precaches the v3 assets -- otherwise a deploy
  ships new markup against a cached old bundle.
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import admin_build_lock  # noqa: E402

RETIRED_V2_ASSETS = (
    "rmc-tenant-admin-sidebar-v2.css",
    "rmc-tenant-admin-sidebar-v2.js",
    "rmc-operator-admin-sidebar-v2.css",
    "rmc-operator-admin-sidebar-v2.js",
)


def read(path: str) -> str:
    target = ROOT / path
    if not target.is_file():
        return ""
    return target.read_text(encoding="utf-8", errors="replace")


def main() -> int:
    failures: list[str] = []

    base = read("templates/admin/base_site.html")
    shell = read("templates/admin/base.html")
    tenant = read("templates/admin/sidebar_inner.html")
    operator = read("templates/partials/manager_platform_admin_sidebar.html")
    body = read("templates/admin/sidebar_v3_body.html")
    javascript = read("static/js/rmc-admin-sidebar-v3.js")
    css = read("static/css/rmc-admin-sidebar-v3.css")
    worker = read("static/js/service-worker.js")
    preferences = read("apps/siteconfig/admin_navigation_preferences.py")

    for label, source in (
        ("templates/admin/base_site.html", base),
        ("templates/admin/sidebar_inner.html", tenant),
        ("templates/partials/manager_platform_admin_sidebar.html", operator),
        ("templates/admin/sidebar_v3_body.html", body),
        ("static/js/rmc-admin-sidebar-v3.js", javascript),
        ("static/css/rmc-admin-sidebar-v3.css", css),
    ):
        if not source:
            failures.append(f"missing or empty: {label}")
    if failures:
        print("ADMIN_SIDEBAR_V3_FAIL")
        for message in failures:
            print(f"  - {message}")
        return 1

    # One asset owner for both shells.
    for asset in ("rmc-admin-sidebar-v3.css", "rmc-admin-sidebar-v3.js"):
        count = base.count(asset)
        if count != 1:
            failures.append(f"base_site.html must load {asset} exactly once (found {count})")
    for retired in RETIRED_V2_ASSETS:
        if retired in base:
            failures.append(f"retired v2 asset still loaded: {retired}")

    # Scope is data, and both scopes mount the same body.
    if 'data-rmc-admin-sidebar-scope="tenant"' not in tenant:
        failures.append("tenant sidebar does not declare its scope")
    if 'data-rmc-admin-sidebar-scope="operator"' not in operator:
        failures.append("operator sidebar does not declare its scope")
    for label, source in (("tenant", tenant), ("operator", operator)):
        if 'include "admin/sidebar_v3_body.html"' not in source:
            failures.append(f"{label} sidebar does not include the shared v3 body")

    # The information architecture the body must actually render.
    for region in (
        "data-rmc-admin-command-open",
        "data-rmc-admin-now",
        "data-rmc-admin-this-page",
        "data-rmc-admin-pinned-wrap",
        "data-rmc-admin-work-areas",
        "data-rmc-admin-recent-wrap",
        "data-rmc-admin-undo",
    ):
        if region not in body:
            failures.append(f"sidebar body is missing region: {region}")

    # Server side of the concurrency contract.
    for label, token in (
        ("row lock", "select_for_update"),
        ("transaction", "transaction.atomic"),
        ("conflict type", "NavigationRevisionConflict"),
        ("http conflict", "status=409"),
        ("idempotency", "applied_mutation_ids"),
    ):
        if token not in preferences:
            failures.append(f"preference service is missing the {label} ({token})")

    # Client side: operations with a base revision, never a whole-state snapshot.
    for label, token in (
        ("patch verb", 'method: "PATCH"'),
        ("base revision", "expected_revision"),
        ("conflict rebase", "revision_conflict"),
        ("cross-tab sync", "BroadcastChannel"),
        ("offline queue", 'addEventListener("offline"'),
        ("bounded backoff", "Math.min(30000"),
    ):
        if token not in javascript:
            failures.append(f"sidebar runtime is missing the {label} ({token})")

    # Build identity moves with the assets.
    for asset in ("/static/css/rmc-admin-sidebar-v3.css", "/static/js/rmc-admin-sidebar-v3.js"):
        if asset not in worker:
            failures.append(f"service worker does not precache {asset}")
    # Monotonic, never an exact match. A peer wave bumps CACHE_VERSION for its own
    # reasons and would otherwise "break" this gate by shipping something NEWER --
    # the same brittleness that made the v22 admin gates unwireable until 2026-08-21.
    lock = admin_build_lock.load()
    ok, explanation = admin_build_lock.sw_at_least(lock.get("sw_version", ""), worker)
    if not ok:
        failures.append(explanation)
    build_id = str(lock.get("build_id") or "")
    if not build_id or build_id not in base + shell:
        failures.append(
            f"admin shell does not carry the approved build id {build_id!r} "
            "from var/admin-approval-build-lock.json"
        )

    if failures:
        print("ADMIN_SIDEBAR_V3_FAIL")
        for message in failures:
            print(f"  - {message}")
        return 1
    print("ADMIN_SIDEBAR_V3_PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
