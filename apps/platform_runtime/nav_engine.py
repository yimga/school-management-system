"""Platform nav catalog — spine / search / action destinations for every rail.

Live tenant rail still renders from ``portal_sidebar_items``; live operator rail
still renders from ``control_plane_nav`` + ``manager_nav_convergence``. Those
projectors **must** consume this catalog for new membership so Cmd+K, tenant
staff ops, and operator hubs stay one id set.

``sidebar_registry.py`` remains the Studio-focus seed only. Do not treat it as
the portal/operator SOT.

Chrome (CSS/JS rail) is out of scope here.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Literal

NavClass = Literal["spine", "search", "action"]
Plane = Literal["tenant", "operator", "studio"]
Surface = Literal["ops", "config"]


@dataclass(frozen=True)
class NavSpec:
    id: str
    label: str
    url_name: str
    icon: str
    planes: tuple[Plane, ...]
    nav_class: NavClass
    group: str = ""
    section: str = ""
    surface: Surface = "ops"
    cmd_kind: str = "navigate"
    cmd_scope: str = "tenant_admin"


# Extended hats that get staff ops+config (not User.Role TextChoices).
# HOD was missing and received neither teacher workspace nor staff admin nav.
STAFF_PRIMARY_ROLES: frozenset[str] = frozenset(
    {
        "ADMIN",  # role-string-allow: nav-engine-staff-primary-hat-set
        "LEADERSHIP",  # role-string-allow: nav-engine-staff-primary-hat-set
        "IT_ADMIN",  # role-string-allow: nav-engine-staff-primary-hat-set
        "PRINCIPAL",  # role-string-allow: nav-engine-staff-primary-hat-set
        "VICE_PRINCIPAL",  # role-string-allow: nav-engine-staff-primary-hat-set
        "DEAN",  # role-string-allow: nav-engine-staff-primary-hat-set
        "HOD",  # role-string-allow: nav-engine-staff-primary-hat-set
        "BURSAR",  # role-string-allow: nav-engine-staff-primary-hat-set
        "ACCOUNTANT",  # role-string-allow: nav-engine-staff-primary-hat-set
        "PROPRIETOR",  # role-string-allow: nav-engine-staff-primary-hat-set
        "DISCIPLINE_MASTER",  # role-string-allow: nav-engine-staff-primary-hat-set
        "SECRETARY",  # role-string-allow: nav-engine-staff-primary-hat-set
    }
)

FAMILY_HATS: frozenset[str] = frozenset(
    {
        "PARENT",  # role-string-allow: nav-engine-family-hat-set
        "STUDENT",  # role-string-allow: nav-engine-family-hat-set
    }
)

TENANT_STAFF_SPINE_IDS: tuple[str, ...] = (
    "teachers",
    "subjects",
    "specialties",
    "classrooms",
    "academic_years",
    "sync_center",
    "ops_hub",
    "ops_inventory",
    "ops_transport",
    "ops_timetabling",
    "timetable_generate",
    "migration_wizard",
)

TENANT_STAFF_SPINE: tuple[NavSpec, ...] = (
    # Added 2026-09-04 with the identity handshake. The queue is where a box's
    # request to create a person gets answered, and a queue nobody can navigate
    # to is the same defect it was built to fix -- a refusal with nowhere to go.
    NavSpec(
        id="access_requests",
        label="Access requests",
        url_name="accounts:provisioning_queue",
        icon="bi-person-plus",
        planes=("tenant",),
        nav_class="spine",
        section="People & Access",
        cmd_kind="navigate",
        cmd_scope="tenant_admin",
    ),
    NavSpec(
        id="teachers",
        label="Teachers",
        url_name="accounts:backend_teacher_list",
        icon="bi-person-badge",
        planes=("tenant",),
        nav_class="spine",
        section="People & Access",
        cmd_kind="navigate",
        cmd_scope="tenant_admin",
    ),
    NavSpec(
        id="subjects",
        label="Subjects",
        url_name="accounts:backend_subject_list",
        icon="bi-journal-text",
        planes=("tenant",),
        nav_class="spine",
        section="Academic Management",
        cmd_kind="navigate",
        cmd_scope="tenant_admin",
    ),
    NavSpec(
        id="specialties",
        label="Specialties",
        url_name="accounts:backend_specialty_list",
        icon="bi-diagram-3",
        planes=("tenant",),
        nav_class="spine",
        section="Academic Management",
        cmd_kind="navigate",
        cmd_scope="tenant_admin",
    ),
    NavSpec(
        id="classrooms",
        label="Classrooms",
        url_name="accounts:backend_classroom_list",
        icon="bi-building",
        planes=("tenant",),
        nav_class="spine",
        section="People & Access",
        cmd_kind="navigate",
        cmd_scope="tenant_admin",
    ),
    NavSpec(
        id="academic_years",
        label="Academic years",
        url_name="siteconfig:academic_years_setup_evidence",
        icon="bi-calendar3",
        planes=("tenant",),
        nav_class="spine",
        section="Academic Management",
        cmd_kind="navigate",
        cmd_scope="tenant_admin",
    ),
    NavSpec(
        id="sync_center",
        label="Sync Center",
        url_name="siteconfig:sync_center",
        icon="bi-arrow-repeat",
        planes=("tenant",),
        nav_class="spine",
        section="Operations",
        cmd_kind="navigate",
        cmd_scope="tenant_admin",
    ),
    NavSpec(
        id="ops_hub",
        label="School operations",
        url_name="accounts:ops_hub",
        icon="bi-building-gear",
        planes=("tenant",),
        nav_class="spine",
        section="Operations",
        cmd_kind="navigate",
        cmd_scope="tenant_admin",
    ),
    NavSpec(
        id="ops_inventory",
        label="Inventory",
        url_name="accounts:ops_inventory",
        icon="bi-box-seam",
        planes=("tenant",),
        nav_class="spine",
        section="Operations",
        cmd_kind="navigate",
        cmd_scope="tenant_admin",
    ),
    NavSpec(
        id="ops_transport",
        label="Transport",
        url_name="accounts:ops_transport",
        icon="bi-bus-front",
        planes=("tenant",),
        nav_class="spine",
        section="Operations",
        cmd_kind="navigate",
        cmd_scope="tenant_admin",
    ),
    NavSpec(
        id="ops_timetabling",
        label="Timetabling",
        url_name="accounts:ops_timetabling",
        icon="bi-calendar-week",
        planes=("tenant",),
        nav_class="spine",
        section="Academic Management",
        cmd_kind="navigate",
        cmd_scope="tenant_admin",
    ),
    NavSpec(
        id="timetable_generate",
        label="Generate timetable",
        url_name="academics:timetable_generate",
        icon="bi-magic",
        planes=("tenant",),
        nav_class="spine",
        section="Academic Management",
        cmd_kind="navigate",
        cmd_scope="tenant_admin",
    ),
    NavSpec(
        id="migration_wizard",
        label="Migration wizard",
        url_name="accounts:migration_wizard",
        icon="bi-cloud-arrow-up",
        planes=("tenant",),
        nav_class="spine",
        section="Operations",
        cmd_kind="navigate",
        cmd_scope="tenant_admin",
    ),
)

OPERATOR_SPINE: tuple[NavSpec, ...] = (
    NavSpec(
        # Which school is on which release, and which one is stuck. Registered here rather
        # than left as a bare URL because an operator page nobody can navigate to is very
        # nearly as useless as no page: the whole point is that somebody LOOKS at the
        # canary before widening a release.
        id="super_edge_fleet",
        label="Edge fleet",
        url_name="super:edge_fleet_console",
        icon="bi-hdd-network",
        planes=("operator",),
        nav_class="spine",
        group="Platform Overview",
        surface="ops",
        cmd_kind="navigate",
        cmd_scope="staff",
    ),
    NavSpec(
        id="super_founder_dashboard",
        label="Founder dashboard",
        url_name="super:founder_dashboard",
        icon="bi-flag",
        planes=("operator",),
        nav_class="spine",
        group="Platform Overview",
        surface="ops",
        cmd_kind="navigate",
        cmd_scope="staff",
    ),
    NavSpec(
        id="super_ai_model_hub",
        label="AI model hub",
        url_name="super:ai_model_hub",
        icon="bi-cpu",
        planes=("operator",),
        nav_class="spine",
        group="Platform Overview",
        surface="ops",
        cmd_kind="navigate",
        cmd_scope="staff",
    ),
    NavSpec(
        id="super_fleet_wall",
        label="Fleet wall",
        url_name="super:fleet_wall",
        icon="bi-grid-3x3",
        planes=("operator",),
        nav_class="spine",
        group="Tenants",
        surface="ops",
        cmd_kind="navigate",
        cmd_scope="staff",
    ),
    NavSpec(
        id="super_group_campuses",
        label="Group campuses",
        url_name="super:group_campuses",
        icon="bi-diagram-3",
        planes=("operator",),
        nav_class="spine",
        group="Tenants",
        surface="ops",
        cmd_kind="navigate",
        cmd_scope="staff",
    ),
    NavSpec(
        id="super_native_roster_connectors",
        label="Native roster connectors",
        url_name="super:native_roster_connectors",
        icon="bi-plug",
        planes=("operator",),
        nav_class="spine",
        group="Tenants",
        surface="ops",
        cmd_kind="navigate",
        cmd_scope="staff",
    ),
    NavSpec(
        id="super_advancement_hub",
        label="Advancement",
        url_name="super:advancement_hub",
        icon="bi-mortarboard",
        planes=("operator",),
        nav_class="spine",
        group="Tenants",
        surface="ops",
        cmd_kind="navigate",
        cmd_scope="staff",
    ),
    NavSpec(
        id="super_he_pack",
        label="Higher-ed pack",
        url_name="super:he_pack",
        icon="bi-journal-richtext",
        planes=("operator",),
        nav_class="spine",
        group="Tenants",
        surface="ops",
        cmd_kind="navigate",
        cmd_scope="staff",
    ),
    NavSpec(
        id="super_marketplace_installation_health",
        label="Installation health",
        url_name="super:marketplace_installation_health",
        icon="bi-heart-pulse",
        planes=("operator",),
        nav_class="spine",
        group="Marketplace",
        surface="ops",
        cmd_kind="navigate",
        cmd_scope="staff",
    ),
    NavSpec(
        id="super_plans_list",
        label="Plans",
        url_name="super:plans_list",
        icon="bi-card-list",
        planes=("operator",),
        nav_class="spine",
        group="Observability & Billing",
        surface="ops",
        cmd_kind="navigate",
        cmd_scope="staff",
    ),
    NavSpec(
        id="super_security_hub",
        label="Security hub",
        url_name="super:security_hub",
        icon="bi-shield-check",
        planes=("operator",),
        nav_class="spine",
        group="Trust & Compliance",
        surface="ops",
        cmd_kind="navigate",
        cmd_scope="staff",
    ),
    NavSpec(
        id="super_orchestration_workbench",
        label="Orchestration workbench",
        url_name="super:orchestration_workbench",
        icon="bi-diagram-2",
        planes=("operator",),
        nav_class="spine",
        group="Operator tools",
        surface="config",
        cmd_kind="navigate",
        cmd_scope="staff",
    ),
)

OPERATOR_SPINE_IDS: tuple[str, ...] = tuple(spec.id for spec in OPERATOR_SPINE)


def all_catalog() -> tuple[NavSpec, ...]:
    return TENANT_STAFF_SPINE + OPERATOR_SPINE


def catalog_ids() -> frozenset[str]:
    return frozenset(spec.id for spec in all_catalog())


def spine_specs(*, plane: Plane | None = None) -> tuple[NavSpec, ...]:
    rows = [spec for spec in all_catalog() if spec.nav_class == "spine"]
    if plane:
        rows = [spec for spec in rows if plane in spec.planes]
    return tuple(rows)


def operator_items_for_group(group_label: str) -> list[dict]:
    """Dicts ready for ``control_plane_nav.add_group`` item lists."""
    out: list[dict] = []
    for spec in OPERATOR_SPINE:
        if spec.group != group_label:
            continue
        out.append(
            {
                "id": spec.id,
                "label": spec.label,
                "url_name": spec.url_name,
                "icon": spec.icon,
            }
        )
    return out


def command_bar_extra_defs() -> tuple[tuple, ...]:
    """6-tuples matching ``command_bar_registry._PLATFORM_ACTION_DEFS``."""
    rows = []
    for spec in all_catalog():
        if spec.nav_class == "action":
            continue
        rows.append(
            (
                spec.cmd_kind,
                spec.label,
                spec.icon,
                spec.url_name,
                spec.cmd_scope,
                None,
            )
        )
    return tuple(rows)


def is_staff_primary_role(role: str | None) -> bool:
    return (role or "").upper() in STAFF_PRIMARY_ROLES


def is_family_hat(role: str | None) -> bool:
    return (role or "").upper() in FAMILY_HATS


def resolve_specs(
    specs: Iterable[NavSpec],
    reverse_fn,
) -> list[dict]:
    """Turn catalog rows into portal sidebar item dicts. Missing URLs are skipped."""
    items: list[dict] = []
    for spec in specs:
        url = reverse_fn(spec.url_name)
        if not url:
            continue
        items.append(
            {
                "id": spec.id,
                "label": spec.label,
                "url": url,
                "icon": spec.icon,
                "section": spec.section or spec.group or "Navigation",
                "badge": None,
            }
        )
    return items
