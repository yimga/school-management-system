"""
Section 22: Identifier policy service for tenant admission number generation and validation.
Uses TenantAdmissionNumberPolicy when present, else get_effective_policy(school)["admissions"] / the site settings singleton.
"""

from __future__ import annotations

import re
from typing import Any, Dict

from django.db import DatabaseError


OPTIONAL_POLICY_ERRORS = (
    AttributeError,
    DatabaseError,
    ImportError,
    TypeError,
    ValueError,
)


def default_school_code_for(school=None, fallback: str = "SCH") -> str:
    raw = (
        (getattr(school, "slug", None) or getattr(school, "name", None) or "")
        .strip()
        .upper()
    )
    if not raw:
        return fallback
    parts = [part for part in re.split(r"[^A-Z0-9]+", raw) if part]
    initials = "".join(part[0] for part in parts[:6])
    if initials:
        return initials[:6]
    return "".join(parts)[:6] or fallback


#: What a node calls itself inside an identifier when nobody has said. Deliberately one
#: character and deliberately not a hostname: it is printed on a school document.
_NODE_NAMESPACE_BY_PROFILE = {"online": "C", "edge": "B", "hybrid": "H"}
_NODE_NAMESPACE_FALLBACK = "C"


def node_identifier_namespace(school=None, policy=None) -> str:
    """WHICH NODE is issuing this identifier, as a short mark that goes in the number.

    An admission number is minted from a LOCAL row count, so two nodes enrolling at the
    same time both believe they are issuing number N. ``student_code`` defaults to the
    admission number and IS on the sync rail, per-school unique -- so the second copy to
    arrive is refused with 422 and that student never lands, on that attempt or any later
    one, because nothing about a retry changes the number.

    A mark that differs per node makes the collision impossible rather than unlikely, and
    it does so without either node asking the other anything -- which is the point,
    because a box must be able to enrol a child with the internet down.

    Resolution runs the configurability cascade, most specific first: the school's own
    admissions policy (it is the school's document, and the school may name the mark),
    then the deployment's explicit setting, then the deployment PROFILE, then a platform
    constant. Sanitised to the character class an identifier can carry, so a stray value
    cannot produce an admission number that fails the school's own pattern.
    """
    from django.conf import settings

    if policy is None and school is not None:
        try:
            policy = get_admissions_policy(school)
        except OPTIONAL_POLICY_ERRORS:
            policy = None
    for candidate in (
        (policy or {}).get("node_code"),
        getattr(settings, "RMC_NODE_IDENTIFIER_NAMESPACE", None),
    ):
        # NOT truncated. A cap here would silently merge two nodes an operator named
        # ANNEXA and ANNEXB back into one mark -- reintroducing, quietly, the exact
        # collision this exists to prevent. An over-long mark instead shows up in the
        # first number issued, where somebody sees it.
        cleaned = re.sub(r"[^A-Z0-9]", "", str(candidate or "").strip().upper())
        if cleaned:
            return cleaned

    profile = str(
        getattr(settings, "RMC_DEPLOYMENT_PROFILE", None) or "online"
    ).strip().lower()
    return _NODE_NAMESPACE_BY_PROFILE.get(profile, _NODE_NAMESPACE_FALLBACK)


def get_admissions_policy(school) -> Dict[str, Any]:
    """
    Return merged admission number config for a school.
    TenantAdmissionNumberPolicy overrides when present and active; else policy resolver + the site settings singleton.
    """
    try:
        from apps.siteconfig.models import TenantAdmissionNumberPolicy

        if school is None:
            raise ValueError("school required")
        policy_model = TenantAdmissionNumberPolicy.objects.filter(
            school=school, is_active=True
        ).first()
        if policy_model:
            template = (getattr(policy_model, "template", None) or "").strip()
            return {
                "school_code": (
                    getattr(policy_model, "school_code", None)
                    or default_school_code_for(school)
                ).upper(),
                "admission_number_strategy": getattr(policy_model, "strategy", "FULL")
                or "FULL",
                "admission_number_template": template,
                "admission_number_pattern": (
                    getattr(policy_model, "pattern", None) or ""
                ).strip(),
                "admission_number_mode": "AUTO_OR_MANUAL",
                "seq_width": getattr(policy_model, "seq_width", 4),
                "reset_frequency": getattr(policy_model, "reset_frequency", "YEARLY"),
            }
    except OPTIONAL_POLICY_ERRORS:
        pass
    from apps.policies.policy_registry import get_effective_policy

    out = get_effective_policy(school)
    return out.get("admissions") or {}


