"""Phase 11 — workflow_registry contracts.

Pure-Python tests (SimpleTestCase): the registry is in-process data only, no
DB access, no Django boot beyond settings load. These tests lock the
invariants the Phase 2 spec depends on.
"""
from __future__ import annotations

from django.test import SimpleTestCase

from apps.platform_runtime import workflow_registry as wf


class WorkflowRegistryStructureTests(SimpleTestCase):
    def test_workflows_is_a_non_empty_dict(self):
        self.assertIsInstance(wf.WORKFLOWS, dict)
        self.assertGreater(len(wf.WORKFLOWS), 0, "Registry must seed at least one workflow")

    def test_all_keys_are_lowercase_slugs(self):
        # Keys are stable lowercase slugs. Two families coexist by design: UI
        # workflows use kebab-case ("migration-cloud-connect-sis"), while the
        # system/orchestration workflows use snake_case because the key IS the
        # load-bearing identifier elsewhere — the Celery task name and the
        # persisted WorkflowRun.workflow_key / WorkflowAutopilotPolicy.workflow_key
        # (e.g. "tenant_school_provision"). Renaming those to kebab would orphan
        # live rows, so the slug rule is lowercase + no spaces, not no-underscore.
        for key in wf.WORKFLOWS:
            self.assertIsInstance(key, str)
            self.assertTrue(key, "Workflow key must not be empty")
            self.assertEqual(key, key.lower(), f"Workflow key {key!r} must be lowercase")
            self.assertNotIn(" ", key, f"Workflow key {key!r} must not contain spaces")
            self.assertRegex(key, r"^[a-z0-9]+([_-][a-z0-9]+)*$", f"Workflow key {key!r} must be a slug")

    def test_no_duplicate_titles_per_audience(self):
        seen: set[tuple[str, str]] = set()
        for key, wdef in wf.WORKFLOWS.items():
            audiences = getattr(wdef, "audience", None) or ()
            if isinstance(audiences, str):
                audiences = (audiences,)
            for aud in audiences:
                pair = (aud, getattr(wdef, "title", ""))
                self.assertNotIn(
                    pair, seen,
                    f"Duplicate (audience, title) for {key}: {pair}",
                )
                seen.add(pair)

    def test_all_workflows_carry_module_owner(self):
        # Per WorkflowDefinition's own docstring, `module` is "the Django app the
        # workflow lives under (e.g. 'migration_cloud')" — a bare app label, not a
        # filesystem path. Assert it is a non-empty lowercase label (traceable to
        # an owning app), not an apps/ path prefix.
        for key, wdef in wf.WORKFLOWS.items():
            module = getattr(wdef, "module", "")
            self.assertTrue(module, f"Workflow {key} has empty module owner")
            self.assertEqual(module, module.lower(), f"Workflow {key} module {module!r} must be lowercase")
            self.assertNotIn("/", module, f"Workflow {key} module {module!r} must be a Django app label, not a path")
            self.assertNotIn(" ", module, f"Workflow {key} module {module!r} must not contain spaces")

    def test_all_workflows_carry_purpose_sentence(self):
        for key, wdef in wf.WORKFLOWS.items():
            purpose = getattr(wdef, "purpose", "")
            self.assertTrue(purpose, f"Workflow {key} has empty purpose")
            self.assertGreater(len(purpose), 10, f"Workflow {key} purpose is suspiciously short")


class WorkflowRegistryAudienceTests(SimpleTestCase):
    def test_audience_values_are_known(self):
        for key, wdef in wf.WORKFLOWS.items():
            audiences = getattr(wdef, "audience", None) or ()
            if isinstance(audiences, str):
                audiences = (audiences,)
            for aud in audiences:
                self.assertIn(
                    aud, wf.ALL_AUDIENCES,
                    f"Workflow {key} audience {aud!r} not in ALL_AUDIENCES",
                )

    def test_audience_constants_match_values(self):
        # The 7 audience constants exposed by the module must each map to a
        # value present in ALL_AUDIENCES.
        constants = [getattr(wf, name) for name in dir(wf) if name.startswith("AUDIENCE_")]
        for c in constants:
            self.assertIn(c, wf.ALL_AUDIENCES)


class WorkflowRegistryTagTaxonomyTests(SimpleTestCase):
    def test_tag_taxonomy_at_least_19_entries(self):
        """Phase 2 spec requires the 19-tag taxonomy.

        We assert ``>= 19`` so the test stays green if Phase 4+ extends the
        taxonomy intentionally.
        """
        tag_constants = [n for n in dir(wf) if n.startswith("TAG_")]
        self.assertGreaterEqual(
            len(tag_constants), 19,
            f"Expected >= 19 TAG_ constants, found {len(tag_constants)}",
        )

    def test_tag_constants_are_kebab_case(self):
        for name in dir(wf):
            if not name.startswith("TAG_"):
                continue
            value = getattr(wf, name)
            self.assertIsInstance(value, str)
            self.assertEqual(value, value.lower())
            self.assertNotIn("_", value)
            self.assertNotIn(" ", value)

    def test_workflow_default_tags_are_registry_known(self):
        known_tag_values = {getattr(wf, n) for n in dir(wf) if n.startswith("TAG_")}
        for key, wdef in wf.WORKFLOWS.items():
            tags = getattr(wdef, "default_tags", None) or ()
            for t in tags:
                self.assertIn(
                    t, known_tag_values,
                    f"Workflow {key} references unknown tag {t!r}",
                )


class WorkflowRegistryStepsTests(SimpleTestCase):
    def test_steps_are_ordered_tuples_when_present(self):
        for key, wdef in wf.WORKFLOWS.items():
            steps = getattr(wdef, "steps", None)
            if steps is None or len(steps) == 0:
                continue
            self.assertTrue(hasattr(steps, "__iter__"))
            for step in steps:
                self.assertTrue(
                    hasattr(step, "key") or isinstance(step, dict),
                    f"Workflow {key} step lacks a key field: {step!r}",
                )

    def test_is_known_tag_helper(self):
        self.assertTrue(wf.is_known_tag(wf.TAG_REQUIRED))
        self.assertFalse(wf.is_known_tag("not-a-real-tag"))
        self.assertFalse(wf.is_known_tag(""))
