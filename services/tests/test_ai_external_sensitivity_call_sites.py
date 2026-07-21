"""External-tier sensitivity declarations, audited per CALL SITE.

``services.ai_gateway._data_tier_allows_premium`` is deny-by-default: a caller
reaches the external LiteLLM tier only by explicitly declaring a
``sensitivity_class`` from ``_external_sensitivity_allowlist()``. Quality is
restored one call site at a time, and only for prompts that provably cannot
carry personal data.

This module is the gate on that decision. It has three jobs:

1. **Positive** — every call site we annotated really does declare a class the
   gateway accepts. Revert an annotation and the matching row goes RED.
2. **Purity** — the annotated site's prompt expression does not interpolate a
   student / guardian / free-text field. Add ``student.first_name`` to one of
   those prompts and the matching row goes RED.
3. **Negative control** — the sites we deliberately left alone are STILL denied
   the external tier. This is what stops a future "just allow everything"
   change (a blanket default, a wildcard allowlist, a shared helper that
   stamps a class for all callers) from landing green.
"""

from __future__ import annotations

import ast
import inspect
import re
import textwrap
from unittest.mock import patch

from django.test import SimpleTestCase, override_settings

from services.ai_gateway import (
    TaskType,
    _data_tier_allows_premium,
    _external_sensitivity_allowlist,
    invoke,
    reset_ai_gateway_circuits,
)

# ---------------------------------------------------------------------------
# AST helpers — we assert on the SOURCE of each call site so the gate keeps
# working without spinning up tenants, sessions or RBAC fixtures.
# ---------------------------------------------------------------------------

#: Identifiers that mean "this prompt touched a person". Deliberately narrow and
#: accessor-shaped (``.first_name``, ``guardian_email``) so a benign aggregate
#: such as ``student_count`` does NOT trip it — a gate that rejects true
#: statements is worse than no gate.
_PERSONAL_ACCESSOR_RE = re.compile(
    r"""(?xi)
    (?:^|[.\[\]'"\s])(?:
        first_name | last_name | full_name | display_name | student_name
      | guardian(?:_\w+)? | parent_name | parent_email | next_of_kin
      | date_of_birth | dob | admission_number | roll_number
      | safeguarding\w* | disciplin\w* | medical\w* | sen_status
      | free_text | user_query | page_excerpt | selection_summary
      | error_message | excerpt | ticket\w* | notes | message_body
    )\b
    """
)


def _function_ast(func) -> ast.AST:
    """Parse a single function/method into an AST node."""
    return ast.parse(textwrap.dedent(inspect.getsource(func))).body[0]


def _declared_sensitivity_classes(node: ast.AST) -> set[str]:
    """Every ``sensitivity_class`` this function declares, however it is passed.

    Covers both shapes in use:
      * a ``"sensitivity_class": "internal"`` entry in a metadata dict literal
        (the ``invoke_with_request`` / ``guard_copilot_invoke`` callers), and
      * a ``sensitivity_class="internal"`` keyword argument (the
        ``run_ai_prompt`` callers), and
      * a ``metadata["sensitivity_class"] = "internal"`` subscript assignment
        (``services.ai_palette``).
    """
    found: set[str] = set()
    for child in ast.walk(node):
        if isinstance(child, ast.Assign) and isinstance(child.value, ast.Constant):
            for target in child.targets:
                if (
                    isinstance(target, ast.Subscript)
                    and isinstance(target.slice, ast.Constant)
                    and target.slice.value == "sensitivity_class"
                    and isinstance(child.value.value, str)
                ):
                    found.add(child.value.value.strip().lower())
        if isinstance(child, ast.Dict):
            for key, value in zip(child.keys, child.values):
                if (
                    isinstance(key, ast.Constant)
                    and key.value == "sensitivity_class"
                    and isinstance(value, ast.Constant)
                    and isinstance(value.value, str)
                ):
                    found.add(value.value.strip().lower())
        elif isinstance(child, ast.keyword):
            if (
                child.arg == "sensitivity_class"
                and isinstance(child.value, ast.Constant)
                and isinstance(child.value.value, str)
            ):
                found.add(child.value.value.strip().lower())
    return found


def _prompt_expressions(node: ast.AST, *, call_name: str | None) -> list[str]:
    """Source text of everything that becomes model-visible prompt text.

    ``assign`` sites build ``prompt = <expr>`` then hand it to the gateway.
    ``call_name`` sites (``run_ai_prompt``) pass the prompt AND the context
    blob positionally, so both positional args are scanned.
    """
    out: list[str] = []
    if call_name:
        for child in ast.walk(node):
            if isinstance(child, ast.Call):
                fn = child.func
                name = fn.attr if isinstance(fn, ast.Attribute) else getattr(fn, "id", "")
                if name == call_name:
                    out.extend(ast.unparse(arg) for arg in child.args[:2])
    for child in ast.walk(node):
        if isinstance(child, ast.Assign):
            targets = [t.id for t in child.targets if isinstance(t, ast.Name)]
            if "prompt" in targets:
                out.append(ast.unparse(child.value))
    return out


