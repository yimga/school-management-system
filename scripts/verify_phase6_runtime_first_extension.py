#!/usr/bin/env python3
"""
Phase 6 extension gate: runtime-first contracts on allowlisted high-risk policy consumers.

Allowlist:
- admissions: apps/siteconfig/identifier_policy_service.py
- gradebook: apps/evals/runtime_gradebook.py
- finance: apps/finance/runtime_helpers.py
- section-10 policy consumers: apps/policies/section_10_helpers.py
- finance API entrypoints: apps/finance/api_views.py
- policy-backed school config API: apps/schools/api_views.py
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
# Discovery guard: newly introduced admissions API view files must be explicitly
# allowlisted in this gate or justified in this tuple to prevent silent drift.
ADMISSIONS_API_VIEW_DISCOVERY_GLOBS = (
    "apps/**/admission*api*.py",
    "apps/**/api*admission*.py",
    "apps/**/admissions*api*.py",
    "apps/**/api*admissions*.py",
)
JUSTIFIED_ADMISSIONS_API_VIEW_FILES = frozenset(
    {
        # Keep empty unless a file is intentionally excluded from allowlist checks.
    }
)


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace")


def _strip_multiline_strings(text: str) -> str:
    text = re.sub(r'"""[\s\S]*?"""', "", text)
    text = re.sub(r"'''[\s\S]*?'''", "", text)
    return text


def _discover_admissions_api_view_files() -> list[Path]:
    hits: set[Path] = set()
    for pattern in ADMISSIONS_API_VIEW_DISCOVERY_GLOBS:
        for path in ROOT.glob(pattern):
            if path.is_file():
                hits.add(path.resolve())
    return sorted(hits)


def main() -> int:
    errors: list[str] = []

    admissions_py = ROOT / "apps" / "siteconfig" / "identifier_policy_service.py"
    gradebook_py = ROOT / "apps" / "evals" / "runtime_gradebook.py"
    finance_py = ROOT / "apps" / "finance" / "runtime_helpers.py"
    section10_py = ROOT / "apps" / "policies" / "section_10_helpers.py"
    finance_api_py = ROOT / "apps" / "finance" / "api_views.py"
    schools_api_py = ROOT / "apps" / "schools" / "api_views.py"

    allowlisted = (
        admissions_py,
        gradebook_py,
        finance_py,
        section10_py,
        finance_api_py,
        schools_api_py,
    )
    for path in allowlisted:
        if not path.is_file():
            errors.append(f"Missing allowlisted runtime-first file: {path.relative_to(ROOT).as_posix()}")
    if errors:
        print("verify_phase6_runtime_first_extension: FAIL", file=sys.stderr)
        for item in errors:
            print(f"  - {item}", file=sys.stderr)
        return 1

    admissions_text = _read(admissions_py)
    gradebook_text = _read(gradebook_py)
    finance_text = _read(finance_py)
    section10_text = _read(section10_py)
    finance_api_text = _read(finance_api_py)
    schools_api_text = _read(schools_api_py)

    # Contract checks: each module must source behavior from runtime/policy helpers.
    if "from apps.policies.policy_registry import get_effective_policy" not in admissions_text:
        errors.append("identifier_policy_service.py must import get_effective_policy for admissions fallback.")
    if "out = get_effective_policy(school)" not in admissions_text:
        errors.append("identifier_policy_service.py must resolve admissions fallback via get_effective_policy(school).")

    if 'return getattr(modules, "gradebook", None) or {}' not in gradebook_text:
        errors.append("runtime_gradebook.py must source gradebook config from runtime.modules.gradebook.")

    if "runtime = getattr(request, \"tenant_runtime\", None)" not in finance_text:
        errors.append("finance/runtime_helpers.py must read request.tenant_runtime first.")
    if "return runtime.policy" not in finance_text:
        errors.append("finance/runtime_helpers.py must return runtime.policy when present.")
    if "from apps.policies.policy_registry import get_effective_policy" not in finance_text:
        errors.append("finance/runtime_helpers.py must use get_effective_policy as fallback path.")
    if "return get_effective_policy(school)" not in finance_text:
        errors.append("finance/runtime_helpers.py must fallback to get_effective_policy(school).")

    if "from apps.policies.policy_registry import get_effective_policy" not in section10_text:
        errors.append("section_10_helpers.py must import get_effective_policy.")
    for section in ("finance", "attendance", "communication", "hr_staff", "compliance"):
        if f'return policy.get("{section}") or {{}}' not in section10_text:
            errors.append(f"section_10_helpers.py must return policy-driven section for {section}.")

    # API-view entrypoint checks (narrow/noise-aware).
    if "def _request_school(request):" not in finance_api_text:
        errors.append("finance/api_views.py must keep _request_school(request) helper.")
    for token in (
        "school = _request_school(request)",
        "school = _request_school(self.request)",
        "base = base.filter(school=school)",
    ):
        if token not in finance_api_text:
            errors.append(f"finance/api_views.py missing tenant-scoped API contract token: {token}")

    if "from apps.policies.policy_registry import get_effective_policy" not in schools_api_text:
        errors.append("schools/api_views.py must import get_effective_policy for policy-backed config API.")
    if "policy = get_effective_policy(school, user=getattr(request, \"user\", None))" not in schools_api_text:
        errors.append("schools/api_views.py must resolve features via get_effective_policy(school, user=...).")

    # Discovery guard: force review for newly introduced admissions API view files.
    allowlisted_rel = {path.relative_to(ROOT).as_posix() for path in allowlisted}
    discovered_rel = {
        path.relative_to(ROOT).as_posix() for path in _discover_admissions_api_view_files()
    }
    unmanaged = sorted(
        discovered_rel - allowlisted_rel - set(JUSTIFIED_ADMISSIONS_API_VIEW_FILES)
    )
    if unmanaged:
        errors.append(
            "Unmanaged admissions API view file(s) discovered. Add to allowlist or "
            f"JUSTIFIED_ADMISSIONS_API_VIEW_FILES: {unmanaged}"
        )

    # Fallback-ban checks on allowlisted files (downstream guardrails).
    banned = (
        r"\bSiteSettings\.get_solo\(",
        r"\bSiteSettings\.load\(",
        r"\bSiteSettings\.objects\.",
        r"\bschool\.settings\b",
        r"\bschool\.features\b",
    )
    for path, raw_text in (
        (admissions_py, admissions_text),
        (gradebook_py, gradebook_text),
        (finance_py, finance_text),
        (section10_py, section10_text),
        (finance_api_py, finance_api_text),
        (schools_api_py, schools_api_text),
    ):
        text = _strip_multiline_strings(raw_text)
        for pattern in banned:
            if re.search(pattern, text):
                errors.append(
                    f"{path.relative_to(ROOT).as_posix()} contains banned downstream fallback pattern: {pattern}"
                )

    if errors:
        print("verify_phase6_runtime_first_extension: FAIL", file=sys.stderr)
        for item in errors:
            print(f"  - {item}", file=sys.stderr)
        return 1

    print(
        "verify_phase6_runtime_first_extension: PASS "
        "(allowlisted admissions/gradebook/finance policy-consumer contracts)"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
