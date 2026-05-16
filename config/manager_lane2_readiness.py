"""
Lane-2 readiness surface.

Consumes the 3 SOT registers (PSP adapters, SOC2 controls, pilots) and
renders an operator dashboard showing platform readiness for external
commercial work. Single page, three sections, each a table with status
counts.

Closes the master-prompt residual "External PSP/SOC2/pilots — Lane 2" by
giving the operator a single internal scoreboard. The actual external work
still happens off-platform — but the operator can no longer be surprised
about which PSPs are certified, which SOC2 controls have evidence, or which
pilots are blocked.
"""

from __future__ import annotations

from django.shortcuts import render
from django.urls import NoReverseMatch, reverse
from django.views.decorators.http import require_GET


@require_GET
def manager_lane2_readiness(request):
    from apps.schools.control_plane import user_has_control_plane_access
    from django.http import HttpResponseForbidden

    if not user_has_control_plane_access(getattr(request, "user", None)):
        return HttpResponseForbidden("Operator access required.")

    from apps.billing.psp_adapter_registry import iter_psps, status_counts as psp_counts
    from apps.compliance.soc2_control_register import (
        iter_controls,
        status_counts as soc2_counts,
    )
    from apps.sales.pilot_register import iter_pilots, stage_counts

    psps = [p.to_dict() for p in iter_psps()]
    soc2_rows = []
    for c in iter_controls():
        d = c.to_dict()
        d["evidence_url"] = None
        if c.evidence_route_name:
            try:
                d["evidence_url"] = reverse(c.evidence_route_name)
            except NoReverseMatch:
                d["evidence_url"] = None
        soc2_rows.append(d)
    pilots = [p.to_dict() for p in iter_pilots()]

    return render(
        request,
        "schools/manager_lane2_readiness.html",
        {
            "psps": psps,
            "psp_counts": psp_counts(),
            "soc2_rows": soc2_rows,
            "soc2_counts": soc2_counts(),
            "pilots": pilots,
            "pilot_counts": stage_counts(),
        },
    )