def _load(module_path: str, attr_path: str):
    """Import ``module_path`` and walk dotted ``attr_path`` off it."""
    module = __import__(module_path, fromlist=["*"])
    obj = module
    for part in attr_path.split("."):
        obj = getattr(obj, part)
    return obj


# ---------------------------------------------------------------------------
# The audit tables. Editing these is editing the security decision.
# ---------------------------------------------------------------------------

#: (label, module, attribute path, positional-call name or None)
ANNOTATED_SITES = [
    (
        "ai_palette._try_cloud_generation",
        "services.ai_palette",
        "_try_cloud_generation",
        None,
    ),
    (
        "live_banner_studio.api_live_banner_suggest_program",
        "apps.siteconfig.views_live_banner_studio",
        "api_live_banner_suggest_program",
        None,
    ),
    (
        "onboarding_coach.api_onboarding_coach",
        "apps.siteconfig.views_onboarding_coach",
        "api_onboarding_coach",
        None,
    ),
    (
        "learning_institution_api.InstitutionProfileSuggestView.get",
        "apps.api.learning_institution_api",
        "InstitutionProfileSuggestView.get",
        None,
    ),
    (
        "ai_system_layer.generate_school_health_insight",
        "apps.platform_runtime.ai_system_layer",
        "generate_school_health_insight",
        "run_ai_prompt",
    ),
    (
        "ai_system_layer.generate_onboarding_next_action_insight",
        "apps.platform_runtime.ai_system_layer",
        "generate_onboarding_next_action_insight",
        "run_ai_prompt",
    ),
    (
        "ai_system_layer.generate_anomaly_risk_nudge",
        "apps.platform_runtime.ai_system_layer",
        "generate_anomaly_risk_nudge",
        "run_ai_prompt",
    ),
]

#: Sites audited as NOT-SAFE. They must stay undeclared, and therefore denied.
#: A blanket "allow everything" change would light this table up.
NOT_SAFE_SITES = [
    ("support_ai_triage.run_ai_triage", "apps.siteconfig.support_ai_triage", "run_ai_triage"),
    ("support_ai_reply.run_ai_draft_reply", "apps.siteconfig.support_ai_reply", "run_ai_draft_reply"),
    (
        "live_banner_studio.api_live_banner_draft_emergency",
        "apps.siteconfig.views_live_banner_studio",
        "api_live_banner_draft_emergency",
    ),
    (
        "ai_assistant_service.generate_parent_message",
        "apps.platform_runtime.ai_assistant_service",
        "generate_parent_message",
    ),
    (
        "ai_assistant_service.generate_report_summary",
        "apps.platform_runtime.ai_assistant_service",
        "generate_report_summary",
    ),
    ("wizard_ai._call_gateway", "apps.setup_studio.wizard_ai", "_call_gateway"),
    ("migration_cloud.ai_bridge._invoke", "apps.migration_cloud.ai_bridge", "_invoke"),
    (
        "studio_os.copilot_rail_service.generate_insights",
        "apps.studio_os.copilot_rail_service",
        "generate_insights",
    ),
    (
        "workflow_healing_ai.ai_diagnosis_for_run",
        "apps.platform_runtime.workflow_healing_ai",
        "ai_diagnosis_for_run",
    ),
    (
        "fleet_context_service._maybe_llm_tour_narrator",
        "apps.siteconfig.fleet_context_service",
        "_maybe_llm_tour_narrator",
    ),
    (
        "send_parent_digests.Command._narrate",
        "apps.communication.management.commands.send_parent_digests",
        "Command._narrate",
    ),
    (
        "ai_narrate_risk_digest.Command._narrate",
        "apps.analytics.management.commands.ai_narrate_risk_digest",
        "Command._narrate",
    ),
]


