"""
Section 7: Multi-Tenant Extensibility & Nuance Engine.

JSON-Logic only, no raw code. apply_nuance(school, hook_point, context) returns result;
context is scrubbed to allowed keys per hook. Timeout 50ms. verify_nuance_safety before save.
"""

from __future__ import annotations

import logging
import signal
import threading
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeoutError
from typing import Any

from apps.platform_runtime.structured_logging import log_exception_with_context

logger = logging.getLogger(__name__)

# Typed exceptions for §2.4 broad-except replacement (allowlist 0).
_NUANCE_EVAL_ERRORS = (
    TypeError,
    ValueError,
    KeyError,
    AttributeError,
    ZeroDivisionError,
    RecursionError,
    OverflowError,
)

# Hook points and allowed context keys (whitelist). Add keys as needed.
# student_tags: list of tag names for the student (InformationTag); use in JSON-Logic with "in" op.
HOOK_REGISTRY = {
    "tuition_calc": [
        "fee",
        "student_id",
        "gpa",
        "sibling_count",
        "years_enrolled",
        "is_staff_child",
        "student_tags",
    ],
    "grade_weight": ["score", "weight", "category", "student_id"],
    "attendance_alert": ["attendance_rate", "student_id", "term_id"],
    "fee_discount": [
        "fee",
        "gpa",
        "sibling_count",
        "attendance_rate",
        "is_staff_child",
        "student_tags",
    ],
    "scholarship_eligibility": [
        "gpa",
        "sibling_count",
        "student_tags",
        "custom_attributes",
        "attendance_rate",
        "fee_status",
    ],
    "report_card_avg": [
        "scores_by_subject",
        "coefficients",
        "scale_max",
        "weighted_sum",
        "coefficient_total",
        "value",
    ],  # regional grading (e.g. Cameroon coefficient)
    "generic": ["value"],  # minimal for custom hooks
}

# Hook points evaluated via evaluate_json_logic on inline JSON (not CustomNuance rows).
VIRTUAL_HOOK_POINTS = frozenset({"scholarship_eligibility"})

HOOK_POINT_LABELS: dict[str, str] = {
    "tuition_calc": "Tuition / fee calculation",
    "grade_weight": "Grade weighting",
    "attendance_alert": "Attendance alerts",
    "fee_discount": "Fee discount eligibility",
    "report_card_avg": "Report card weighted average",
    "generic": "Generic (custom)",
    "scholarship_eligibility": "Scholarship eligibility (inline JSON on Scholarship)",
}


def model_hook_point_choices() -> list[tuple[str, str]]:
    """Django CharField choices for CustomNuance / PendingNuance (HOOK_REGISTRY minus virtual)."""
    return [
        (key, HOOK_POINT_LABELS.get(key, key.replace("_", " ").title()))
        for key in HOOK_REGISTRY
        if key not in VIRTUAL_HOOK_POINTS
    ]


def database_hook_points() -> frozenset[str]:
    """Hook points that may be stored on CustomNuance."""
    return frozenset(k for k in HOOK_REGISTRY if k not in VIRTUAL_HOOK_POINTS)


def default_test_contexts_for_hook(hook_point: str) -> list[dict[str, Any]]:
    """
    Canonical safety-test contexts for verify_nuance_safety (admin approve, policy attach, sync).
    Keys must stay within HOOK_REGISTRY allowed keys for the hook.
    """
    if hook_point in ("tuition_calc", "fee_discount"):
        return [
            {"fee": 1000, "gpa": 3.5, "sibling_count": 0},
            {"fee": 2000, "gpa": 4.0, "sibling_count": 2},
        ]
    if hook_point == "grade_weight":
        return [{"score": 85, "weight": 0.3, "category": "exam"}]
    if hook_point == "attendance_alert":
        return [{"attendance_rate": 0.92, "student_id": 1, "term_id": 1}]
    if hook_point == "report_card_avg":
        return [
            {
                "weighted_sum": 42.0,
                "coefficient_total": 6.0,
                "scale_max": 20.0,
                "scores_by_subject": {},
                "coefficients": {},
            },
            {
                "value": 14.5,
                "scale_max": 20.0,
                "scores_by_subject": {},
                "coefficients": {},
            },
        ]
    if hook_point == "scholarship_eligibility":
        return [
            {"gpa": 3.5, "sibling_count": 0, "attendance_rate": 0.95, "fee_status": "current"},
            {"gpa": 2.0, "sibling_count": 1, "attendance_rate": 0.6, "fee_status": "overdue"},
        ]
    return [{"value": 1}]


# Default allowed keys if hook unknown (restrictive)
DEFAULT_ALLOWED_KEYS = {"value"}

EXECUTION_TIMEOUT_SECONDS = 0.05  # 50ms


