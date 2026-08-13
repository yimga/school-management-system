"""Deterministic, I/O-free presentation profiles for Django Admin surfaces."""
from __future__ import annotations
from dataclasses import asdict, dataclass
from typing import Final
from django.utils.translation import gettext as _

@dataclass(frozen=True, slots=True)
class AdminSurfaceProfile:
    role_slug: str
    role_label: str
    mission_label: str
    index_title: str
    index_summary: str
    primary_action_label: str
    tone: str
    def as_context(self) -> dict[str, str]:
        return asdict(self)

_TENANT: Final = {
    "principal": AdminSurfaceProfile("principal", _("Principal"), _("Learning & leadership"), _("School leadership records"), _("Review school-scoped records and configuration that keep learning operations aligned."), _("Open configuration"), "violet"),
    "bursar": AdminSurfaceProfile("bursar", _("Bursar"), _("Finance operations"), _("Finance configuration & records"), _("Manage school-scoped finance records, controls, and integrations from this workbench."), _("Open finance records"), "emerald"),
    "registrar": AdminSurfaceProfile("registrar", _("Registrar"), _("Enrollment operations"), _("Enrollment configuration & records"), _("Keep admissions, learner records, and registry-backed configuration accurate and ready."), _("Open people records"), "coral"),
    "admin": AdminSurfaceProfile("admin", _("Administrator"), _("School operations"), _("Configuration & records"), _("Open any school-scoped model or use guided configuration for safer operational changes."), _("Open configuration"), "azure"),
}
_ALIASES: Final = {"ACCOUNTANT":"bursar","BURSAR":"bursar","FINANCE":"bursar","PRINCIPAL":"principal","HEAD_TEACHER":"principal","REGISTRAR":"registrar","ADMISSIONS":"registrar","SECRETARY":"registrar"}

def build_admin_surface_profile(*, user: object, is_platform: bool) -> dict[str, str]:
    """Return a bounded template-safe profile; never performs database or network I/O."""
    if is_platform:
        return AdminSurfaceProfile("operator", _("Operator"), _("Platform operations"), _("Platform catalog"), _("Open governed platform records while guided workflows remain available from the control plane."), _("Create school"), "indigo").as_context()
    raw = str(getattr(user, "role", "") or "").strip().upper()[:64]
    return _TENANT[_ALIASES.get(raw, "admin")].as_context()
