"""
Inject tenant_ctx and global_env (resolved policy) into template context.
Use request.tenant_ctx and global_env in templates instead of reading school.settings/features directly.
"""
from django.core.exceptions import ObjectDoesNotExist
from django.db import DatabaseError

POLICY_CONTEXT_SOFT_FAILURES = (
    AttributeError,
    DatabaseError,
    ImportError,
    LookupError,
    ObjectDoesNotExist,
    TypeError,
    ValueError,
)


def tenant_policy_context(request):
    """Add tenant_ctx and global_env to every template (RunMyCampus blueprint)."""
    ctx = {}
    tenant_ctx = getattr(request, "tenant_ctx", None)
    if tenant_ctx is not None:
        ctx["tenant_ctx"] = tenant_ctx
        try:
            from apps.policies.policy_registry import get_effective_policy
            school = getattr(request, "school", None)
            policy = get_effective_policy(school, user=getattr(request, "user", None))
            ctx["global_env"] = policy
            # Section 10: expose policy slices for templates (attendance, communication, compliance)
            ctx["tenant_attendance_policy"] = policy.get("attendance") or {}
            ctx["tenant_communication_policy"] = policy.get("communication") or {}
            ctx["tenant_compliance_policy"] = policy.get("compliance") or {}
        except POLICY_CONTEXT_SOFT_FAILURES:
            ctx["global_env"] = {}
            ctx["tenant_attendance_policy"] = {}
            ctx["tenant_communication_policy"] = {}
            ctx["tenant_compliance_policy"] = {}
    else:
        ctx["tenant_ctx"] = None
        ctx["global_env"] = {}
        ctx["tenant_attendance_policy"] = {}
        ctx["tenant_communication_policy"] = {}
        ctx["tenant_compliance_policy"] = {}
    return ctx
