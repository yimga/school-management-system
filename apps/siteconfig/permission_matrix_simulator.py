"""Permission Matrix Simulator — explain why a role can or cannot access a capability."""

from __future__ import annotations

from typing import Any

from apps.accounts.permissions import ROLE_RANK
from apps.platform_runtime.role_registry import ALL_ROLES
from apps.accounts.effective_access import school_permission_access
from apps.schools.tenant_access import SchoolAction


# Surfaces admins most often debug (maps to coarse actions + feature codes).
_CAPABILITY_MATRIX = (
    {
        "key": "view_roster",
        "label": "View student roster",
        "school_action": "view",
        "feature_code": "people.manage",
        "entity": "student",
        "pdp_action": "read",
    },
    {
        "key": "edit_grades",
        "label": "Edit grades",
        "school_action": "edit",
        "feature_code": "grades.manage",
        "entity": "grade",
        "pdp_action": "write",
    },
    {
        "key": "export_attendance",
        "label": "Export attendance CSV",
        "school_action": "export",
        "feature_code": "attendance.manage",
        "entity": "attendance",
        "pdp_action": "export",
    },
    {
        "key": "manage_settings",
        "label": "Manage school settings",
        "school_action": "admin",
        "feature_code": "settings.manage",
        "entity": "site_settings",
        "pdp_action": "write",
    },
    {
        "key": "view_finance",
        "label": "View finance ledger",
        "school_action": "view",
        "feature_code": "finance.manage",
        "entity": "invoice",
        "pdp_action": "read",
    },
)


def list_simulator_roles() -> list[str]:
    from apps.accounts.models import User

    extra = {str(c.value) for c in User.Role}
    return sorted(ALL_ROLES | extra | set(ROLE_RANK.keys()))


def simulate_role_capabilities(
    *,
    school,
    role: str,
    subject_user=None,
) -> dict[str, Any]:
    """
    Explain visibility for a role (or concrete user) across standard capabilities.

    Uses SchoolMembership role, has_school_permission, feature permissions, and PDP.
    """
    role_norm = (role or "").strip().upper()
    if not role_norm:
        return {"role": "", "capabilities": [], "error": "role_required"}

    class _ProxyUser:
        is_authenticated = True
        is_superuser = False
        role = role_norm
        pk = None

        def has_feature_permission(self, code: str) -> bool:
            from apps.accounts.models import User

            if not code:
                return False
            perm_code = (code or "").strip().lower()
            try:
                if hasattr(User, "feature_permission_codes_for_role"):
                    allowed = User.feature_permission_codes_for_role(role_norm)
                    return perm_code in {str(x).lower() for x in (allowed or [])}
            except (AttributeError, TypeError, ValueError):
                pass
            if role_norm in {"ADMIN", "SUPERADMIN", "PROPRIETOR", "LEADERSHIP"}:
                return True
            if role_norm == "TEACHER" and perm_code in {
                "attendance.manage",
                "grades.manage",
                "people.manage",
            }:
                return True
            if role_norm == "PARENT" and perm_code in {"portal.parent"}:
                return True
            return False

    proxy = subject_user if subject_user is not None else _ProxyUser()
    capabilities: list[dict[str, Any]] = []

    for row in _CAPABILITY_MATRIX:
        school_action: SchoolAction = row["school_action"]  # type: ignore[assignment]
        school_ok = (
            school_permission_access(proxy, school, school_action) if school else False
        )
        feature_ok = False
        if hasattr(proxy, "has_feature_permission"):
            try:
                feature_ok = proxy.has_feature_permission(row["feature_code"])
            except (AttributeError, TypeError, ValueError):
                feature_ok = False

        pdp_effect = "implicit_deny"
        pdp_reason = "No policy evaluation (school missing)."
        if school is not None:
            try:
                from apps.policies.pdp import decide

                decision = decide(
                    {"role": role_norm, "user_id": getattr(proxy, "pk", None)},
                    row["pdp_action"],
                    {
                        "entity": row["entity"],
                        "school_id": str(school.pk),
                    },
                    school=school,
                )
                pdp_effect = decision.effect
                pdp_reason = decision.reason
            except (ImportError, AttributeError, TypeError, ValueError) as exc:
                pdp_reason = f"PDP unavailable: {exc}"

        visible = school_ok and (feature_ok or role_norm in {"ADMIN", "SUPERADMIN"})
        if pdp_effect == "deny":
            visible = False

        reasons = []
        if school_ok:
            reasons.append(f"School action '{school_action}' allowed.")
        else:
            reasons.append(f"School action '{school_action}' denied for role {role_norm}.")
        if feature_ok:
            reasons.append(f"Feature '{row['feature_code']}' granted.")
        else:
            reasons.append(f"Feature '{row['feature_code']}' not in role bundle.")
        reasons.append(f"PDP: {pdp_effect} — {pdp_reason}")

        capabilities.append(
            {
                "key": row["key"],
                "label": row["label"],
                "visible": visible,
                "school_action_ok": school_ok,
                "feature_ok": feature_ok,
                "pdp_effect": pdp_effect,
                "reasons": reasons,
                "patch_hint": (
                    "Grant membership with a staff role, or add feature via AccessRole."
                    if not visible
                    else ""
                ),
            }
        )

    return {
        "role": role_norm,
        "role_rank": ROLE_RANK.get(role_norm, 0),
        "capabilities": capabilities,
    }


def compare_roles_capabilities(
    *,
    school,
    roles: list[str],
) -> dict[str, Any]:
    """Side-by-side capability matrix for multiple roles."""
    rows = []
    for role in roles:
        sim = simulate_role_capabilities(school=school, role=role)
        rows.append(sim)
    keys = [c["key"] for c in _CAPABILITY_MATRIX]
    comparison: list[dict[str, Any]] = []
    for key in keys:
        label = next(r["label"] for r in _CAPABILITY_MATRIX if r["key"] == key)
        entry: dict[str, Any] = {"key": key, "label": label, "roles": {}}
        for sim in rows:
            cap = next(
                (c for c in sim["capabilities"] if c["key"] == key),
                {"visible": False},
            )
            entry["roles"][sim["role"]] = cap.get("visible", False)
        comparison.append(entry)
    return {"comparison": comparison, "simulations": rows}


def export_simulation_json(simulation: dict[str, Any]) -> dict[str, Any]:
    return {
        "role": simulation.get("role"),
        "role_rank": simulation.get("role_rank"),
        "capabilities": [
            {
                "key": c["key"],
                "label": c["label"],
                "visible": c["visible"],
                "reasons": c.get("reasons", []),
            }
            for c in simulation.get("capabilities", [])
        ],
    }


def export_simulation_csv(simulation: dict[str, Any]) -> str:
    import csv
    import io

    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(["role", "capability", "label", "visible", "reasons"])
    role = simulation.get("role", "")
    for cap in simulation.get("capabilities", []):
        writer.writerow(
            [
                role,
                cap.get("key", ""),
                cap.get("label", ""),
                "yes" if cap.get("visible") else "no",
                " | ".join(cap.get("reasons", [])),
            ]
        )
    return buf.getvalue()