def _scrub_context(context: dict[str, Any], allowed_keys: set[str]) -> dict[str, Any]:
    """Return only allowed keys from context (DTO / data masking)."""
    if not allowed_keys:
        return {}
    return {k: v for k, v in (context or {}).items() if k in allowed_keys}


def _safe_eval(logic: Any, data: dict[str, Any]) -> Any:
    """
    Minimal JSON-Logic evaluator. Only allowed ops: var, and, or, not, <, >, <=, >=, ==, +, -, *, /, if, max, min.
    No imports, no file access, no side effects.
    """
    if logic is None:
        return None
    if isinstance(logic, (str, int, float, bool)):
        return logic
    if not isinstance(logic, dict):
        return None
    keys = list(logic.keys())
    if len(keys) != 1:
        return None
    op, args = keys[0], logic[keys[0]]
    if not isinstance(args, list):
        args = [args]

    def get_var(name: str) -> Any:
        if not isinstance(name, str):
            return None
        return data.get(name)

    if op == "var":
        return get_var(args[0]) if args else None
    if op == "and":
        for a in args:
            if not _safe_eval(a, data):
                return False
        return True
    if op == "or":
        for a in args:
            if _safe_eval(a, data):
                return True
        return False
    if op == "not":
        return not _safe_eval(args[0], data) if args else True
    if op in (">", "<", ">=", "<=", "=="):
        if len(args) != 2:
            return None
        a, b = _safe_eval(args[0], data), _safe_eval(args[1], data)
        if a is None or b is None:
            return None
        try:
            if op == ">":
                return a > b
            if op == "<":
                return a < b
            if op == ">=":
                return a >= b
            if op == "<=":
                return a <= b
            if op == "==":
                return a == b
        except TypeError:
            return None
    if op in ("+", "-", "*", "/"):
        if len(args) != 2:
            return None
        a, b = _safe_eval(args[0], data), _safe_eval(args[1], data)
        if a is None or b is None:
            return None
        try:
            if op == "+":
                return float(a) + float(b)
            if op == "-":
                return float(a) - float(b)
            if op == "*":
                return float(a) * float(b)
            if op == "/":
                return float(a) / float(b) if float(b) != 0 else None
        except (TypeError, ValueError):
            return None
    if op == "if":
        if len(args) < 2:
            return None
        cond = _safe_eval(args[0], data)
        if cond:
            return _safe_eval(args[1], data)
        return _safe_eval(args[2], data) if len(args) > 2 else None
    if op == "max" and args:
        vals = [_safe_eval(a, data) for a in args]
        vals = [v for v in vals if v is not None]
        return max(vals) if vals else None
    if op == "min" and args:
        vals = [_safe_eval(a, data) for a in args]
        vals = [v for v in vals if v is not None]
        return min(vals) if vals else None
    # Membership: {"in": [needle, haystack]} — e.g. {"in": ["Early Bird", {"var": "student_tags"}]}
    if op == "in" and len(args) >= 2:
        needle = _safe_eval(args[0], data)
        haystack = _safe_eval(args[1], data)
        if not isinstance(haystack, list):
            return False
        return needle in haystack
    return None


def _sigalrm_timeout_available() -> bool:
    """SIGALRM/itimer only work on the main interpreter thread (not Gunicorn gthread workers)."""
    return hasattr(signal, "SIGALRM") and threading.current_thread() is threading.main_thread()


def _run_with_timeout(
    logic: dict, data: dict, timeout_sec: float = EXECUTION_TIMEOUT_SECONDS
) -> Any:
    """Run evaluator with timeout (main thread: SIGALRM; workers: thread pool)."""
    result = [None]
    timeout = max(0.001, float(timeout_sec))

    def run_eval():
        result[0] = _safe_eval(logic, data)

    if _sigalrm_timeout_available():

        def handler(signum, frame):
            raise TimeoutError("Nuance execution exceeded %s s" % timeout_sec)

        old = signal.signal(signal.SIGALRM, handler)
        try:
            signal.setitimer(signal.ITIMER_REAL, timeout)  # type: ignore[attr-defined]
            try:
                run_eval()
            except _NUANCE_EVAL_ERRORS as e:
                log_exception_with_context(
                    "nuance_engine: _run_with_timeout eval failed",
                    extra={"error": str(e)},
                )
                return None
            finally:
                signal.setitimer(signal.ITIMER_REAL, 0)  # type: ignore[attr-defined]
        except TimeoutError:
            logger.warning("Nuance execution timed out")
            return None
        finally:
            signal.signal(signal.SIGALRM, old)
        return result[0]

    pool = ThreadPoolExecutor(max_workers=1)
    try:
        future = pool.submit(run_eval)
        try:
            future.result(timeout=timeout)
        except FuturesTimeoutError:
            logger.warning("Nuance execution timed out (thread pool)")
            return None
        except _NUANCE_EVAL_ERRORS as e:
            log_exception_with_context(
                "nuance_engine: _run_with_timeout eval failed",
                extra={"error": str(e)},
            )
            return None
    finally:
        pool.shutdown(wait=False, cancel_futures=True)
    return result[0]


