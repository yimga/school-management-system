#!/usr/bin/env python3
"""
Phase 6 gate: runtime-first conformance.

Checks:
1) resolver precedence contract for touched runtime flows
2) fallback-ban checks (no direct singleton/ORM fallback anti-patterns)
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace")


def _assert_in_order(text: str, markers: tuple[str, ...], label: str, errors: list[str]) -> None:
    pos = -1
    for marker in markers:
        idx = text.find(marker)
        if idx < 0:
            errors.append(f"{label}: missing marker {marker!r}")
            return
        if idx <= pos:
            errors.append(
                f"{label}: precedence marker out of order {marker!r} (must preserve canonical order)."
            )
            return
        pos = idx


def main() -> int:
    errors: list[str] = []

    tenant_cfg_py = ROOT / "apps" / "siteconfig" / "tenant_config.py"
    policy_resolver_py = ROOT / "apps" / "policies" / "resolver.py"
    runtime_resolver_py = ROOT / "apps" / "platform_runtime" / "runtime_resolver.py"
    precedence_py = ROOT / "apps" / "platform_runtime" / "precedence.py"
    precedence_doc = ROOT / "docs" / "runtime_precedence.md"

    required = (
        tenant_cfg_py,
        policy_resolver_py,
        runtime_resolver_py,
        precedence_py,
    )
    for path in required:
        if not path.is_file():
            errors.append(f"Missing required file: {path.relative_to(ROOT).as_posix()}")
    if errors:
        print("verify_phase6_runtime_first_conformance: FAIL", file=sys.stderr)
        for item in errors:
            print(f"  - {item}", file=sys.stderr)
        return 1

    tenant_cfg_text = _read(tenant_cfg_py)
    policy_text = _read(policy_resolver_py)
    runtime_text = _read(runtime_resolver_py)
    precedence_text = _read(precedence_py)

    # 1) Compile precedence contract (tenant config compiler layers must remain deterministic).
    _assert_in_order(
        tenant_cfg_text,
        (
            "1. global defaults",
            "2. regional policy pack",
            "3. education profile defaults/config",
            "4. plan/add-on derived features",
            "5. tenant overrides (school.settings)",
            "6. campus overrides",
            "7. user overrides",
        ),
        "compile_effective_tenant_config docstring",
        errors,
    )
    _assert_in_order(
        tenant_cfg_text,
        (
            "# Layer 2: regional policy pack",
            "# Layer 3: education profile (if available)",
            "# Layer 4: plan/add-ons to feature_modules",
            "# Layer 5: tenant overrides",
            "# Layer 6: campus overrides",
            "# Layer 7: user overrides",
        ),
        "compile_effective_tenant_config implementation",
        errors,
    )

    # 2) Runtime resolver contract: policy must be resolved via get_effective_policy in request build flow.
    if "from apps.policies.policy_registry import get_effective_policy" not in runtime_text:
        errors.append("runtime_resolver.py must import get_effective_policy from policy_registry.")
    if "policy = get_effective_policy(school, user=user)" not in runtime_text:
        errors.append("runtime_resolver.py must resolve policy via get_effective_policy(school, user=user).")

    # 3) Policy resolver precedence: compiled config merge must happen before legacy settings merge.
    compiled_marker = 'compiled = settings.get("tenant_compiled_config")'
    raw_settings_marker = "# Tenant overrides from School.settings (JSON)"
    if compiled_marker not in policy_text:
        errors.append("resolver.py missing compiled tenant config marker.")
    if "_merge_compiled_config_into_policy(out, compiled)" not in policy_text:
        errors.append("resolver.py must merge tenant_compiled_config into effective policy.")
    if raw_settings_marker not in policy_text:
        errors.append("resolver.py missing raw School.settings merge marker.")
    if (
        compiled_marker in policy_text
        and raw_settings_marker in policy_text
        and policy_text.find(compiled_marker) > policy_text.find(raw_settings_marker)
    ):
        errors.append(
            "resolver.py precedence violation: tenant_compiled_config merge must run before raw School.settings merge."
        )

    # 4) Fallback ban checks on touched flows: block singleton direct reads and direct SiteSettings ORM.
    fallback_bans = (
        r"\bSiteSettings\.get_solo\(",
        r"\bSiteSettings\.load\(",
        r"\bSiteSettings\.objects\.",
    )
    for path, text in (
        (tenant_cfg_py, tenant_cfg_text),
        (policy_resolver_py, policy_text),
        (runtime_resolver_py, runtime_text),
    ):
        for pattern in fallback_bans:
            if re.search(pattern, text):
                errors.append(
                    f"{path.relative_to(ROOT).as_posix()} contains banned fallback pattern: {pattern}"
                )

    if "PRECEDENCE_ORDER" not in precedence_text:
        errors.append("apps/platform_runtime/precedence.py must define PRECEDENCE_ORDER.")
    if precedence_doc.is_file():
        doc_text = _read(precedence_doc)
        for heading in ("Platform default", "Policy bundle", "Tenant override"):
            if heading not in doc_text:
                errors.append(f"runtime_precedence.md missing heading/token: {heading}")
        if "sandbox_override" not in doc_text and "Sandbox override" not in doc_text:
            errors.append(
                "runtime_precedence.md missing sandbox override token (expected 'sandbox_override' or 'Sandbox override')."
            )

    if errors:
        print("verify_phase6_runtime_first_conformance: FAIL", file=sys.stderr)
        for item in errors:
            print(f"  - {item}", file=sys.stderr)
        return 1

    print(
        "verify_phase6_runtime_first_conformance: PASS "
        "(resolver precedence contract + fallback-ban checks)"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
