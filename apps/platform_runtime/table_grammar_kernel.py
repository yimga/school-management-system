"""Wave U (v3.99.0 — 2026-05-27) — 5-column table grammar + drawer kernel.

The Protocol Zero-Click-Intuition rule: no master-list table renders more
than 5 columns. Excess columns route into the right-aligned context
detail drawer that opens on row click. This kernel enforces the rule
declaratively so template code never has to branch on persona / breakpoint.

Public API:
    truncate_columns(columns, persona, max_visible=5)
        Returns (visible_columns, drawer_columns).
        Caller renders ``visible_columns`` in the <thead>/<tbody> grid;
        ``drawer_columns`` populate the slide-from-right drawer.

    classify_column_priority(column)
        Stable ordering used internally when persona-specific priority is
        not explicit. Identity / status / primary metric > everything else.

The kernel is pure-Python (no Django, no DB) so it stays
``SimpleTestCase``-friendly.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable, Sequence

# Maximum primary-visible columns per table. The "5" is fixed because
# wider grids horizontally scroll on mobile / RTL / 40%-typography expansion.
MAX_PRIMARY_COLUMNS = 5

# Personas (kept in parity with smart_links_kernel).
PERSONA_ANY = "any"
PERSONA_OPERATOR = "operator"
PERSONA_TENANT_ADMIN = "tenant_admin"
PERSONA_TEACHER = "teacher"
PERSONA_PARENT = "parent"
PERSONA_STUDENT = "student"
PERSONA_STAFF = "staff"

# Priority tiers — lower number renders first.
PRIORITY_IDENTITY = 0      # name / label / id chip
PRIORITY_STATUS = 1        # state / badge
PRIORITY_PRIMARY_METRIC = 2  # the row's key number
PRIORITY_SECONDARY = 3
PRIORITY_TERTIARY = 4
PRIORITY_DRAWER_ONLY = 9   # never surfaced in the main grid

# Column-name hints used by the default heuristic. ``classify_column_priority``
# checks these in order; first match wins.
_IDENTITY_HINTS = ("name", "title", "label", "student", "applicant", "guardian")
_STATUS_HINTS = ("status", "state", "stage", "phase")
_METRIC_HINTS = ("balance", "due", "score", "grade", "rate", "count", "total")
_SECONDARY_HINTS = ("date", "submitted", "created", "updated", "owner", "class")
_DRAWER_ONLY_HINTS = (
    "notes", "narrative", "history", "audit", "raw", "internal_id",
    "metadata", "ip_address", "user_agent",
)


@dataclass(frozen=True)
class Column:
    """A typed column descriptor passed to ``truncate_columns``."""

    key: str
    label: str
    priority: int | None = None
    # Per-persona priority overrides — a key like ``{"parent": 0}`` will
    # hoist this column to identity priority for the parent shell only.
    persona_overrides: dict[str, int] = field(default_factory=dict)
    helper_text: str = ""
    # If ``always_drawer`` is True, the column is never surfaced in the
    # main grid regardless of persona — sensitive narrative / raw audit
    # rows should set this.
    always_drawer: bool = False


@dataclass(frozen=True)
class TruncationResult:
    visible_columns: tuple[Column, ...]
    drawer_columns: tuple[Column, ...]
    overflow_count: int

    @property
    def fits_without_drawer(self) -> bool:
        return self.overflow_count == 0


def classify_column_priority(column: Column, persona: str = PERSONA_ANY) -> int:
    """Return the effective priority for a column on a given persona."""
    if column.always_drawer:
        return PRIORITY_DRAWER_ONLY
    # Persona-specific override wins outright.
    if persona in column.persona_overrides:
        return int(column.persona_overrides[persona])
    if column.priority is not None:
        return int(column.priority)
    key_lc = (column.key or "").lower()
    for hint in _DRAWER_ONLY_HINTS:
        if hint in key_lc:
            return PRIORITY_DRAWER_ONLY
    for hint in _IDENTITY_HINTS:
        if hint in key_lc:
            return PRIORITY_IDENTITY
    for hint in _STATUS_HINTS:
        if hint in key_lc:
            return PRIORITY_STATUS
    for hint in _METRIC_HINTS:
        if hint in key_lc:
            return PRIORITY_PRIMARY_METRIC
    for hint in _SECONDARY_HINTS:
        if hint in key_lc:
            return PRIORITY_SECONDARY
    return PRIORITY_TERTIARY


def truncate_columns(
    columns: Sequence[Column],
    persona: str = PERSONA_ANY,
    max_visible: int = MAX_PRIMARY_COLUMNS,
) -> TruncationResult:
    """Partition ``columns`` into primary (visible) and drawer (overflow) sets.

    Sort is stable: input order is preserved within priority tiers so a
    caller that has already curated their column order gets predictable
    output. Drawer-only columns ALWAYS go to the drawer regardless of cap.
    """
    if max_visible < 1:
        raise ValueError("max_visible must be >= 1")
    if not columns:
        return TruncationResult((), (), 0)

    decorated = [
        (classify_column_priority(col, persona=persona), idx, col)
        for idx, col in enumerate(columns)
    ]
    # Stable sort by (priority, original index).
    decorated.sort(key=lambda triple: (triple[0], triple[1]))

    visible: list[Column] = []
    drawer: list[Column] = []
    for priority, _idx, col in decorated:
        if priority == PRIORITY_DRAWER_ONLY:
            drawer.append(col)
            continue
        if len(visible) < max_visible:
            visible.append(col)
        else:
            drawer.append(col)

    overflow = len(drawer) - sum(
        1 for c in columns if classify_column_priority(c, persona=persona) == PRIORITY_DRAWER_ONLY
    )
    return TruncationResult(
        visible_columns=tuple(visible),
        drawer_columns=tuple(drawer),
        overflow_count=max(0, overflow),
    )


# --- Convenience builders -------------------------------------------------


def build_columns_from_dicts(rows: Iterable[dict]) -> list[Column]:
    """Tiny helper for tests + ad-hoc callers.

    Each dict can carry ``key`` (required) and any of: ``label``, ``priority``,
    ``persona_overrides``, ``helper_text``, ``always_drawer``.
    """
    out: list[Column] = []
    for row in rows:
        if "key" not in row:
            raise ValueError(f"column dict missing 'key': {row!r}")
        out.append(
            Column(
                key=row["key"],
                label=row.get("label") or row["key"].replace("_", " ").title(),
                priority=row.get("priority"),
                persona_overrides=row.get("persona_overrides", {}) or {},
                helper_text=row.get("helper_text", ""),
                always_drawer=bool(row.get("always_drawer", False)),
            ),
        )
    return out
