"""Plan usage caps, enforced on the action that exceeds them.

A cap answers exactly one question: *may this school add one more student /
staff member right now?* It must never answer "may this school be used", which
is what the previous ``UsageLimitMiddleware`` did -- it ran in
``process_request`` and returned 403 for EVERY request once a school reached
its cap, so attendance, report cards and fee collection all died together. A
school that cannot operate does not upgrade; it churns. It also cannot reach
our checkout, so the platform's own share of the fees it collects dies with it.

Slack hides message history but keeps the workspace. Shopify stops new actions
but keeps the storefront readable. Same rule here: block the enrolment, keep
the school.

SCOPE (documented, not silently missing): this guard hangs off ``save()`` on
the profile models, the one chokepoint every enrolment path shares. Portal
onboarding, bulk CSV import, admissions kernel and geos lane-2 all create rows
one at a time through ``save()``, so all four ARE capped (there is no single
enrolment service to gate instead). The one path that would bypass the cap is a
raw ``bulk_create()``, which skips ``save()`` -- but no product path uses it on
these models today (verified: zero ``bulk_create`` on Student/TeacherProfile
outside tests), so that escape hatch is theoretical. If one is ever added,
decide deliberately whether an operator bulk-import should be capped mid-batch
or allowed to land.
"""

from __future__ import annotations

from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _

# Billing postures that buy out every usage cap. Mirrors is_feature_enabled's
# escape hatch, so a waived school behaves consistently across features + caps.
WAIVED_BILLING_TYPES: tuple[str, ...] = ("COMPLIMENTARY", "MANUAL_OVERRIDE")


def plan_cap_exceeded(school, *, cap_field: str, model) -> int | None:
    """Return the cap that adding one more row would breach, else ``None``.

    ``None`` means "allowed" -- and it is returned for every reason a cap
    cannot apply: no school, no plan, a waived billing type, or a plan that
    does not set this cap. A plan-less school is unrestricted, which is the
    behaviour live tenants have today and must not lose.
    """
    if school is None:
        return None
    if getattr(school, "billing_type", None) in WAIVED_BILLING_TYPES:
        return None
    plan = getattr(school, "plan", None)
    if plan is None:
        return None
    cap = getattr(plan, cap_field, None)
    if cap is None:
        return None
    current = model.objects.filter(school=school).count()
    if current >= cap:
        return int(cap)
    return None


def enforce_enrolment_cap(instance, *, cap_field: str, model, label: str) -> None:
    """Raise if ``instance`` would be the row that breaches the plan's cap.

    Only checked when the row is being CREATED. Editing or re-saving an
    existing record must keep working at the cap -- a school sitting exactly on
    its limit still has to correct a misspelled name.
    """
    if not instance._state.adding:
        return
    school = getattr(instance, "school", None)
    cap = plan_cap_exceeded(school, cap_field=cap_field, model=model)
    if cap is None:
        return
    raise ValidationError(
        _(
            "Your plan's %(label)s limit of %(cap)s has been reached. "
            "Upgrade to add more — everything already set up keeps working."
        )
        % {"label": label, "cap": cap}
    )