def _logic_from_policy(school, hook_point: str) -> dict[str, Any] | None:
    """PolicyBundle / resolver grading templates (JSON-Logic only)."""
    if school is None:
        return None
    try:
        from apps.policies.resolver import get_effective_policy

        policy = get_effective_policy(school)
        grading = policy.get("grading") if isinstance(policy.get("grading"), dict) else {}
        templates = grading.get("nuance_templates") if isinstance(grading.get("nuance_templates"), dict) else {}
        spec = templates.get(hook_point)
        if isinstance(spec, dict):
            logic = spec.get("logic_data")
            if isinstance(logic, dict):
                return logic
    except (ImportError, AttributeError, TypeError, ValueError):
        return None
    return None


def evaluate_json_logic(
    logic: dict,
    data: dict[str, Any],
    *,
    timeout_sec: float = EXECUTION_TIMEOUT_SECONDS,
) -> Any:
    """
    Evaluate JSON-Logic with Gunicorn-safe timeout semantics.

    Use this instead of calling ``_safe_eval`` directly from request/worker code paths.
    """
    if not logic or not isinstance(logic, dict):
        return None
    return _run_with_timeout(logic, data, timeout_sec=timeout_sec)


def compute_report_card_average(
    school,
    *,
    weighted_sum: float,
    coefficient_total: float,
    scale_max: float = 20.0,
) -> float:
    """
    Coefficient-weighted term average via report_card_avg nuance (CustomNuance / policy template).

    Falls back to weighted_sum / coefficient_total when no logic is configured or evaluation fails.
    """
    if coefficient_total <= 0:
        return 0.0
    raw_avg = weighted_sum / coefficient_total
    if school is None:
        return raw_avg
    context = {
        "weighted_sum": weighted_sum,
        "coefficient_total": coefficient_total,
        "scale_max": scale_max,
        "value": raw_avg,
        "scores_by_subject": {},
        "coefficients": {},
    }
    result = apply_nuance(school, "report_card_avg", context)
    if result is None:
        return raw_avg
    try:
        return float(result)
    except (TypeError, ValueError):
        return raw_avg


def apply_nuance(school, hook_point: str, context: dict[str, Any]) -> Any:
    """
    Load active CustomNuance for (school, hook_point), scrub context to allowed keys,
    run JSON-Logic, return result. Core code applies the value (read-only: logic does not write DB).
    """
    from .models import CustomNuance

    allowed = set(HOOK_REGISTRY.get(hook_point, DEFAULT_ALLOWED_KEYS))
    scrubbed = _scrub_context(context, allowed)
    nuance = CustomNuance.objects.filter(
        school=school,
        hook_point=hook_point,
        is_active=True,
    ).first()
    logic_data = None
    if nuance and nuance.logic_data:
        logic_data = nuance.logic_data
    if logic_data is None:
        logic_data = _logic_from_policy(school, hook_point)
    if not logic_data:
        return None
    return _run_with_timeout(logic_data, scrubbed)


def verify_nuance_safety(
    logic_data: dict,
    test_contexts: list[dict[str, Any]],
    *,
    reject_negative_fee: bool = True,
) -> tuple[bool, str]:
    """
    Run logic against test contexts. Return (True, "") if safe; (False, reason) otherwise.
    Reject if result is negative when reject_negative_fee (financial safety).
    """
    if not logic_data or not isinstance(logic_data, dict):
        return False, "Logic must be a non-empty JSON object"
    for i, ctx in enumerate(test_contexts or []):
        try:
            result = _run_with_timeout(logic_data, ctx or {})
        except _NUANCE_EVAL_ERRORS as e:
            log_exception_with_context(
                "nuance_engine: verify_nuance_safety test crashed",
                extra={"test_index": i},
            )
            return False, f"Test {i + 1} crashed: {e}"
        if reject_negative_fee and result is not None:
            try:
                if float(result) < 0:
                    return False, f"Test {i + 1} resulted in negative value: {result}"
            except (TypeError, ValueError):
                pass
        if result is not None and not isinstance(
            result, (int, float, bool, str, type(None))
        ):
            return False, f"Test {i + 1} returned invalid type"
    return True, ""


def nuance_engine_enabled(school) -> bool:
    """True if school's plan or addons include nuance_engine / custom_logic (gate for save)."""
    if not school:
        return False
    from apps.schools.models import is_feature_enabled

    return is_feature_enabled(school, "nuance_engine") or is_feature_enabled(
        school, "custom_logic"
    )
