"""Children's-privacy (COPPA / FERPA-minor) age-gate primitive.

RunMyCampus provisions student accounts *through the school* — the
FTC-recognised "school as agent" basis for ed-tech under COPPA
(16 CFR §312.5(a)(1); FTC COPPA FAQ Section M). Every account-creation
surface on the platform is school- or operator-mediated (there is no
anonymous public self-registration of a child), so the operative consent
basis for those flows is :attr:`ConsentBasis.SCHOOL_AUTHORIZATION`.

This module makes that basis **explicit and enforceable** instead of implicit:

  * :func:`evaluate_coppa_gate` is the single decision point. A minor
    (age < the configured threshold, default 13) may only have an account
    created through a flow that carries a real consent basis — school
    authorization or verifiable guardian consent. A genuinely self-service
    (unauthenticated, basis-less) creation of a minor's account is refused.
  * It is **data-minimising by construction**: callers pass an age *or* a
    date of birth only so this module can DERIVE a coarse minor/adult
    classification. The raw date of birth is never returned, stored, or
    logged by anything here — only the derived ``is_minor`` flag and a
    coarse ``age_band`` are worth persisting downstream.

The primitive is pure (no DB, no I/O) so it is cheap to call on every
account-creation path and trivially unit-testable.
"""

from __future__ import annotations

import datetime as _dt
from dataclasses import dataclass
from enum import Enum
from typing import Optional, Union

from django.conf import settings

# COPPA's operative threshold: personal information "from a child" means a
# person under 13 (16 CFR §312.2). Overridable per-deployment for regimes with
# a different age of digital consent (e.g. GDPR Art. 8 allows 13–16).
DEFAULT_COPPA_MIN_AGE = 13


def coppa_min_age() -> int:
    """Configured minimum self-service age; falls back to the COPPA default.

    Reads ``settings.COPPA_SELF_SERVICE_MIN_AGE`` (env-overridable) so nothing is
    hardcoded at the call sites. A non-positive / unparseable value degrades to
    :data:`DEFAULT_COPPA_MIN_AGE` rather than disabling the gate.
    """
    try:
        value = int(getattr(settings, "COPPA_SELF_SERVICE_MIN_AGE", DEFAULT_COPPA_MIN_AGE))
    except (TypeError, ValueError):
        return DEFAULT_COPPA_MIN_AGE
    return value if value > 0 else DEFAULT_COPPA_MIN_AGE


class ConsentBasis(str, Enum):
    """The legal basis under which a minor's account may be created."""

    #: School acts as the parent's agent for ed-tech (COPPA §312.5(a)(1)).
    SCHOOL_AUTHORIZATION = "school_authorization"
    #: A verifiable guardian consent record is on file for this student.
    GUARDIAN_CONSENT = "guardian_consent"
    #: No consent basis — a bare self-service attempt.
    NONE = "none"


_VALID_BASES = frozenset(
    {ConsentBasis.SCHOOL_AUTHORIZATION.value, ConsentBasis.GUARDIAN_CONSENT.value}
)


def _coerce_date(dob: Union[_dt.date, _dt.datetime, str, None]) -> Optional[_dt.date]:
    """Best-effort coerce a DOB (``date``/``datetime``/ISO string) to a ``date``."""
    if dob is None or dob == "":
        return None
    if isinstance(dob, _dt.datetime):
        return dob.date()
    if isinstance(dob, _dt.date):
        return dob
    text = str(dob).strip()
    if not text:
        return None
    try:
        # Accept an ISO date or the date prefix of an ISO datetime.
        return _dt.date.fromisoformat(text[:10])
    except ValueError:
        return None


def derive_age(
    dob: Union[_dt.date, _dt.datetime, str, None],
    *,
    today: Optional[_dt.date] = None,
) -> Optional[int]:
    """Whole-years age from a date of birth; ``None`` if absent/unparseable.

    Birthday-correct: a person born 2013-07-31 is 12 until 2026-07-31. A future
    DOB (clock skew / typo) yields ``None`` rather than a negative age.
    """
    born = _coerce_date(dob)
    if born is None:
        return None
    ref = today or _dt.date.today()
    if born > ref:
        return None
    years = ref.year - born.year - ((ref.month, ref.day) < (born.month, born.day))
    return max(0, years)


@dataclass(frozen=True)
class AgeGateDecision:
    """Outcome of :func:`evaluate_coppa_gate`. Carries no raw DOB."""

    allowed: bool
    is_minor: Optional[bool]
    reason: str
    requires_guardian_consent: bool
    min_age: int
    #: Coarse, non-PII band: ``"adult"`` | ``"minor"`` | ``"unknown"``.
    age_band: str


def _normalise_basis(consent_basis: Union[ConsentBasis, str, None]) -> str:
    if isinstance(consent_basis, ConsentBasis):
        return consent_basis.value
    return str(consent_basis or "").strip().lower()


def consent_basis_is_sufficient_for_minor(
    consent_basis: Union[ConsentBasis, str, None],
) -> bool:
    """True iff ``consent_basis`` is a real basis to create a minor's account.

    For callers that already carry a persisted ``is_minor`` flag (e.g. an
    account-creation service downstream of the DOB boundary) and therefore no
    longer have the raw age. Equivalent to the minor branch of
    :func:`evaluate_coppa_gate`.
    """
    return _normalise_basis(consent_basis) in _VALID_BASES


def evaluate_coppa_gate(
    *,
    age: Optional[int],
    consent_basis: Union[ConsentBasis, str, None],
    min_age: Optional[int] = None,
) -> AgeGateDecision:
    """Decide whether a self-service account creation may proceed.

    * ``age >= threshold`` → allowed (adult); no consent needed.
    * ``age <  threshold`` → allowed **only** with a real consent basis
      (:attr:`ConsentBasis.SCHOOL_AUTHORIZATION` or
      :attr:`ConsentBasis.GUARDIAN_CONSENT`); otherwise **refused** with
      ``requires_guardian_consent=True``.
    * ``age is None`` → not blocked here (school/operator flows legitimately
      omit DOB); ``is_minor`` is ``None`` and the caller decides. This keeps
      the gate from breaking the school-as-agent flows that never collect a
      birth date while still refusing a *basis-less* creation once an age that
      proves the subject is a child is known.
    """
    threshold = int(min_age) if min_age else coppa_min_age()
    has_basis = _normalise_basis(consent_basis) in _VALID_BASES

    if age is None:
        return AgeGateDecision(
            allowed=True,
            is_minor=None,
            reason="age_unknown",
            requires_guardian_consent=False,
            min_age=threshold,
            age_band="unknown",
        )

    if age >= threshold:
        return AgeGateDecision(
            allowed=True,
            is_minor=False,
            reason="adult",
            requires_guardian_consent=False,
            min_age=threshold,
            age_band="adult",
        )

    if has_basis:
        return AgeGateDecision(
            allowed=True,
            is_minor=True,
            reason=f"minor_{_normalise_basis(consent_basis)}",
            requires_guardian_consent=False,
            min_age=threshold,
            age_band="minor",
        )

    return AgeGateDecision(
        allowed=False,
        is_minor=True,
        reason="minor_requires_consent",
        requires_guardian_consent=True,
        min_age=threshold,
        age_band="minor",
    )


__all__ = [
    "DEFAULT_COPPA_MIN_AGE",
    "coppa_min_age",
    "ConsentBasis",
    "derive_age",
    "AgeGateDecision",
    "evaluate_coppa_gate",
    "consent_basis_is_sufficient_for_minor",
]