def render_admission_number(
    policy: Dict[str, Any],
    *,
    year_2digit: str,
    school_code: str,
    seq_4digit: str,
    spec_code: str,
    class_segment: str,
    node_code: str,
) -> str:
    """THE shape of an admission number. One implementation, deliberately.

    The preview a school configures against and the number it is actually issued used to
    be built by two separate copies of this logic, and they had already drifted: the
    preview knew nothing about the node mark, so a school would have set its
    `admission_number_pattern` against a sample that no real enrolment could match, and a
    template using {node_code} raised KeyError into a bare `except: pass` and silently
    produced a number of an entirely different shape.

    A format the school validates against has to be the format the school is given.
    """
    template = (policy.get("admission_number_template") or "").strip()
    if template:
        try:
            return template.format(
                year_2digit=year_2digit,
                school_code=school_code,
                seq_4digit=seq_4digit,
                spec_code=spec_code,
                class_segment=class_segment,
                node_code=node_code,
            )
        except (KeyError, IndexError):
            # A placeholder this version does not offer. Falling through to a built-in
            # strategy keeps enrolment working rather than failing it on a config typo.
            pass

    strategy = policy.get("admission_number_strategy") or "FULL"
    if strategy == "YEAR_SEQ":
        return f"{year_2digit}{school_code}{node_code}{seq_4digit}"
    if strategy == "SEQ_ONLY":
        # Even here. SEQ_ONLY is the shortest form a school can choose, and it is exactly
        # the form two nodes are most certain to collide on.
        return f"{node_code}{seq_4digit}"
    return (
        f"{year_2digit}{school_code}{node_code}{seq_4digit}{spec_code}{class_segment}"
    )


def preview_admission_number(
    school,
    *,
    year_2digit: str = "26",
    school_code: str = "",
    seq_4digit: str = "0001",
    spec_code: str = "XX",
    class_segment: str = "00",
) -> str:
    """
    Section 22.2: Return a sample admission number for the given policy (for setup preview).
    """
    policy = get_admissions_policy(school)
    school_code = (
        school_code or policy.get("school_code") or default_school_code_for(school)
    ).upper()
    # The mark THIS node would really issue, not a placeholder: the whole point of a
    # preview is that a school can set its pattern against what it will actually get.
    return render_admission_number(
        policy,
        year_2digit=year_2digit,
        school_code=school_code,
        seq_4digit=seq_4digit,
        spec_code=spec_code,
        class_segment=class_segment,
        node_code=node_identifier_namespace(school, policy=policy),
    )


def pattern_accepts_own_numbers(school, *, policy=None) -> tuple:
    """Would this school's own pattern reject the numbers this node now issues?

    A school stores `admission_number_pattern` and `StudentProfile.clean()` enforces it.
    Adding the node mark makes every issued number one character longer, so a pattern
    written before the mark existed -- one pinning an exact length, say -- now rejects
    the very numbers this code generates. Every enrolment of the term would fail
    validation against a rule the school itself set, and the message would point at the
    number rather than at the pattern.

    Returns ``(ok, sample, pattern)``. ``ok`` is True when there is no pattern to fail,
    when the pattern is unusable as a regex (validation cannot enforce what it cannot
    compile), or when the sample matches. Checking rather than assuming, because the
    answer is per school and nobody can eyeball 500 of them.
    """
    policy = policy if policy is not None else get_admissions_policy(school)
    pattern = (policy.get("admission_number_pattern") or "").strip()
    mark = node_identifier_namespace(school, policy=policy)
    sample = render_admission_number(
        policy,
        year_2digit="26",
        school_code=(
            policy.get("school_code") or default_school_code_for(school)
        ).upper(),
        seq_4digit="0001",
        spec_code="GEN",
        class_segment="F1",
        node_code=mark,
    )
    if not pattern:
        return True, sample, pattern
    try:
        return bool(re.match(pattern, sample)), sample, pattern
    except re.error:
        return True, sample, pattern

def validate_admission_number(school, value: str) -> bool:
    """Return True if value matches the policy pattern for this school."""
    if not value or not value.strip():
        return True
    policy = get_admissions_policy(school)
    pattern = (policy.get("admission_number_pattern") or "").strip()
    if not pattern:
        pattern = r"^(\d{2}[A-Z0-9]{2,10}\d{4}[A-Z0-9]{2,6}[A-Z0-9]{1,4})|(\d{2}-[A-Z0-9]{2,10}-\d{4}-[A-Z0-9]{2,6}-[A-Z0-9]{1,4})$"
    try:
        return bool(re.match(pattern, value.strip()))
    except re.error:
        return True
