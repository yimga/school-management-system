"""Financial + integrity guardrails for the Migration Cloud apply step.

The financial guardrail is the strongest trust signal for schools — control
totals supplied by the operator (sum of all invoice amounts, count of
students, sum of payments) must match the platform's post-apply totals
before the bundle is marked APPLIED. A mismatch aborts the apply with
``FinancialMismatchError`` so no half-applied financial ledger ever lands
in the tenant.

Operators set ``bundle.expected_totals`` upfront (shape documented on the
model field). The guardrail computes the observed totals from the apply's
``ApplyResult`` + audit trail and raises on any divergence above a small
tolerance (default 0.01 absolute / 0.001 relative — drift-from-rounding).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from typing import Any

from .models import FinancialMismatchError


@dataclass
class GuardrailCheck:
    key: str
    expected: Decimal
    observed: Decimal
    delta: Decimal
    tolerance_abs: Decimal
    tolerance_rel: Decimal
    passed: bool


@dataclass
class GuardrailReport:
    bundle_id: int
    checks: list[GuardrailCheck] = field(default_factory=list)
    failed: list[GuardrailCheck] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.failed

    def to_dict(self) -> dict[str, Any]:
        return {
            "bundle_id": self.bundle_id,
            "ok": self.ok,
            "checks": [
                {
                    "key": c.key,
                    "expected": str(c.expected),
                    "observed": str(c.observed),
                    "delta": str(c.delta),
                    "tolerance_abs": str(c.tolerance_abs),
                    "tolerance_rel": str(c.tolerance_rel),
                    "passed": c.passed,
                }
                for c in self.checks
            ],
            "failed": [
                {"key": c.key, "expected": str(c.expected), "observed": str(c.observed)}
                for c in self.failed
            ],
        }


def _default_tolerances() -> tuple[Decimal, Decimal]:
    """Tolerances from the configurability cascade. Seed fallbacks are 0.01 / 0.001."""
    from apps.migration_cloud import defaults as _mc_defaults
    try:
        abs_tol = Decimal(str(_mc_defaults.get("migration_cloud.guardrail.tolerance_abs")))
    except Exception:  # noqa: BLE001
        abs_tol = Decimal("0.01")
    try:
        rel_tol = Decimal(str(_mc_defaults.get("migration_cloud.guardrail.tolerance_rel")))
    except Exception:  # noqa: BLE001
        rel_tol = Decimal("0.001")
    return abs_tol, rel_tol


_DEFAULT_TOL_ABS = Decimal("0.01")
_DEFAULT_TOL_REL = Decimal("0.001")


def _to_decimal(value: Any) -> Decimal | None:
    if value in (None, ""):
        return None
    try:
        return Decimal(str(value).replace(",", "").replace("$", "").strip())
    except (InvalidOperation, ValueError, TypeError):
        return None


def evaluate_expected_totals(
    *,
    bundle: Any,
    observed: dict[str, Any],
    tolerance_abs: Decimal | None = None,
    tolerance_rel: Decimal | None = None,
) -> GuardrailReport:
    """Compare bundle.expected_totals against observed totals.

    ``observed`` is a dict keyed identically to ``expected_totals``; the
    caller is responsible for computing observed values (see
    :func:`compute_observed_totals` for the standard set).
    """
    if tolerance_abs is None or tolerance_rel is None:
        cascade_abs, cascade_rel = _default_tolerances()
        tolerance_abs = tolerance_abs if tolerance_abs is not None else cascade_abs
        tolerance_rel = tolerance_rel if tolerance_rel is not None else cascade_rel
    expected = bundle.expected_totals or {}
    report = GuardrailReport(bundle_id=getattr(bundle, "pk", 0))
    for key, raw_expected in expected.items():
        exp = _to_decimal(raw_expected)
        obs = _to_decimal(observed.get(key))
        if exp is None:
            continue
        if obs is None:
            check = GuardrailCheck(
                key=key,
                expected=exp,
                observed=Decimal("0"),
                delta=exp,
                tolerance_abs=tolerance_abs,
                tolerance_rel=tolerance_rel,
                passed=False,
            )
            report.checks.append(check)
            report.failed.append(check)
            continue
        delta = abs(exp - obs)
        rel_tol = abs(exp) * tolerance_rel
        passed = delta <= tolerance_abs or delta <= rel_tol
        check = GuardrailCheck(
            key=key,
            expected=exp,
            observed=obs,
            delta=delta,
            tolerance_abs=tolerance_abs,
            tolerance_rel=tolerance_rel,
            passed=passed,
        )
        report.checks.append(check)
        if not passed:
            report.failed.append(check)
    return report


def compute_observed_totals(*, bundle: Any) -> dict[str, str]:
    """Compute the standard observed totals from the bundle's post-apply state.

    Standard keys:
        finance.invoice_total_amount  — sum of Invoice.amount for the school
        finance.invoice_count         — count of Invoice rows for the school
        students.count                — count of StudentProfile rows for the school
        guardians.count               — count of StudentGuardian rows for the school
    """
    totals: dict[str, str] = {}
    school = getattr(bundle, "school", None)
    if school is None:
        return totals
    schema_name = getattr(bundle, "schema_name", "") or ""

    def _run_under_schema(fn):
        if not schema_name:
            return fn()
        try:
            from django_tenants.utils import schema_context
        except ImportError:
            return fn()
        from django.db import connection
        if not hasattr(connection, "set_schema"):
            # Non-tenant DB backend (single-schema sqlite test/dev lane, or an
            # RLS single-schema deploy): entering schema_context raises
            # AttributeError ('DatabaseWrapper' has no 'tenant'). Everything is
            # already in one schema — run as-is. Mirrors orchestrator's guard.
            return fn()
        with schema_context(schema_name):
            return fn()

    try:
        from apps.finance.models import Invoice
    except Exception:  # noqa: BLE001
        Invoice = None
    if Invoice is not None:
        def _finance():
            _inv_fields = {f.name for f in Invoice._meta.get_fields()}
            if "school" in _inv_fields:
                qs = Invoice.objects.filter(school=school)  # tenant-isolation-allow: scoped by the invoice's own school FK (matches finance_lander)
            elif "student" in _inv_fields:
                qs = Invoice.objects.filter(student__school=school)  # tenant-isolation-allow: scoped via student__school=school
            else:
                qs = Invoice.objects.all()  # tenant-isolation-allow: no school field; schema-context isolates
            from django.db.models import Sum, Count

            # Field is ``total_amount`` (NOT ``amount``); Sum("amount") raised
            # FieldError that the caller's broad except swallowed, so the control
            # total was silently never computed.
            agg = qs.aggregate(amount_sum=Sum("total_amount"), c=Count("pk"))
            totals["finance.invoice_total_amount"] = str(agg.get("amount_sum") or Decimal("0"))
            totals["finance.invoice_count"] = str(agg.get("c") or 0)
        try:
            _run_under_schema(_finance)
        except Exception:  # noqa: BLE001
            pass

    try:
        from apps.people.models import StudentProfile
    except Exception:  # noqa: BLE001
        StudentProfile = None
    if StudentProfile is not None:
        def _students():
            totals["students.count"] = str(
                StudentProfile.objects.filter(school=school).count()
                if "school" in {f.name for f in StudentProfile._meta.get_fields()}
                else StudentProfile.objects.count()
            )
        try:
            _run_under_schema(_students)
        except Exception:  # noqa: BLE001
            pass

    try:
        from apps.people.models import StudentGuardian
    except Exception:  # noqa: BLE001
        StudentGuardian = None
    if StudentGuardian is not None:
        def _guardians():
            _g_fields = {f.name for f in StudentGuardian._meta.get_fields()}
            if "student" in _g_fields:
                qs = StudentGuardian.objects.filter(student__school=school)  # tenant-isolation-allow: scoped via student__school=school
            else:
                qs = StudentGuardian.objects.all()  # tenant-isolation-allow: no student link; schema-context isolates
            totals["guardians.count"] = str(qs.count())
        try:
            _run_under_schema(_guardians)
        except Exception:  # noqa: BLE001
            pass

    return totals


def enforce_financial_guardrail(*, bundle: Any) -> GuardrailReport:
    """Compute observed totals and raise FinancialMismatchError on failure.

    Caller should invoke this AFTER the apply commits per-row updates but
    BEFORE flipping bundle.status to APPLIED. The orchestrator catches the
    raise, rolls back via MigrationRun.trigger_rollback() if `apply_atomic`
    isn't on, and re-raises so the API surface returns 409.
    """
    if not bundle.expected_totals:
        return GuardrailReport(bundle_id=getattr(bundle, "pk", 0))
    observed = compute_observed_totals(bundle=bundle)
    report = evaluate_expected_totals(bundle=bundle, observed=observed)
    if not report.ok:
        failed_summary = ", ".join(
            f"{c.key}: expected {c.expected} got {c.observed} (Δ {c.delta})"
            for c in report.failed
        )
        raise FinancialMismatchError(
            f"Financial guardrail failed for bundle {bundle.pk}: {failed_summary}"
        )
    return report
