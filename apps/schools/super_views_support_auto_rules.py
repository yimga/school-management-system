"""v4.00.42 — AutoTicketRule operator UI.

Surfaces the existing ``apps.customersuccess.models.AutoTicketRule`` (until
now admin-only) so operators can list, create, toggle, and edit auto-ticket
triggers from the support workbench.
"""

from __future__ import annotations

import json

from django.contrib import messages
from django.shortcuts import redirect, render
from django.views.decorators.http import require_http_methods

from apps.platform_runtime.operator_identity import (
    PLATFORM_SCOPE_TEAM_MANAGE,
    PLATFORM_SCOPE_TEAM_READ,
    require_platform_scope,
)


@require_platform_scope(PLATFORM_SCOPE_TEAM_READ)
def support_auto_rules_dashboard(request):
    """List + inline-create AutoTicketRule entries."""
    from apps.customersuccess.models import AutoTicketRule

    rules = list(AutoTicketRule.objects.order_by("trigger", "name"))
    return render(
        request,
        "schools/super_support_auto_rules.html",
        {
            "rules": rules,
            "trigger_choices": AutoTicketRule.Trigger.choices,
            "active_count": sum(1 for r in rules if r.is_active),
            "inactive_count": sum(1 for r in rules if not r.is_active),
        },
    )


@require_platform_scope(PLATFORM_SCOPE_TEAM_MANAGE)
@require_http_methods(["POST"])
def support_auto_rules_save(request):
    """Create or update an AutoTicketRule from the operator UI."""
    from apps.customersuccess.models import AutoTicketRule

    action = (request.POST.get("action") or "create").strip().lower()
    rule_id = (request.POST.get("rule_id") or "").strip()

    if action == "delete" and rule_id:
        try:
            AutoTicketRule.objects.filter(pk=int(rule_id)).delete()
            messages.success(request, "Rule deleted.")
        except (TypeError, ValueError):
            messages.error(request, "Invalid rule id.")
        return redirect("super:support_auto_rules_dashboard")

    if action == "toggle" and rule_id:
        try:
            rule = AutoTicketRule.objects.get(pk=int(rule_id))
            rule.is_active = not rule.is_active
            rule.save(update_fields=["is_active", "updated_at"])
            messages.success(
                request,
                f"Rule {'activated' if rule.is_active else 'deactivated'}.",
            )
        except (AutoTicketRule.DoesNotExist, TypeError, ValueError):
            messages.error(request, "Rule not found.")
        return redirect("super:support_auto_rules_dashboard")

    # create / update
    name = (request.POST.get("name") or "").strip()[:120]
    trigger = (request.POST.get("trigger") or "").strip()
    raw_config = (request.POST.get("config") or "{}").strip()
    is_active = request.POST.get("is_active") in ("1", "true", "on", "yes")
    if not name or not trigger:
        messages.error(request, "Name and trigger are required.")
        return redirect("super:support_auto_rules_dashboard")
    try:
        config = json.loads(raw_config or "{}")
        if not isinstance(config, dict):
            raise ValueError("config must be an object")
    except (TypeError, ValueError) as exc:
        messages.error(request, f"Invalid config JSON: {exc}")
        return redirect("super:support_auto_rules_dashboard")
    valid_triggers = dict(AutoTicketRule.Trigger.choices)
    if trigger not in valid_triggers:
        messages.error(request, "Unknown trigger.")
        return redirect("super:support_auto_rules_dashboard")

    if rule_id:
        try:
            rule = AutoTicketRule.objects.get(pk=int(rule_id))
        except (AutoTicketRule.DoesNotExist, TypeError, ValueError):
            messages.error(request, "Rule not found.")
            return redirect("super:support_auto_rules_dashboard")
        rule.name = name
        rule.trigger = trigger
        rule.config = config
        rule.is_active = is_active
        rule.save()
        messages.success(request, "Rule updated.")
    else:
        AutoTicketRule.objects.create(
            name=name,
            trigger=trigger,
            config=config,
            is_active=is_active,
        )
        messages.success(request, "Rule created.")
    return redirect("super:support_auto_rules_dashboard")
