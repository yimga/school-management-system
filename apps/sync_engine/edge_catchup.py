"""Empty-box pull rewind — first online cycle must ask the cloud for everything.

If a box was brought up ``--fresh`` and a dry-run or failed cycle still left a
PULL cursor, later live cycles only ask for rows newer than that stamp. Cloud
students never arrive. One rewind (then a flag) is the catch-up, tenant-wide.
"""

from __future__ import annotations


_EDGE_SETTINGS_KEY = "rmc_edge"
_EMPTY_PULL_DONE = "empty_box_full_pull_done"


def maybe_rewind_empty_box_pull(school) -> bool:
    """Rewind the PULL cursor once when the box has no students but a cursor.

    Returns True when cursors were rewound. Never raises into the sync runner.
    """
    from apps.sync_engine.edge_enabled import edge_sync_enabled

    if not edge_sync_enabled():
        return False
    if school is None:
        return False
    try:
        from apps.people.models import StudentProfile
        from apps.sync_engine.models import EdgeSyncCursor, get_sync_cursor, reset_sync_cursors

        st = dict(getattr(school, "settings", None) or {})
        edge = dict(st.get(_EDGE_SETTINGS_KEY) or {})
        if edge.get(_EMPTY_PULL_DONE):
            return False
        # tenant-isolation-allow: edge-box-catchup-scoped-via-school-fk-on-studentprofile
        if StudentProfile.objects.filter(school=school).exists():
            _mark_done(school, st, edge)
            return False
        cursor = get_sync_cursor(school, EdgeSyncCursor.PULL)
        if cursor is None:
            return False
        reset_sync_cursors(school, direction=EdgeSyncCursor.PULL)
        _mark_done(school, st, edge)
        return True
    except Exception:  # noqa: BLE001 — catch-up must never break a cycle
        return False


def _mark_done(school, st: dict, edge: dict) -> None:
    edge[_EMPTY_PULL_DONE] = True
    st[_EDGE_SETTINGS_KEY] = edge
    school.settings = st
    school.save(update_fields=["settings", "updated_at"])
