"""Studio OS cross-cutting operator/tenant boundary contracts (v3.54.0, 2026-05-21).

Asserts that operator-only controls and tenant-safe scopes are correctly
gated across all 6 Studio OS sections. Per-section tests cover their own
boundary in detail (e.g. test_control_governance_cockpit.py); this module
is the cross-cutting backstop.

Static-only (SimpleTestCase) — no DB needed.
"""

from __future__ import annotations

import re
from pathlib import Path

from django.test import SimpleTestCase


REPO_ROOT = Path(__file__).resolve().parents[3]
TEMPLATES_DIR = REPO_ROOT / "templates" / "studio_os"
PARTIALS_DIR = TEMPLATES_DIR / "partials"
SHELL_PATH = TEMPLATES_DIR / "shell.html"


OPERATOR_ONLY_PARTIALS_AND_TOKENS = [
    # (partial, token that should be guarded by `request.public_host_kind == 'manager'`)
    ("overview_command_cockpit.html", "legacy_urls.rbac"),
    ("overview_command_cockpit.html", "legacy_urls.feature_control"),
]


def _read(rel: str) -> str:
    return (PARTIALS_DIR / rel).read_text(encoding="utf-8")


class OperatorHostGateTests(SimpleTestCase):
    """Operator-only chips/buttons must sit inside a request.public_host_kind
    == 'manager' guard."""

    def test_operator_only_tokens_sit_inside_manager_host_guard(self) -> None:
        for partial, token in OPERATOR_ONLY_PARTIALS_AND_TOKENS:
            with self.subTest(partial=partial, token=token):
                src = _read(partial)
                # Find the token, then walk backward for the nearest opening
                # {% if ... manager ... %} and ensure no {% endif %} between
                # the guard and the token.
                idx = src.find(token)
                self.assertGreater(
                    idx, -1, f"{partial}: token {token!r} not found"
                )
                preceding = src[:idx]
                # The token must have at least one matching manager-host guard
                # without a closing endif between it and the token.
                guards = list(
                    re.finditer(
                        r"\{%\s*if\s+request\.public_host_kind\s*==\s*['\"]manager['\"]",
                        preceding,
                    )
                )
                self.assertTrue(
                    guards,
                    f"{partial}: token {token!r} not preceded by any "
                    f"`request.public_host_kind == 'manager'` guard",
                )
                # Get text after last guard, ensure it doesn't close before token.
                last_guard_end = guards[-1].end()
                between = preceding[last_guard_end:]
                opens = len(re.findall(r"\{%\s*if\b", between))
                closes = len(re.findall(r"\{%\s*endif\b", between))
                self.assertGreaterEqual(
                    opens, closes,
                    f"{partial}: token {token!r} lives outside its host guard "
                    f"(endif count {closes} >= if count {opens} between guard and token)",
                )


class NoPiiInAuditListTests(SimpleTestCase):
    """Audit lists must never render raw email/username/slug. Use actor_display."""

    PII_FIELDS = ("actor_email", "actor_username", "actor_slug", "user_email", "user.email")

    def test_shell_control_audit_uses_actor_display_not_pii(self) -> None:
        src = SHELL_PATH.read_text(encoding="utf-8")
        # Find the control-mode audit list block.
        match = re.search(
            r"current_mode\s*==\s*['\"]control['\"].*?(?=\{%\s*el)",
            src,
            flags=re.DOTALL,
        )
        self.assertIsNotNone(match, "control branch not found in shell.html")
        block = match.group(0)
        for field in self.PII_FIELDS:
            with self.subTest(field=field):
                self.assertNotIn(
                    field,
                    block,
                    f"shell.html control audit list renders {field!r} — "
                    f"use actor_display instead (PII-safe).",
                )
        # Positive assertion: actor_display IS used.
        self.assertIn(
            "actor_display", block,
            "shell.html control audit list must render actor_display (PII-safe)",
        )


