"""
Canonical RBAC envelope for every copilot surface (rail, floating panel, gateway).

No copilot invoke should assume role access — call ``prepare_copilot_invoke`` or
at minimum ``build_copilot_permissions`` + ``validate_copilot_query`` before any
LLM/rules path runs.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

__all__ = [
    "CopilotRbacEnvelope",
    "CopilotInvokeGuard",
    "COPILOT_RBAC_INTERNAL_TASKS",
    "build_copilot_permissions",
    "validate_copilot_query",
    "guard_copilot_invoke",
    "invoke_service_layer_ai",
    "prepare_copilot_invoke",
    "prepare_engine_room_rbac",
    "format_engine_room_denial",
    "rbac_directives_for_permissions",
    "guided_task_allowed_for_permissions",
    "copilot_request_shim",
]

# Background / batch tasks — no user-authored query RBAC gate (tenant policy still applies).
COPILOT_RBAC_INTERNAL_TASKS = frozenset(
    {
        "migration_mapping",
        "migration_fingerprint",
        "migration_parity",
        "doc_classify",
        "semantic_search",
        "narrative",
        "risk_explain",
        "report_card_comment",
    }
)


@dataclass(frozen=True)
class CopilotRbacEnvelope:
    allowed: bool
    denial_reason: str
    permissions: dict[str, Any]
    prompt: str
    metadata: dict[str, Any]


@dataclass(frozen=True)
class CopilotInvokeGuard:
    allowed: bool
    denial_reason: str
    prompt: str
    metadata: dict[str, Any]


def _normalize_task_key(task_type: Any) -> str:
    if hasattr(task_type, "value"):
        return str(task_type.value).lower()
    return str(task_type or "").lower().strip()


def _control_plane_operator(user: Any) -> bool:
    try:
        from apps.schools.control_plane import user_has_control_plane_access

        return user_has_control_plane_access(user)
    except Exception:
        return False


def build_copilot_permissions(user, *, request: Any | None = None) -> dict[str, Any]:
    """Role → capability map for copilot (single source of truth)."""
    school = getattr(request, "school", None) if request is not None else None
    role = getattr(user, "role", None) if user is not None else None
    if not role:
        try:
            from apps.accounts.utils import get_user_role

            role = get_user_role(user, school) if user is not None else None
        except Exception:
            role = None
    role = role or "USER"
    role_upper = str(role).upper()

    admin_roles = {
        "ADMIN",
        "LEADERSHIP",
        "PRINCIPAL",
        "VICE_PRINCIPAL",
        "DEAN",
        "IT_ADMIN",
        "SUPERADMIN",
        "PROPRIETOR",
    }
    is_admin_like = False
    if user is not None and getattr(user, "is_authenticated", False):
        is_admin_like = (
            getattr(user, "is_superuser", False)
            or getattr(user, "is_staff", False)
            or role_upper in admin_roles
            or _control_plane_operator(user)
        )

    permissions: dict[str, Any] = {
        "can_access_ai": bool(user and getattr(user, "is_authenticated", False)),
        "can_analyze_data": False,
        "can_view_financial": False,
        "can_view_compliance": False,
        "can_access_grades": False,
        "can_access_roster": False,
        "can_manage_users": False,
        "can_provision_tenants": False,
        "can_view_fleet_ops": False,
        "scope": "general",
    }
    if not permissions["can_access_ai"]:
        return permissions

    host_kind = getattr(request, "public_host_kind", None) if request is not None else None
    if is_admin_like:
        permissions.update(
            {
                "can_analyze_data": True,
                "can_view_financial": True,
                "can_view_compliance": True,
                "can_access_grades": True,
                "can_access_roster": True,
                "can_manage_users": True,
                "can_provision_tenants": host_kind == "manager" or _control_plane_operator(user),
                "can_view_fleet_ops": host_kind == "manager" or _control_plane_operator(user),
                "scope": "admin",
            }
        )
    elif role_upper == "BURSAR":
        permissions.update(
            {
                "can_analyze_data": True,
                "can_view_financial": True,
                "scope": "finance",
            }
        )
    elif role_upper == "TEACHER":  # role-string-allow: rbac-role-comparison
        permissions.update(
            {
                "can_access_grades": True,
                "can_access_roster": True,
                "scope": "teacher",
            }
        )
    elif role_upper == "PARENT":  # role-string-allow: rbac-role-comparison
        permissions.update(
            {
                "can_access_grades": True,
                "can_view_financial": True,
                "scope": "parent",
            }
        )
    elif role_upper == "STUDENT":  # role-string-allow: rbac-role-comparison
        permissions.update(
            {
                "can_access_grades": True,
                "scope": "student",
            }
        )
    return permissions


def validate_copilot_query(
    user,
    query: str,
    permissions: dict[str, Any] | None = None,
    *,
    school: Any | None = None,
    task_type: str = "studio_os_assistant",
) -> tuple[bool, str]:
    """Aggressive first-line RBAC gate — keyword + task permission."""
    from services.ai_permissions import get_ai_permission_for_user

    if user is None or not getattr(user, "is_authenticated", False):
        return False, "You are not authenticated to use AI Copilot."

    perms = permissions or build_copilot_permissions(user)
    if not perms.get("can_access_ai"):
        return False, "You are not authenticated to use AI Copilot."

    if not get_ai_permission_for_user(user, task_type, school):
        return False, "You don't have permission to use the AI assistant."

    q = (query or "").strip()
    if not q:
        return False, "Query cannot be empty."

    q_lower = q.lower()
    scope = str(perms.get("scope") or "general")

    payroll_keywords = ("salary", "payroll", "staff wage", "employee compensation")
    financial_keywords = (
        "invoice",
        "payment",
        "fee",
        "financial",
        "revenue",
        "billing",
        "tuition",
        "bursar",
    )
    compliance_keywords = (
        "audit log",
        "compliance export",
        "access log",
        "security audit",
        "ferpa export",
        "dsar",
        "subpoena",
    )
    fleet_keywords = (
        "all tenants",
        "every tenant",
        "fleet-wide",
        "migration cloud operator",
        "super dashboard",
        "create school",
        "provision tenant",
        "add tenant",
        "rapid create",
        "webhook secret",
        "api token mint",
    )
    roster_bulk_keywords = (
        "all grades",
        "all students grade",
        "every student",
        "full roster",
        "every class",
        "all classes grades",
    )
    user_admin_keywords = (
        "assign role",
        "change role",
        "delete user",
        "reset password for",
        "impersonate",
        "other parent",
        "other student",
    )

    if any(kw in q_lower for kw in payroll_keywords):
        if scope not in {"admin", "finance"}:
            return False, "You don't have permission to access payroll data."

    if any(kw in q_lower for kw in financial_keywords):
        if not perms.get("can_view_financial"):
            return False, "You don't have permission to access financial data."
        if scope == "parent" and any(
            tok in q_lower for tok in ("all invoices", "school revenue", "every fee", "total revenue")
        ):
            return False, "Parents can only view their own child's fees, not school-wide finance."

    if any(kw in q_lower for kw in compliance_keywords):
        if not perms.get("can_view_compliance"):
            return False, "You don't have permission to access compliance or audit data."

    if any(kw in q_lower for kw in fleet_keywords):
        if not perms.get("can_provision_tenants") and not perms.get("can_view_fleet_ops"):
            return False, "That workflow is restricted to platform operators."

    if any(kw in q_lower for kw in roster_bulk_keywords):
        if scope == "parent":
            return False, "Parents can only view their child's grades, not all students."
        if scope == "student":
            return False, "Students can only view their own grades, not all students."
        if scope == "teacher" and "all" in q_lower:
            return False, "Teachers can only view their own classes' grades and rosters."

    if any(kw in q_lower for kw in user_admin_keywords):
        if not perms.get("can_manage_users"):
            return False, "You don't have permission to manage other users."

    if scope in {"parent", "student", "teacher", "general"}:
        if any(kw in q_lower for kw in ("other school", "different tenant", "cross tenant")):
            return False, "You can only access information for your current school."

    return True, ""


def guard_copilot_invoke(
    *,
    request: Any | None,
    task_type: Any,
    prompt: str,
    user_query: str = "",
    metadata: dict[str, Any] | None = None,
) -> CopilotInvokeGuard:
    """Last-line RBAC before ``invoke_with_request`` / stream (belt-and-suspenders)."""
    md = dict(metadata or {})
    if md.get("copilot_rbac_enforced"):
        return CopilotInvokeGuard(True, "", prompt, md)
    if md.get("copilot_rbac_skip"):
        return CopilotInvokeGuard(True, "", prompt, md)

    task_key = _normalize_task_key(task_type)
    if task_key in COPILOT_RBAC_INTERNAL_TASKS:
        return CopilotInvokeGuard(True, "", prompt, md)
    if request is None:
        return CopilotInvokeGuard(True, "", prompt, md)

    user = getattr(request, "user", None)
    school = md.get("school") or getattr(request, "school", None)
    permissions = build_copilot_permissions(user, request=request)
    query = (user_query or "").strip()

    if query:
        allowed, denial = validate_copilot_query(
            user,
            query,
            permissions,
            school=school,
            task_type=task_key or "studio_os_assistant",
        )
        if not allowed:
            return CopilotInvokeGuard(
                False,
                denial,
                "",
                {
                    **md,
                    "outcome": "permission_refusal",
                    "copilot_rbac_enforced": True,
                    "provider": "none",
                },
            )

    host_kind = getattr(request, "public_host_kind", None)
    active_url = str(md.get("active_url") or getattr(request, "path", "") or "")
    directives = rbac_directives_for_permissions(
        permissions,
        active_url=active_url,
        host_kind=host_kind,
    )
    guarded_prompt = prompt
    if directives and directives not in prompt:
        guarded_prompt = f"{directives}\n\n{prompt}".strip()

    md.update(
        {
            "permissions": permissions,
            "rbac_scope": permissions.get("scope") or "general",
            "copilot_rbac_enforced": True,
        }
    )
    return CopilotInvokeGuard(True, "", guarded_prompt, md)


def invoke_service_layer_ai(
    *,
    user: Any | None,
    school: Any | None,
    task_type: Any,
    prompt: str,
    user_query: str = "",
    metadata: dict[str, Any] | None = None,
    require_available: bool = False,
    surface: str = "ai_service_layer",
    skip_rbac: bool = False,
    skip_reason: str = "",
) -> tuple[Any, dict[str, Any]]:
    """Closed-fail AI invoke for ``services/*`` draft helpers — never raises."""
    import logging

    from services.ai_helpers import invoke_with_request

    logger = logging.getLogger(__name__)
    md = dict(metadata or {})
    md.setdefault("surface", surface)
    if skip_rbac:
        md["copilot_rbac_skip"] = skip_reason or "automated-system-prompt"

    rbac_request = None
    if user is not None and getattr(user, "is_authenticated", False):
        rbac_request = copilot_request_shim(user=user, school=school)

    guard = guard_copilot_invoke(
        request=rbac_request,
        task_type=task_type,
        prompt=prompt,
        user_query=user_query,
        metadata=md,
    )
    if not guard.allowed:
        return guard.denial_reason or "Permission denied.", guard.metadata

    try:
        outcome = invoke_with_request(
            task_type=task_type,
            prompt=guard.prompt,
            request=rbac_request,
            school=school,
            user_query=user_query,
            metadata=guard.metadata,
            require_available=require_available,
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("invoke_service_layer_ai: invoke failed: %s", type(exc).__name__)
        return "", {"error": str(exc)[:200], "provider": "none"}

    if outcome is None:
        return "", {"provider": "none", "error": "unavailable"}
    result, meta = outcome
    if isinstance(result, str):
        return result.strip(), meta or {}
    return result, meta or {}


def rbac_directives_for_permissions(
    permissions: dict[str, Any],
    *,
    active_url: str = "",
    host_kind: str | None = None,
) -> str:
    """Hard system directives injected ahead of every copilot prompt."""
    scope = str(permissions.get("scope") or "general")
    lines = [
        "[RBAC ENFORCEMENT — NON-NEGOTIABLE]",
        f"Effective scope: {scope}.",
        "Never reveal data, URLs, or actions the user cannot access in the live UI.",
        "Never invent tenant names, student names, invoice amounts, or grades.",
        "If the question exceeds this scope, refuse briefly and suggest an in-product path they CAN open.",
    ]
    if host_kind == "manager":
        lines.append("Host: platform manager — fleet answers OK only when scope is admin/operator.")
    else:
        lines.append("Host: tenant portal — answers MUST stay inside this school and this user's role.")
    if scope == "parent":
        lines.append("Parent lane: only their linked child(ren); never other families or staff records.")
    elif scope == "student":
        lines.append("Student lane: only their own grades, schedule, and assignments.")
    elif scope == "teacher":
        lines.append("Teacher lane: only their assigned classes/rosters — not school-wide finance or HR.")
    elif scope == "finance":
        lines.append("Finance lane: monetary data OK; no compliance audit exports unless explicitly allowed.")
    elif scope not in {"admin"}:
        lines.append("General lane: navigation/help only — no privileged records.")
    if active_url:
        lines.append(f"Active screen: {active_url[:240]}")
    caps = []
    for key, label in (
        ("can_view_financial", "financial"),
        ("can_view_compliance", "compliance/audit"),
        ("can_access_roster", "rosters"),
        ("can_access_grades", "grades"),
        ("can_manage_users", "user administration"),
        ("can_provision_tenants", "tenant provisioning"),
        ("can_view_fleet_ops", "fleet/control-plane ops"),
    ):
        caps.append(f"{label}={'yes' if permissions.get(key) else 'no'}")
    lines.append("Capabilities: " + ", ".join(caps))
    return "\n".join(lines)


def guided_task_allowed_for_permissions(task_key: str, permissions: dict[str, Any]) -> bool:
    """Filter rules-tier topic routing so degraded answers respect RBAC."""
    key = (task_key or "general_chat").strip().lower()
    if key == "general_chat":
        return True
    if key in {"setup_recommend", "control_plane_intelligence"}:
        return bool(permissions.get("can_provision_tenants") or permissions.get("can_view_fleet_ops"))
    if key in {"observability_assistant", "trust_compliance_assistant"}:
        return bool(permissions.get("can_view_fleet_ops") or permissions.get("can_view_compliance"))
    if key == "billing_usage_explain":
        return bool(permissions.get("can_view_financial"))
    if key in {"interop_assistant", "runtime_config_explain", "studio_os_assistant", "config_explain"}:
        return permissions.get("scope") in {"admin", "finance", "teacher"} or permissions.get(
            "can_analyze_data"
        )
    return True


def _permission_labels(user, *, school: Any | None) -> list[str]:
    try:
        from services.ai.knowledge import permission_labels_for_user

        return permission_labels_for_user(user, school=school)
    except Exception:
        return []


def _context_header(user, *, school: Any | None, active_url: str) -> str:
    try:
        from services.ai.tenant_isolation import TenantContextEnforcer

        enforcer = TenantContextEnforcer(user, school=school)
        return enforcer.build_context_header(
            active_url=active_url,
            permission_labels=_permission_labels(user, school=school),
        )
    except Exception:
        return ""


def _attach_rag(request, user_query: str, metadata: dict[str, Any]) -> tuple[str, list[dict[str, Any]]]:
    user = getattr(request, "user", None)
    school = metadata.get("school") or getattr(request, "school", None)
    try:
        from services.ai.knowledge import retrieve_knowledge_snippets
        from services.ai.tenant_isolation import TenantContextEnforcer

        scope = TenantContextEnforcer(user, school=school).resolve_scope().tier
        lines, rows = retrieve_knowledge_snippets(
            user=user,
            school=school,
            user_query=user_query,
            scope=scope,
            limit=4,
        )
        block = "\n".join(lines)[:1200] if lines else ""
        return block, rows
    except Exception:
        return "", []


def copilot_request_shim(
    *,
    user: Any,
    school: Any | None = None,
    active_url: str = "",
    host_kind: str | None = None,
) -> Any:
    """Minimal request-shaped object for RBAC when no Django request exists."""
    from types import SimpleNamespace

    resolved_host = host_kind
    if resolved_host is None:
        try:
            from services.ai.tenant_isolation import PlatformTier, TenantContextEnforcer

            tier = TenantContextEnforcer(user, school=school).resolve_scope().tier
            resolved_host = "manager" if tier == PlatformTier.PLATFORM_MANAGER else "tenant"
        except Exception:
            resolved_host = "tenant"
    path = (active_url or "/").strip() or "/"
    return SimpleNamespace(
        user=user,
        school=school,
        path=path[:500],
        public_host_kind=resolved_host,
    )


def format_engine_room_denial(
    reason: str,
    user: Any,
    permissions: dict[str, Any],
) -> str:
    """Engine-room structured refusal (matches help drawer / SSE shape)."""
    role_label = getattr(user, "role", None) or permissions.get("scope") or "your role"
    scope = permissions.get("scope") or "general"
    return (
        f"**Direct Answer**: {reason}\n"
        f"**Execution Path**: Use a screen your role ({role_label}) can access, "
        f"or contact your school administrator.\n"
        f"**Action Steps**:\n"
        f"1. Rephrase within your access level (scope: {scope}).\n"
        f"2. Ask an admin, bursar, or IT contact if you need a privileged workflow.\n"
        f"**System Bound**: Copilot RBAC enforced — do not infer data beyond your clearance."
    )


def prepare_engine_room_rbac(
    user: Any,
    user_query: str,
    *,
    school: Any | None = None,
    active_url: str = "/",
    task_type: str = "support_suggest",
) -> CopilotRbacEnvelope:
    """RBAC envelope for engine-room help drawer / support SSE (shared with copilot rail)."""
    from services.ai_helpers import normalize_gateway_metadata

    request = copilot_request_shim(user=user, school=school, active_url=active_url)
    permissions = build_copilot_permissions(user, request=request)
    allowed, raw_denial = validate_copilot_query(
        user,
        user_query,
        permissions,
        school=school,
        task_type=task_type,
    )
    if not allowed:
        return CopilotRbacEnvelope(
            allowed=False,
            denial_reason=format_engine_room_denial(raw_denial, user, permissions),
            permissions=permissions,
            prompt="",
            metadata={"outcome": "permission_refusal", "copilot_rbac_enforced": True},
        )

    host_kind = getattr(request, "public_host_kind", None)
    active = str(active_url or "/").strip() or "/"
    directives = rbac_directives_for_permissions(
        permissions,
        active_url=active,
        host_kind=host_kind,
    )
    metadata = normalize_gateway_metadata(
        {
            "request": request,
            "school": school,
            "surface": "engine_room_support",
            "mode": "support",
            "content_sensitivity": "standard",
            "permissions": permissions,
            "user_role": (getattr(user, "role", "") or "").upper(),
            "rbac_scope": permissions.get("scope") or "general",
            "active_url": active,
            "copilot_rbac_enforced": True,
        },
        request=request,
        school=school,
    )
    return CopilotRbacEnvelope(
        allowed=True,
        denial_reason="",
        permissions=permissions,
        prompt=directives,
        metadata=metadata,
    )


def prepare_copilot_invoke(
    request,
    user_query: str,
    *,
    mode: str,
    surface: str,
    task_type: str = "studio_os_assistant",
) -> CopilotRbacEnvelope:
    """Full RBAC + prompt + metadata bundle for ``invoke_with_request``."""
    from apps.portal.ai_surface_context import build_ai_surface_context, merge_surface_metadata
    from apps.portal.views_ai_copilot import build_contextual_prompt
    from services.ai_helpers import normalize_gateway_metadata

    user = getattr(request, "user", None)
    school = getattr(request, "school", None)
    permissions = build_copilot_permissions(user, request=request)
    allowed, denial = validate_copilot_query(
        user,
        user_query,
        permissions,
        school=school,
        task_type=task_type,
    )
    if not allowed:
        return CopilotRbacEnvelope(
            allowed=False,
            denial_reason=denial,
            permissions=permissions,
            prompt="",
            metadata={},
        )

    surface_ctx = build_ai_surface_context(request)
    active_url = str(surface_ctx.get("current_path") or surface_ctx.get("active_url") or "")
    host_kind = getattr(request, "public_host_kind", None)

    role = str(permissions.get("scope") or "general")
    directives = rbac_directives_for_permissions(
        permissions,
        active_url=active_url,
        host_kind=host_kind,
    )
    tenant_header = _context_header(user, school=school, active_url=active_url)
    contextual = build_contextual_prompt(
        user,
        user_query,
        current_path=active_url,
    )

    base_md = normalize_gateway_metadata(
        {
            "request": request,
            "school": school,
            "surface": surface,
            "mode": mode,
            "content_sensitivity": "standard",
            "permissions": permissions,
            "user_role": (getattr(user, "role", "") or "").upper(),
            "rbac_scope": role,
            "active_url": active_url,
            "copilot_rbac_enforced": True,
        },
        request=request,
        school=school,
    )
    base_md = merge_surface_metadata(base_md, surface_ctx)
    rag_block, rag_rows = _attach_rag(request, user_query, base_md)
    if rag_rows:
        base_md["rag_snippets"] = rag_rows

    prompt_parts = [directives]
    if tenant_header:
        prompt_parts.append(tenant_header)
    if rag_block:
        prompt_parts.append(
            "Retrieved internal snippets (use only when relevant; do not exceed RBAC):\n"
            f"{rag_block}"
        )
    prompt_parts.append(contextual)
    prompt = "\n\n".join(p for p in prompt_parts if p).strip()

    return CopilotRbacEnvelope(
        allowed=True,
        denial_reason="",
        permissions=permissions,
        prompt=prompt,
        metadata=base_md,
    )
