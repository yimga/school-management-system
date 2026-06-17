"""Dashboard context processors.

``first_run_zero_state`` exposes a per-role first-run welcome card to every
template. It is populated ONLY on a role-home landing while the tenant is still
in first-run (see ``first_run_zero_state.build_first_run_zero_state``); on every
other request it returns ``{}`` so the global cost is a couple of getattrs.
"""

from __future__ import annotations


def first_run_zero_state(request):
    """Inject ``first_run_zero_state`` (a render-ready card) when applicable."""
    try:
        from apps.dashboard.first_run_zero_state import build_first_run_zero_state

        payload = build_first_run_zero_state(request)
    except Exception:  # noqa: BLE001 — a context processor must never break rendering
        return {}
    return {"first_run_zero_state": payload} if payload else {}
