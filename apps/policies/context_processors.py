"""
Inject tenant_ctx and global_env (resolved policy) into template context.
Use request.tenant_ctx and global_env in templates instead of reading school.settings/features directly.
"""


def tenant_policy_context(request):
    """Add tenant_ctx and global_env to every template (RunMyCampus blueprint)."""
    ctx = {}
    tenant_ctx = getattr(request, "tenant_ctx", None)
    if tenant_ctx is not None:
        ctx["tenant_ctx"] = tenant_ctx
        try:
            from apps.policies.resolver import get_effective_policy
            school = getattr(request, "school", None)
            ctx["global_env"] = get_effective_policy(school, user=getattr(request, "user", None))
        except Exception:
            ctx["global_env"] = {}
    else:
        ctx["tenant_ctx"] = None
        ctx["global_env"] = {}
    return ctx
