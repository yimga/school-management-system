"""Canvas-first Experience builder - region catalog + scoped inspector model.

Single source of truth for the six editable "regions" the Studio Experience
canvas-first builder exposes. Design SOT:
``var/design-previews/django-studio-canvas-first-builder-approval.html`` (the
"Page outline" + "Inspector" surfaces).

Each region maps a slice of the tenant preview surface to the theme/experience
fields that govern it.

INVARIANT (enforced by tests + ``validate_region_catalog``): every editable
field a region declares MUST be a member of
``apps.siteconfig.forms.THEME_EXPERIENCE_FIELD_NAMES`` - the publish-guarded
theme SOT. The builder never invents a parallel write path; each editable
inspector row anchors to the real form widget already rendered in the canvas
(``#id_<field>``). Softer, product-derived rows are read-only descriptors -
never fake-editable inputs (that is the decorative-control anti-pattern).

Import discipline: this module holds plain data + pure helpers only. It does
NOT import Django or ``siteconfig.forms`` at module load (the field-name
allowlist is validated lazily, so importing the catalog is free of side
effects and safe to reference from URL/registry scan time).
"""

from __future__ import annotations

from typing import Any

# ---- Field display labels (human, region-inspector) -------------------------
# Keys are members of THEME_EXPERIENCE_FIELD_NAMES; values are short labels.
FIELD_LABELS: dict[str, str] = {
    "primary_color": "Primary color",
    "accent_color": "Accent color",
    "header_bg_color": "Header background",
    "footer_bg_color": "Footer background",
    "success_color": "Success color",
    "warning_color": "Warning color",
    "danger_color": "Danger color",
    "theme_brightness": "Brightness",
    "use_dark_mode": "Dark mode",
    "theme_pack": "Portal theme pack",
    "admin_theme_pack": "Admin theme pack",
    "teacher_theme_pack": "Teacher theme pack",
    "parent_theme_pack": "Parent theme pack",
    "theme_harmony": "Color harmony",
    "admin_use_site_primary": "Admin uses site primary",
    "backend_console_theme": "Backend console theme",
    "secondary_font": "Secondary font",
    "use_secondary_font_for_headings": "Secondary font for headings",
    "base_font_size": "Base font size",
    "default_dashboard_view": "Default dashboard view",
}

# Color fields render a swatch in the inspector.
COLOR_FIELDS: frozenset[str] = frozenset(
    {
        "primary_color",
        "accent_color",
        "header_bg_color",
        "footer_bg_color",
        "success_color",
        "warning_color",
        "danger_color",
    }
)

# ---- Region catalog (design SOT order) --------------------------------------
# ``fields`` = editable, MUST be a subset of THEME_EXPERIENCE_FIELD_NAMES.
# ``derived`` = read-only (label, description) descriptors from the design.
STUDIO_EXPERIENCE_REGIONS: list[dict[str, Any]] = [
    {
        "key": "header",
        "num": 1,
        "title": "Header and navigation",
        "blurb": "Logo, top nav, More menu, search density.",
        "fields": ["theme_pack", "primary_color", "accent_color", "header_bg_color"],
        "derived": [
            ("Search density", "Compact - about 25% narrower than default."),
            ("More button", "Shares the row with Home, Finance, Messages, Analytics."),
            ("Role coverage", "Admin, Teacher, Parent, Student, Finance."),
        ],
    },
    {
        "key": "hero",
        "num": 2,
        "title": "Hero surface",
        "blurb": "Role greeting, action priority, school brand.",
        "fields": ["primary_color", "accent_color", "theme_harmony"],
        "derived": [
            ("Role greeting", "Personalized per role home (Teacher command surface)."),
            ("Action priority", "Primary action promoted; secondary actions grouped."),
        ],
    },
    {
        "key": "cards",
        "num": 3,
        "title": "Dashboard cards",
        "blurb": "Card shape, contrast, spacing, labels.",
        "fields": [
            "theme_brightness",
            "success_color",
            "warning_color",
            "danger_color",
            "base_font_size",
        ],
        "derived": [
            ("Card shape", "Rounded, elevated; consistent across role dashboards."),
            ("Spacing", "Comfortable density; grid gap scales with base font size."),
        ],
    },
    {
        "key": "sidebar",
        "num": 4,
        "title": "Sidebar palette",
        "blurb": "Tenant admin backend and portal navigation.",
        "fields": [
            "admin_theme_pack",
            "teacher_theme_pack",
            "parent_theme_pack",
            "backend_console_theme",
            "admin_use_site_primary",
        ],
        "derived": [
            ("Navigation density", "Backend rail follows the admin console theme."),
        ],
    },
    {
        "key": "footer",
        "num": 5,
        "title": "Footer and help",
        "blurb": "Footer density, help placement, legal links.",
        "fields": ["footer_bg_color", "secondary_font"],
        "derived": [
            ("Footer density", "Condensed footer with grouped links."),
            ("Help placement", "Contextual help anchored bottom-right."),
            ("Legal links", "Privacy, terms, and accessibility statement."),
        ],
    },
    {
        "key": "mobile",
        "num": 6,
        "title": "Mobile layout",
        "blurb": "Collapsed nav and touch targets.",
        "fields": ["use_dark_mode", "default_dashboard_view"],
        "derived": [
            ("Collapsed nav", "Top nav collapses into a single More menu."),
            ("Touch targets", "Minimum 44px targets on primary actions."),
        ],
    },
]

# Every region always ends with this shared publish-guard descriptor (design).
PUBLISH_GUARD_ROW = (
    "Publish guard",
    "Preview all role and device combinations before publish.",
)

_REGION_BY_KEY: dict[str, dict[str, Any]] = {r["key"]: r for r in STUDIO_EXPERIENCE_REGIONS}