class NoRoleStringLiteralsTests(SimpleTestCase):
    """Role names must come from registry, not literal strings outside
    {% trans %} blocks. Cross-cutting backstop for scan_role_strings."""

    ROLE_LITERAL_PATTERNS = (
        r'"\s*ADMIN\s*"',
        r"'\s*ADMIN\s*'",
        r'"\s*TEACHER\s*"',
        r"'\s*TEACHER\s*'",
        r'"\s*PARENT\s*"',
        r"'\s*PARENT\s*'",
        r'"\s*STUDENT\s*"',
        r"'\s*STUDENT\s*'",
        r'"\s*PROPRIETOR\s*"',
        r"'\s*PROPRIETOR\s*'",
    )

    # Files allowed to contain role-string literals (registry SOTs, fixtures).
    ALLOWED_FILES: set[str] = set()

    def test_no_uppercase_role_literals_in_new_v3_54_templates(self) -> None:
        # Only audit the v3.54.0 NEW partials — pre-existing partials are
        # scanned by the broader scan_role_strings.py.
        v3_54_partials = [
            "overview_command_cockpit.html",
            "experience_live_preview_pane.html",
            "automation_simulation_preview_pane.html",
            "output_readiness_preview_pane.html",
            "launch_readiness_preview_pane.html",
            "control_governance_preview_pane.html",
        ]
        for fname in v3_54_partials:
            path = PARTIALS_DIR / fname
            if not path.exists():
                continue
            src = path.read_text(encoding="utf-8")
            for pattern in self.ROLE_LITERAL_PATTERNS:
                hits = re.findall(pattern, src)
                # Allow hits inside {% trans %} or {% blocktrans %} — those
                # are user-visible labels, not role-name comparisons.
                if hits:
                    # Find each hit's surrounding context and exclude trans blocks.
                    for m in re.finditer(pattern, src):
                        ctx_start = max(0, m.start() - 80)
                        ctx_end = min(len(src), m.end() + 20)
                        ctx = src[ctx_start:ctx_end]
                        if "trans" in ctx or "blocktrans" in ctx:
                            continue
                        self.fail(
                            f"{fname}: role-string literal {m.group(0)!r} "
                            f"outside {{% trans %}} block — use role_registry instead. "
                            f"Context: {ctx!r}"
                        )


class DestructiveActionConfirmTests(SimpleTestCase):
    """Destructive surfaces use data-rmc-confirm. Cross-cutting check that
    new v3.54.0 partials with activate/replay/rollback/apply triggers carry
    the marker."""

    DESTRUCTIVE_KEYWORDS = ("rollback", "Apply", "Activate", "Deactivate", "Replay")

    PARTIALS_WITH_DESTRUCTIVE = [
        "control_governance_preview_pane.html",
        "launch_readiness_preview_pane.html",
        "automation_simulation_preview_pane.html",
    ]

    def test_destructive_buttons_carry_data_rmc_confirm(self) -> None:
        for fname in self.PARTIALS_WITH_DESTRUCTIVE:
            path = PARTIALS_DIR / fname
            if not path.exists():
                continue
            src = path.read_text(encoding="utf-8")
            # Find <button ... > or <a ... > elements containing a destructive
            # keyword in their label.
            elements = re.findall(
                r"<(?:button|a)\b[^>]*>([^<]*)</(?:button|a)>",
                src,
                flags=re.IGNORECASE,
            )
            for label in elements:
                if not any(kw.lower() in label.lower() for kw in self.DESTRUCTIVE_KEYWORDS):
                    continue
                # Re-find the element to check its attrs.
                # If this button has destructive keyword text, the element
                # must declare data-rmc-confirm OR be inside a form with one.
                # Loose check: data-rmc-confirm OR onclick="return confirm" must
                # appear somewhere within 200 chars before the label.
                idx = src.find(f">{label}<")
                if idx == -1:
                    continue
                window = src[max(0, idx - 300):idx]
                has_confirm = (
                    "data-rmc-confirm" in window
                    or 'onclick="return confirm' in window
                )
                self.assertTrue(
                    has_confirm,
                    f"{fname}: destructive button labeled `{label.strip()}` "
                    f"is missing data-rmc-confirm. Destructive surfaces must "
                    f"require explicit confirmation.",
                )
