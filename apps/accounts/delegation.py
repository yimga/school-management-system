"""
Delegation (Out of Office / Acting) helpers.
Resolve effective approvers for a workflow: configurable roles + delegate substitution.
No hardcoded role names; all from SiteSettings.
"""
from __future__ import annotations

from django.contrib.auth import get_user_model
from django.db.models import Q
from django.utils import timezone

from apps.siteconfig.models import SiteSettings

User = get_user_model()

# Workflow keys used in scope and in get_effective_approvers
WORKFLOW_SYLLABUS_APPROVAL = "syllabus_approval"
WORKFLOW_GRADE_APPROVAL = "grade_approval"


def _normalize_roles(raw_roles) -> list[str]:
    if not raw_roles:
        return []
    if isinstance(raw_roles, str):
        raw_roles = [raw_roles]
    return [str(r).upper().strip() for r in raw_roles if r]


def _user_has_any_role(user: User, roles: list[str]) -> bool:
    if not user or not roles:
        return False
    if getattr(user, "is_superuser", False):
        return True
    role_upper = (getattr(user, "role", "") or "").upper()
    if role_upper in roles:
        return True
    if hasattr(user, "roles") and user.roles.exists():
        if user.roles.filter(code__in=roles).exists():
            return True
    return False


def get_approval_roles_for_workflow(workflow_key: str) -> list[str]:
    """Return list of role codes that can approve for this workflow (from SiteSettings)."""
    site = SiteSettings.get_solo()
    if workflow_key == WORKFLOW_SYLLABUS_APPROVAL:
        roles = getattr(site, "syllabus_approval_roles", None)
    elif workflow_key == WORKFLOW_GRADE_APPROVAL:
        roles = getattr(site, "grade_approval_roles", None)
    else:
        return []
    return _normalize_roles(roles)


def get_users_with_roles(role_codes: list[str]):
    """Return queryset of users who have any of the given roles (role field or roles M2M)."""
    if not role_codes:
        return User.objects.none()
    return User.objects.filter(
        Q(role__in=role_codes) | Q(roles__code__in=role_codes)
    ).distinct()


def get_active_delegations_for_delegators(delegator_user_ids: list[int], workflow_key: str | None = None):
    """
    Return active Delegation objects where delegator is in the given set.
    If workflow_key is set and delegation has scope, only include if scope is empty or contains workflow_key.
    """
    from apps.accounts.models import Delegation

    now = timezone.now()
    qs = Delegation.objects.filter(
        delegator_id__in=delegator_user_ids,
        is_active=True,
        start_date__lte=now,
    ).filter(
        Q(extended_end_date__isnull=True, end_date__gte=now)
        | Q(extended_end_date__isnull=False, extended_end_date__gte=now)
    )
    if workflow_key:
        # scope empty or None = "all"; else scope must contain workflow_key (filter in Python for DB compatibility)
        delegations = list(qs)
        filtered_ids = [d.id for d in delegations if not d.scope or workflow_key in (d.scope if isinstance(d.scope, list) else [])]
        return Delegation.objects.filter(id__in=filtered_ids) if filtered_ids else qs.none()
    return qs


def get_effective_approvers(workflow_key: str):
    """
    Return list of User objects who can approve for this workflow:
    - Users with an approval role for this workflow (from SiteSettings)
    - Plus delegates who are currently acting for any of those users (when they are OOO)
    So if the Dean is away and delegated to the HOD, the HOD appears in the result.
    """
    role_codes = get_approval_roles_for_workflow(workflow_key)
    if not role_codes:
        return list(User.objects.none())

    primary_approvers = get_users_with_roles(role_codes)
    primary_ids = list(primary_approvers.values_list("id", flat=True))
    effective = set(primary_ids)

    # Add delegates for any primary approver who is currently OOO
    active_delegations = get_active_delegations_for_delegators(primary_ids, workflow_key)
    for d in active_delegations.select_related("delegate"):
        effective.add(d.delegate_id)

    return list(User.objects.filter(id__in=effective).order_by("username"))


def get_active_delegation_for_delegate(user: User):
    """Return the active Delegation where this user is the delegate, if any."""
    from apps.accounts.models import Delegation

    now = timezone.now()
    return (
        Delegation.objects.filter(
            delegate=user,
            is_active=True,
            start_date__lte=now,
        )
        .filter(
            Q(extended_end_date__isnull=True, end_date__gte=now)
            | Q(extended_end_date__isnull=False, extended_end_date__gte=now)
        )
        .select_related("delegator")
        .first()
    )


def user_is_acting_for(user: User, delegator: User) -> bool:
    """True if user is currently the delegate (acting) for delegator."""
    d = get_active_delegation_for_delegate(user)
    return d is not None and d.delegator_id == delegator.id


def can_user_approve_for_workflow(user: User, workflow_key: str) -> bool:
    """True if user can approve (has role or is acting delegate for someone who has role)."""
    if not user or not user.is_authenticated:
        return False
    approvers = get_effective_approvers(workflow_key)
    return user in approvers


def log_delegation_action(delegation, actor, action_taken, object_repr="", object_id=None, content_type=None, metadata=None):
    """Record an action taken by a delegate for catch-up and audit."""
    from apps.accounts.models import DelegationActionLog

    return DelegationActionLog.objects.create(
        delegation=delegation,
        actor=actor,
        acting_for=delegation.delegator,
        action_taken=action_taken,
        object_repr=object_repr or "",
        object_id=object_id,
        content_type=content_type,
        metadata=metadata or {},
    )


def get_delegation_role_mapping():
    """Return who can delegate to whom from SiteSettings (dict: delegator_role -> [delegate_roles])."""
    site = SiteSettings.get_solo()
    mapping = getattr(site, "delegation_role_mapping", None) or {}
    if isinstance(mapping, dict):
        return mapping
    return {}


def get_allowed_delegate_role_codes(delegator_user: User) -> list[str]:
    """Return role codes the delegator is allowed to choose as delegate (from SiteSettings role mapping)."""
    if not delegator_user or not delegator_user.is_authenticated:
        return []
    mapping = get_delegation_role_mapping()
    role_upper = (getattr(delegator_user, "role", "") or "").upper()
    if not role_upper:
        return []
    allowed = mapping.get(role_upper)
    if not allowed:
        return []
    return _normalize_roles(allowed)


def get_allowed_delegate_queryset(delegator_user: User):
    """Return queryset of users the delegator can assign as delegate (excluding self)."""
    role_codes = get_allowed_delegate_role_codes(delegator_user)
    if not role_codes:
        return User.objects.none()
    return get_users_with_roles(role_codes).exclude(pk=delegator_user.pk).filter(is_active=True).order_by("username")


def user_can_create_delegation(user: User) -> bool:
    """True if the user's role appears in delegation_role_mapping (can assign a delegate)."""
    return len(get_allowed_delegate_role_codes(user)) > 0


# Scope choices for delegation UI (workflow keys)
SCOPE_CHOICES = [
    (WORKFLOW_SYLLABUS_APPROVAL, "Syllabus approvals"),
    (WORKFLOW_GRADE_APPROVAL, "Grade approvals"),
]