def region_keys() -> list[str]:
    """Ordered region keys."""
    return [r["key"] for r in STUDIO_EXPERIENCE_REGIONS]


def resolve_selected_region(key: str | None) -> dict[str, Any]:
    """Return the region dict for ``key`` (falls back to the first region)."""
    if key:
        region = _REGION_BY_KEY.get(str(key).strip().lower())
        if region is not None:
            return region
    return STUDIO_EXPERIENCE_REGIONS[0]


def resolve_view_mode(value: str | None) -> str:
    """Normalize the Draft/Live toggle value. Defaults to ``draft``."""
    v = (value or "").strip().lower()
    return "live" if v == "live" else "draft"


def build_region_inspector(
    region: dict[str, Any], values: dict[str, Any] | None
) -> list[dict[str, Any]]:
    """Build the scoped inspector rows for ``region``.

    Editable rows carry ``editable=True`` + ``field_name`` + ``anchor`` so the
    template links each to the real form widget (``id_<field>``). Derived rows
    are read-only descriptors. Values come from the bound ThemeColorsForm; a
    missing/empty value renders as "Not set".
    """
    values = values or {}
    rows: list[dict[str, Any]] = [
        {
            "label": "Selected region",
            "value": region.get("title", ""),
            "editable": False,
            "kind": "meta",
        }
    ]
    for field_name in region.get("fields", []):
        raw = values.get(field_name)
        if raw is None or raw == "":
            display = "Not set"
        elif raw is True:
            display = "On"
        elif raw is False:
            display = "Off"
        else:
            display = str(raw)
        rows.append(
            {
                "label": FIELD_LABELS.get(field_name, field_name.replace("_", " ").title()),
                "value": display,
                "editable": True,
                "field_name": field_name,
                "anchor": "id_%s" % field_name,
                "kind": "color" if field_name in COLOR_FIELDS else "field",
                "swatch": display if field_name in COLOR_FIELDS and display != "Not set" else "",
            }
        )
    for label, description in region.get("derived", []):
        rows.append(
            {"label": label, "value": description, "editable": False, "kind": "derived"}
        )
    rows.append(
        {
            "label": PUBLISH_GUARD_ROW[0],
            "value": PUBLISH_GUARD_ROW[1],
            "editable": False,
            "kind": "derived",
        }
    )
    return rows


def build_region_outline(selected_key: str | None) -> list[dict[str, Any]]:
    """Outline navigator rows with an ``active`` flag on the selected region."""
    selected = resolve_selected_region(selected_key)["key"]
    return [
        {
            "key": r["key"],
            "num": r["num"],
            "title": r["title"],
            "blurb": r["blurb"],
            "active": r["key"] == selected,
            "field_count": len(r.get("fields", [])),
        }
        for r in STUDIO_EXPERIENCE_REGIONS
    ]


# ---- Role/device filmstrip (design SOT: "Role and device snapshots") --------
# Keyword -> descriptor. Matched against the role slug then the label so the
# filmstrip stays honest even when the tenant exposes a different role set.
_FILMSTRIP_DESCRIPTORS: list[tuple[str, str]] = [
    ("admin", "Backend density"),
    ("principal", "Backend density"),
    ("teacher", "Primary preview"),
    ("parent", "Family surface"),
    ("guardian", "Family surface"),
    ("student", "Mobile first"),
    ("finance", "Table clarity"),
    ("bursar", "Table clarity"),
]


def _filmstrip_descriptor(role: str, label: str) -> str:
    haystack = ("%s %s" % (role or "", label or "")).lower()
    for keyword, descriptor in _FILMSTRIP_DESCRIPTORS:
        if keyword in haystack:
            return descriptor
    return "Role preview"


def build_role_filmstrip(
    entries: list[dict[str, Any]] | None, limit: int = 5
) -> list[dict[str, Any]]:
    """Build role/device snapshot thumbnails from ``studio_role_preview_entries``.

    Each thumb links to the real role preview URL. Entries without a URL are
    dropped (a thumb must be openable - no dead tiles). Returns at most ``limit``.
    """
    out: list[dict[str, Any]] = []
    for entry in entries or []:
        if not isinstance(entry, dict):
            continue
        url = (entry.get("url") or "").strip()
        if not url or url == "#":
            continue
        role = entry.get("role", "")
        label = entry.get("label") or role or "Role"
        out.append(
            {
                "role": role,
                "label": label,
                "url": url,
                "descriptor": _filmstrip_descriptor(role, label),
            }
        )
        if len(out) >= limit:
            break
    return out


def validate_region_catalog() -> list[str]:
    """Return a list of invariant violations (empty when the catalog is sound).

    Checks: (1) every editable field is a member of THEME_EXPERIENCE_FIELD_NAMES;
    (2) region keys are unique; (3) numbering is 1..N contiguous. Imported lazily
    so this module has no Django import at load time.
    """
    from apps.siteconfig.forms import THEME_EXPERIENCE_FIELD_NAMES

    allowed = frozenset(THEME_EXPERIENCE_FIELD_NAMES)
    problems: list[str] = []
    seen_keys: set[str] = set()
    for idx, region in enumerate(STUDIO_EXPERIENCE_REGIONS, start=1):
        key = region.get("key")
        if key in seen_keys:
            problems.append("duplicate region key: %s" % key)
        seen_keys.add(key)
        if region.get("num") != idx:
            problems.append(
                "region %s num=%s expected %s" % (key, region.get("num"), idx)
            )
        for field_name in region.get("fields", []):
            if field_name not in allowed:
                problems.append(
                    "region %s field %r not in THEME_EXPERIENCE_FIELD_NAMES"
                    % (key, field_name)
                )
    return problems