class AnnotatedCallSiteDeclarationTests(SimpleTestCase):
    """(1) Every annotated site declares a class the gateway actually accepts."""

    def test_each_annotated_site_declares_an_allowlisted_sensitivity_class(self):
        allowlist = _external_sensitivity_allowlist()
        for label, module_path, attr_path, _call in ANNOTATED_SITES:
            with self.subTest(site=label):
                node = _function_ast(_load(module_path, attr_path))
                declared = _declared_sensitivity_classes(node)
                self.assertTrue(
                    declared,
                    f"{label} declares no sensitivity_class — the external tier "
                    f"is silently skipped for this surface.",
                )
                for value in declared:
                    self.assertIn(
                        value,
                        allowlist,
                        f"{label} declares '{value}', which the gateway does not accept.",
                    )
                    self.assertTrue(
                        _data_tier_allows_premium(
                            {"sensitivity_class": value},
                            prompt="setup guidance",
                            user_query="",
                        ),
                        f"{label} declares '{value}' but the gateway still denies premium.",
                    )

    def test_no_annotated_site_declares_high(self):
        """``high`` is an explicit deny — declaring it would be a silent no-op."""
        for label, module_path, attr_path, _call in ANNOTATED_SITES:
            with self.subTest(site=label):
                node = _function_ast(_load(module_path, attr_path))
                self.assertNotIn("high", _declared_sensitivity_classes(node), label)


class AnnotatedCallSitePromptPurityTests(SimpleTestCase):
    """(2) The annotated prompts do not interpolate a student/guardian field."""

    def test_annotated_prompts_do_not_interpolate_personal_fields(self):
        for label, module_path, attr_path, call_name in ANNOTATED_SITES:
            with self.subTest(site=label):
                node = _function_ast(_load(module_path, attr_path))
                exprs = _prompt_expressions(node, call_name=call_name)
                self.assertTrue(
                    exprs,
                    f"{label}: could not locate the prompt expression — the audit "
                    f"cannot vouch for a prompt it cannot see.",
                )
                for expr in exprs:
                    hit = _PERSONAL_ACCESSOR_RE.search(expr)
                    self.assertIsNone(
                        hit,
                        f"{label} now interpolates '{hit.group(0).strip() if hit else ''}' "
                        f"into a prompt annotated as safe for the external tier. "
                        f"Remove the annotation or the field.",
                    )

    def test_live_banner_suggest_prompt_is_a_pure_literal(self):
        """The strongest form of the purity claim: zero interpolation at all."""
        from apps.siteconfig import views_live_banner_studio

        node = _function_ast(views_live_banner_studio.api_live_banner_suggest_program)
        exprs = _prompt_expressions(node, call_name=None)
        self.assertEqual(len(exprs), 1)
        prompt_node = ast.parse(exprs[0], mode="eval").body
        self.assertFalse(
            any(isinstance(c, ast.JoinedStr) for c in ast.walk(prompt_node)),
            "api_live_banner_suggest_program's prompt became an f-string; it is "
            "annotated safe on the basis that it interpolates nothing.",
        )

    def test_palette_prompt_cannot_carry_a_hostile_seed_string(self):
        """A name/DOB pushed in as the 'seed colour' never reaches the prompt."""
        from services import ai_palette

        hostile = "Kwabena Mensah 2011-03-04"
        captured: dict[str, object] = {}

        def _capture(**kwargs):
            captured.update(kwargs)
            return None

        with patch.object(ai_palette, "invoke_with_request", side_effect=_capture):
            ai_palette.generate_palette_from_seed(hostile, "dual")

        self.assertIn("prompt", captured)
        self.assertNotIn("Kwabena", str(captured["prompt"]))
        self.assertNotIn("2011-03-04", str(captured["prompt"]))

    def test_palette_gateway_metadata_is_accepted_by_the_gateway(self):
        """End-to-end on the real metadata dict the palette site builds."""
        from services import ai_palette

        captured: dict[str, object] = {}

        def _capture(**kwargs):
            captured.update(kwargs)
            return None

        with patch.object(ai_palette, "invoke_with_request", side_effect=_capture):
            ai_palette.generate_palette_from_seed("#4F46E5", "dual", tone="warm")

        metadata = captured.get("metadata") or {}
        self.assertIn(metadata.get("sensitivity_class"), _external_sensitivity_allowlist())
        self.assertTrue(
            _data_tier_allows_premium(
                metadata,
                prompt=str(captured.get("prompt") or ""),
                user_query="",
            )
        )


class RunAiPromptSensitivityForwardingTests(SimpleTestCase):
    """The ``run_ai_prompt`` facade forwards the opt-in — and omits it by default."""

    def _invoke(self, **kwargs):
        from apps.platform_runtime import ai_providers

        captured: dict[str, object] = {}

        def _capture(**call_kwargs):
            captured.update(call_kwargs)
            return "ok", {"provider": "rules"}

        school = type("_School", (), {"pk": 7})()
        with patch.object(
            ai_providers,
            "get_ai_runtime_config",
            return_value={"enabled": True, "external_network_allowed": True},
        ):
            with patch(
                "services.ai_copilot_rbac.invoke_service_layer_ai", side_effect=_capture
            ):
                ai_providers.run_ai_prompt("prompt", "context", school, **kwargs)
        return captured.get("metadata") or {}

    def test_declared_class_reaches_gateway_metadata(self):
        metadata = self._invoke(sensitivity_class="internal")
        self.assertEqual(metadata.get("sensitivity_class"), "internal")
        self.assertTrue(_data_tier_allows_premium(metadata, prompt="school health 82%"))

    def test_default_omits_the_class_and_therefore_denies_premium(self):
        """Deny-by-default survives the new parameter."""
        metadata = self._invoke()
        self.assertNotIn("sensitivity_class", metadata)
        self.assertFalse(_data_tier_allows_premium(metadata, prompt="school health 82%"))


