"""Policy Decision Point (Move 3).

A single entry-point function ``decide(subject, action, resource, *, school=None,
context=None)`` that evaluates `PolicyRule` rows and returns a
:class:`Decision` carrying effect (`allow` / `deny` / `implicit_deny`),
the matched rule (if any), and a human-readable explanation.

Every call writes a ``PolicyDecisionLog`` row.

### Rule DSL

`PolicyRule.subject_match` keys (all optional, ANDed):
  - ``role``: required role string equality
  - ``role_any``: list of acceptable role strings
  - ``user_id``: specific user.pk

`PolicyRule.action_match` keys:
  - ``actions``: list of actions. ``"*"`` matches anything.

`PolicyRule.resource_match` keys:
  - ``entity``: required entity type equality (e.g. "student")
  - ``entity_any``: list of acceptable entities
  - ``field``: specific field name (e.g. "ssn") — required exact match
  - ``sensitivity_tier_at_or_above``: minimum tier the rule covers
  - ``compliance_tag``: a single tag the resource must carry to match

`PolicyRule.conditions` is a list of predicate dicts ANDed together:
  ``{"attr": "<dotted.path>", "op": "<eq|ne|lt|lte|gt|gte|in|contains>",
     "value": <literal>}``
The ``attr`` is resolved against the merged context (subject + resource + extras).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable

from django.db import transaction

from apps.policies.models import PolicyDecisionLog, PolicyRule


_TIER_ORDER = {"public": 0, "internal": 1, "restricted": 2, "confidential": 3, "secret": 4}


@dataclass(frozen=True)
class Decision:
    effect: str  # "allow" | "deny" | "implicit_deny"
    matched_rule_id: int | None
    reason: str

    @property
    def allowed(self) -> bool:
        return self.effect == "allow"


def _resolve_attr(path: str, ctx: dict) -> Any:
    """Resolve a dotted attr path against ctx. ``subject.role`` reads ctx['subject']['role']."""

    cur: Any = ctx
    for part in (path or "").split("."):
        if part == "":
            continue
        if isinstance(cur, dict):
            cur = cur.get(part)
        else:
            cur = getattr(cur, part, None)
        if cur is None:
            return None
    return cur


def _evaluate_condition(cond: dict, ctx: dict) -> bool:
    attr = _resolve_attr(cond.get("attr", ""), ctx)
    op = (cond.get("op") or "").lower()
    val = cond.get("value")
    if op == "eq":
        return attr == val
    if op == "ne":
        return attr != val
    if op == "in":
        try:
            return attr in val
        except TypeError:
            return False
    if op == "contains":
        try:
            return val in attr
        except TypeError:
            return False
    if op in ("lt", "lte", "gt", "gte"):
        try:
            a, b = attr, val
            if op == "lt":
                return a < b
            if op == "lte":
                return a <= b
            if op == "gt":
                return a > b
            return a >= b
        except TypeError:
            return False
    return False


def _matches_subject(rule: PolicyRule, subject: dict) -> bool:
    sm = rule.subject_match or {}
    if not sm:
        return True
    role = (subject.get("role") or "").upper()
    if "role" in sm and (sm["role"] or "").upper() != role:
        return False
    if "role_any" in sm and role not in {(r or "").upper() for r in sm["role_any"]}:
        return False
    if "user_id" in sm and str(subject.get("user_id")) != str(sm["user_id"]):
        return False
    return True


def _matches_action(rule: PolicyRule, action: str) -> bool:
    am = rule.action_match or {}
    actions = list(am.get("actions") or [])
    if not actions:
        return True
    return action in actions or "*" in actions


def _inject_rebac_context(ctx: dict, subject: dict, school) -> None:
    """Expose graph ``can`` edges to PDP conditions (``rebac.allowed``)."""
    perm = (ctx.get("resource") or {}).get("permission_code") or ""
    uid = subject.get("user_id")
    if not perm or not uid or school is None:
        return
    try:
        from apps.accounts.rebac import check_permission_token, rebac_enabled

        if not rebac_enabled():
            return
        from apps.accounts.models import User

        user = User.objects.filter(pk=uid).first()
        ctx["rebac"] = {
            "permission_code": perm,
            "allowed": bool(
                user and check_permission_token(user, perm, school=school),
            ),
        }
    except Exception:
        ctx["rebac"] = {"permission_code": perm, "allowed": False}


def _matches_resource(rule: PolicyRule, resource: dict) -> bool:
    rm = rule.resource_match or {}
    if not rm:
        return True
    entity = (resource.get("entity") or "").lower()
    if "entity" in rm and (rm["entity"] or "").lower() != entity:
        return False
    if "entity_any" in rm and entity not in {(e or "").lower() for e in rm["entity_any"]}:
        return False
    if "field" in rm and (rm["field"] or "") != (resource.get("field") or ""):
        return False
    if "compliance_tag" in rm:
        tags = list(resource.get("compliance_tags") or [])
        if rm["compliance_tag"] not in tags:
            return False
    if "sensitivity_tier_at_or_above" in rm:
        res_tier = _TIER_ORDER.get(resource.get("sensitivity_tier") or "internal", 1)
        min_tier = _TIER_ORDER.get(rm["sensitivity_tier_at_or_above"], 0)
        if res_tier < min_tier:
            return False
    return True


def _applicable_rules(school) -> Iterable[PolicyRule]:
    qs = PolicyRule.objects.filter(is_active=True)  # tenant-isolation-allow: policy-decision-rules-global-catalog-lookup
    if school is not None:
        qs = qs.filter(models_school_filter_for(school))
    else:
        qs = qs.filter(school__isnull=True)
    return qs.order_by("priority", "code")


def models_school_filter_for(school):
    """Q-object: rules that are tenant-specific to this school OR platform-wide."""

    from django.db.models import Q

    return Q(school__isnull=True) | Q(school=school)


@transaction.atomic
def decide(
    subject: dict,
    action: str,
    resource: dict,
    *,
    school=None,
    context: dict | None = None,
    log: bool = True,
) -> Decision:
    """Evaluate rules and return a Decision.

    Parameters
    ----------
    subject : dict
        At minimum ``{"user_id": <id-or-None>, "role": "TEACHER"}``.
    action : str
        Verb being attempted: ``"read" | "write" | "delete" | "export" | ...``
    resource : dict
        Identifies what's being accessed; conventionally
        ``{"entity": "student", "id": <pk>, "field": "ssn",
           "sensitivity_tier": "restricted", "compliance_tags": ["pii"]}``.
    school : School instance or None
        Tenant scope. None for platform-wide checks.
    context : dict
        Free-form extra attributes available to conditions.

    Returns
    -------
    Decision
    """

    ctx = {
        "subject": dict(subject or {}),
        "resource": dict(resource or {}),
        **(context or {}),
    }
    _inject_rebac_context(ctx, subject, school)
    matched_rule: PolicyRule | None = None
    effect = "implicit_deny"
    reason = "no rule matched"

    for rule in _applicable_rules(school):
        if not _matches_subject(rule, ctx["subject"]):
            continue
        if not _matches_action(rule, action):
            continue
        if not _matches_resource(rule, ctx["resource"]):
            continue
        if rule.conditions and not all(_evaluate_condition(c, ctx) for c in rule.conditions):
            continue
        matched_rule = rule
        effect = rule.effect
        reason = (
            f"{rule.effect}: rule {rule.code!r} (priority {rule.priority}) matched "
            f"subject={ctx['subject'].get('role','?')} action={action} "
            f"entity={ctx['resource'].get('entity','?')}"
        )
        if rule.description:
            reason += f" — {rule.description[:160]}"
        break

    if log:
        try:
            PolicyDecisionLog.objects.create(
                school=school,
                subject_id=str(subject.get("user_id") or "")[:120],
                subject_role=(subject.get("role") or "")[:64],
                action=action[:64],
                resource_type=(resource.get("entity") or "")[:120],
                resource_id=str(resource.get("id") or "")[:190],
                effect=effect,
                matched_rule=matched_rule,
                decision_reason=reason[:5000],
                context_snapshot={
                    "subject": ctx["subject"],
                    "resource": ctx["resource"],
                },
            )
        except Exception:
            # Decision logging failure must not block the actual decision.
            pass

    return Decision(
        effect=effect,
        matched_rule_id=matched_rule.pk if matched_rule else None,
        reason=reason,
    )


# Convenience wrappers used at call sites:


def allowed(subject: dict, action: str, resource: dict, **kw) -> bool:
    return decide(subject, action, resource, **kw).allowed


def require(subject: dict, action: str, resource: dict, **kw) -> Decision:
    d = decide(subject, action, resource, **kw)
    if not d.allowed:
        from django.core.exceptions import PermissionDenied

        raise PermissionDenied(d.reason)
    return d
