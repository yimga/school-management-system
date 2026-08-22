"""The operator's answer to "which school is on which release, and which one is stuck".

Before this page that question had no answer. Every box reports its manifest hash on every
handshake and the cloud compared it and dropped it; a failed upgrade went to a logfile.
`EdgeDeploymentHistory` cannot help — it is written on the BOX, in the box's own database,
behind whatever link that school has, and the cloud never sees a row of it.

So the honest way to find a stuck box was to ring the school and ask someone to read a
screen. That is not a fleet you can push updates to.

WHAT THIS PAGE IS CAREFUL ABOUT

*Seen* and *moved* are different columns. A box that checked in four minutes ago and last
changed manifest in June is perfectly healthy on the network and completely stuck on the
upgrade; collapsing those into one "last seen" would hide exactly the row an operator is
looking for.

*Waiting* is not *stuck*. A school on `stable` that has simply not been promoted to yet is
behaving correctly, and showing it in the same colour as a box that tried and failed would
teach an operator to ignore the colour. The rollout ring is read for every row so the page
can tell the two apart and say which it is.

Read-only. Promotion happens through `manage.py ota_rollout`, deliberately: a button that
releases a build to every school in the fleet is a button that gets clicked by accident,
and this page's job is to be the thing you read BEFORE you decide.
"""
from __future__ import annotations

from django.shortcuts import render
from django.utils import timezone
from django.utils.translation import gettext as _

from apps.schools.control_plane import require_control_plane_access

# A box is "quiet" once it has missed enough cycles that silence is itself the finding.
# Generous on purpose: an edge box is expected to be offline, and a page that cries about
# every school with a bad afternoon is a page nobody reads.
_QUIET_AFTER_HOURS = 24  # magic-number-allow: hours of silence before a box reads as quiet


def _state_for(row, ring, paused, allowed, reason, operator_hash, now):
    """Classify one school into exactly one honest state.

    Order matters: a failure outranks drift, because a box that TRIED and stopped is a
    different problem from one that has not been offered anything yet.
    """
    if row is None or not row.last_seen_at:
        return "never", _("Never checked in")
    quiet = (now - row.last_seen_at).total_seconds() > _QUIET_AFTER_HOURS * 3600
    if row.last_failure_text:
        return "failed", _("Upgrade failed on the box")
    if paused:
        return "paused", _("Held back by an operator")
    if operator_hash and row.reported_manifest_hash == operator_hash:
        return "quiet" if quiet else "parity", (
            _("Quiet, but on the current release") if quiet else _("On the current release")
        )
    if not allowed:
        # Behind on purpose. This is the working state of a staged rollout, not a fault.
        return "waiting", reason
    return "quiet" if quiet else "behind", (
        _("Quiet, and behind") if quiet else _("Behind — released, not yet applied")
    )


@require_control_plane_access
def edge_fleet_console(request, **kwargs):
    """Every box, what it is on, and whether that is a problem."""
    from apps.schools.models import School
    from apps.sync_engine.models_fleet import EdgeFleetState
    from apps.sync_engine.models_rollout import (
        EdgeRolloutPolicy,
        ManifestRelease,
        default_release_rings,
        may_receive,
    )
    from apps.sync_engine.system_manifest import load_manifest

    manifest = load_manifest() or {}
    operator_hash = str(manifest.get("manifest_hash") or "")
    now = timezone.now()

    states = {s.school_id: s for s in EdgeFleetState.objects.all()}
    policies = {p.school_id: p for p in EdgeRolloutPolicy.objects.all()}
    # Read once, not once per school. Both of these are fleet-wide facts; looking them up
    # inside the loop turned one page into 2N+3 queries, and the policy half of it was
    # re-reading the very map built on the line above.
    released = ManifestRelease.rings_for(operator_hash) if operator_hash else []

    rows = []
    counts = {"parity": 0, "behind": 0, "waiting": 0, "failed": 0, "paused": 0, "quiet": 0, "never": 0}
    for school in School.objects.all().order_by("name"):
        row = states.get(school.pk)
        policy = policies.get(school.pk)
        ring = policy.ring if policy else "stable"
        paused = bool(policy and policy.paused)
        allowed, reason = (
            may_receive(school, operator_hash, ring=ring, paused=paused, released=released)
            if operator_hash
            else (False, _("Operator has no manifest"))
        )
        state, label = _state_for(row, ring, paused, allowed, reason, operator_hash, now)
        counts[state] = counts.get(state, 0) + 1
        rows.append(
            {
                "school": school,
                "ring": ring,
                "paused": paused,
                "state": state,
                "label": label,
                "reported": (row.reported_manifest_hash if row else "") or "",
                "engine": (row.reported_engine if row else "") or "",
                "last_seen": row.last_seen_at if row else None,
                "last_moved": row.last_manifest_change_at if row else None,
                "failure": (row.last_failure_text if row else "") or "",
                "failure_at": row.last_failure_at if row else None,
            }
        )

    # FILTER, not decoration. A summary tile that reports "3 failed" across 300 schools
    # and gives you no way to reach those 3 is a number you cannot act on — you would be
    # scrolling a table hunting for red. Each tile links here, so the count and the rows
    # behind it are the same click.
    wanted = (request.GET.get("state") or "").strip().lower()
    if wanted in counts:
        rows = [r for r in rows if r["state"] == wanted]

    release = ManifestRelease.objects.filter(manifest_hash=operator_hash).first() if operator_hash else None
    context = {
        "page_title": _("Edge fleet — releases"),
        "active_filter": wanted if wanted in counts else "",
        "operator_hash": operator_hash,
        "operator_version": str(manifest.get("version_label") or ""),
        "operator_channel": str(manifest.get("channel") or ""),
        "released_rings": (release.rings if release else default_release_rings()),
        "release_is_explicit": release is not None,
        "rows": rows,
        "counts": counts,
        "total": len(rows),
        "fleet_total": sum(counts.values()),
        "quiet_after_hours": _QUIET_AFTER_HOURS,
    }
    return render(request, "sync_engine/super/fleet_console.html", context)