class NotSafeCallSitesStayDeniedTests(SimpleTestCase):
    """(3) NEGATIVE CONTROL — the unannotated sites must stay locked out."""

    def test_not_safe_sites_declare_no_sensitivity_class(self):
        for label, module_path, attr_path in NOT_SAFE_SITES:
            with self.subTest(site=label):
                node = _function_ast(_load(module_path, attr_path))
                self.assertEqual(
                    _declared_sensitivity_classes(node),
                    set(),
                    f"{label} was audited as NOT-SAFE (it can carry student, "
                    f"guardian or unbounded user free text) but now declares a "
                    f"sensitivity class. Re-audit before allowing this.",
                )

    def test_support_ticket_metadata_is_denied_premium(self):
        """The exact metadata ``run_ai_triage`` builds must not reach LiteLLM."""
        self.assertFalse(
            _data_tier_allows_premium(
                {"feature": "support_ai_triage", "content_sensitivity": "low_pii_ok"},
                prompt="Parent wrote: my son Kwabena is being bullied in Year 8.",
                user_query="bullying",
            )
        )

    def test_parent_message_metadata_is_denied_premium(self):
        self.assertFalse(
            _data_tier_allows_premium(
                {"northstar_prompt_type": "parent_message", "school_id": "7"},
                prompt="Student reference: Y8-014. Topic: attendance. Notes: ...",
                user_query="",
            )
        )

    def test_an_empty_allowlist_cannot_be_used_to_open_everything(self):
        """A wildcard-ish blanket setting must not silently permit unknowns."""
        with override_settings(AI_EXTERNAL_ALLOWED_SENSITIVITY_CLASSES=["public"]):
            self.assertFalse(
                _data_tier_allows_premium(
                    {"sensitivity_class": "internal"}, prompt="hello"
                )
            )
            self.assertFalse(_data_tier_allows_premium({}, prompt="hello"))


@override_settings(
    AI_GATEWAY_ENABLED=True,
    AI_ALLOW_RULES_FALLBACK=True,
    LITELLM_PROXY_URL="https://proxy.example/v1",
    LITELLM_API_KEY="secret-key",
    LITELLM_MODEL="test-model",
    AI_GATEWAY_TASK_TIERS={"narrative": ["litellm", "rules"]},
)
class NotSafeSiteEndToEndDenialTests(SimpleTestCase):
    """The support-ticket surface, driven through the real ``invoke`` chain.

    ``services.ai_gateway._audit_log`` is patched out because it writes an
    ``AIActionAuditLog`` row, which would make this gate depend on a built
    test database. Audit persistence is orthogonal to tier selection — the
    backend chain, ``_data_tier_allows_premium`` and the ``errors`` metadata
    below are all exercised for real.
    """

    def setUp(self):
        reset_ai_gateway_circuits()
        patcher = patch("services.ai_gateway._audit_log")
        patcher.start()
        self.addCleanup(patcher.stop)

    @patch(
        "services.ai_gateway._call_litellm",
        return_value=("premium answer", {"provider": "litellm", "tier": "litellm"}),
    )
    def test_support_ticket_surface_skips_the_external_tier(self, mock_litellm):
        _result, meta = invoke(
            TaskType.NARRATIVE,
            "Triage this support ticket. Subject: fees. Body: <parent free text>",
            user_query="fees",
            metadata={"feature": "support_ai_triage", "content_sensitivity": "low_pii_ok"},
        )
        self.assertEqual(meta.get("errors", {}).get("litellm"), "data_tier_disallowed")
        mock_litellm.assert_not_called()

    @patch(
        "services.ai_gateway._call_litellm",
        return_value=("premium answer", {"provider": "litellm", "tier": "litellm"}),
    )
    def test_annotated_class_is_the_only_thing_that_opens_the_tier(self, mock_litellm):
        """Positive control for the same surface shape — proves the deny above
        is caused by the missing declaration and nothing else."""
        result, meta = invoke(
            TaskType.NARRATIVE,
            "Suggest a live banner program for a school SaaS operator.",
            user_query="",
            metadata={"sensitivity_class": "internal"},
        )
        self.assertEqual(result, "premium answer")
        self.assertEqual(meta.get("tier"), "litellm")
        mock_litellm.assert_called_once()
