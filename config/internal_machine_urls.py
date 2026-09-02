"""Token-authed MACHINE endpoints that every deployment-served urlconf must mount.

WHY THIS MODULE EXISTS
----------------------
``/api/internal/cron/run/`` is the ONLY thing that runs the 26 ``auto_eligible=False``
jobs in ``apps.platform_runtime.periodic``: the ``/health/`` tick deliberately runs
``auto_only=True``, so heavy / financial / tenant-fan-out work never touches the
request-serving hot thread. That makes the route the trigger for the entire
cron-only half of the registry.

It was declared inline in ``config/urls.py`` and ``config/manager_urls.py`` and
NOWHERE else. ``UrlConfSwitcherMiddleware`` (apps/schools/middleware.py) routes by
Host, so the route was absent from every urlconf a real deployment serves:

  * ``config.tenant_urls``  — every tenant subdomain AND **every sovereign box**
    (``is_sovereign_single_tenant_box()`` routes a box here explicitly)
  * ``config.public_urls``  — the canonical base domain
  * ``config.api_urls``     — the api host

A missing route and a missing token are the SAME response by design (the view
returns 404 when ``INTERNAL_CRON_TOKEN`` is unset, "indistinguishable from no such
URL"), so on a box the operator saw 404, concluded the secret was not provisioned,
set it, saw 404 again, and had no next move. Nothing ran either way.

Mounting the machine endpoints from ONE list that every urlconf splats is the fix
AND the seal: a future machine endpoint added here reaches every deployment at
once, and it cannot be added to two urlconfs and forgotten on the other three.
``apps/platform_runtime/tests/test_cron_trigger_reachability_2026_09_02.py``
asserts the route resolves on all five.

Security posture is unchanged by widening the mount. The view is fail-closed on
its own: it 404s unless ``INTERNAL_CRON_TOKEN`` is at least ``MIN_TOKEN_LEN``
chars, constant-time compares the presented secret, and rate-limits per IP.
Reachability is not authorization.
"""
from __future__ import annotations

from django.urls import path

from apps.platform_runtime.views_internal_cron import internal_cron_run

#: Splatted into every deployment-served urlconf. Keep this list tiny: it is for
#: token-authed machine endpoints that must not depend on which Host answered.
INTERNAL_MACHINE_URLPATTERNS = [
    path(  # rbac-allow: machine endpoint authed by INTERNAL_CRON_TOKEN shared secret (constant-time)
        "api/internal/cron/run/",
        internal_cron_run,
        name="internal_cron_run",
    ),
]

#: Every urlconf that a deployment can actually serve. The reachability test walks
#: this so a NEW urlconf cannot quietly ship without the machine endpoints.
DEPLOYMENT_SERVED_URLCONFS = (
    "config.urls",
    "config.manager_urls",
    "config.public_urls",
    "config.tenant_urls",
    "config.api_urls",
)
