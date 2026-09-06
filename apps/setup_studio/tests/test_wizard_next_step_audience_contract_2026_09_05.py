"""The wizard next-step graph must only suggest wizards the user can open.

``wizard_next_steps._SUGGESTIONS`` is the registry that answers "what should
this person do now?" the moment a wizard finishes. It had no test of any kind,
and three of its sixteen outgoing edges were wrong in a way nothing could see:

* ``cross_platform_whitelabel_branding`` is an ``operator`` wizard whose only
  suggestion was constrained to ``tenant_admin``. ``get_suggestions`` filters on
  that constraint, so the chip could never render for anybody -- the wizard was
  a dead end while appearing wired.
* ``custom_domain_setup`` and ``account_migration`` each pointed a
  ``tenant_admin``-constrained suggestion at an ``operator``-only target. The
  chip rendered, and clicking it hit ``_user_can_run_wizard`` -> ``False`` ->
  ``redirect("/")``. The suggested next step bounced the user off the flow.

Both directions are asserted here because they fail differently: a constraint
the source audience does not contain never fires, and a target that excludes the
effective audience fires and then bounces. A registry can hold either mistake
while every other gate stays green -- the names all resolve, the JSON all
parses, and no view raises.

Pure registry assertions: the wizard registry is populated at import, so this
needs no database.
"""

from __future__ import annotations

from django.test import SimpleTestCase

from apps.setup_studio import wizard_engine, wizard_next_steps


def _registry():
    if not wizard_engine.WIZARD_REGISTRY:
        wizard_engine.load_wizard_registry()
    return wizard_engine.WIZARD_REGISTRY


class WizardNextStepAudienceContractTests(SimpleTestCase):
    def test_registry_is_not_empty(self):
        """Calibration: an empty registry would make every assertion below vacuous."""
        self.assertGreater(len(_registry()), 0)
        self.assertGreater(len(wizard_next_steps.source_wizards()), 0)

    def test_every_source_wizard_is_registered(self):
        reg = _registry()
        unknown = [k for k in wizard_next_steps.source_wizards() if k not in reg]
        self.assertEqual(unknown, [], f"suggestions keyed on unregistered wizards: {unknown}")

    def test_every_suggestion_target_is_registered(self):
        reg = _registry()
        unknown = [t for t in wizard_next_steps.list_suggested_targets() if t not in reg]
        self.assertEqual(unknown, [], f"suggestions point at unregistered wizards: {unknown}")

    def test_no_suggestion_is_constrained_to_an_audience_its_source_lacks(self):
        """A constraint the source wizard does not serve can never fire.

        ``get_suggestions`` is called with the RUNTIME user's audience, and a
        user only reaches the source wizard's completion screen when their
        audience is in the source's ``audience`` array. So a constraint outside
        that array filters the suggestion out on every possible request.
        """
        reg = _registry()
        broken = []
        for key in wizard_next_steps.source_wizards():
            source = reg.get(key)
            if source is None:
                continue
            for suggestion in wizard_next_steps.get_suggestions(key):
                constraint = suggestion.audience_constraint
                if constraint is not None and constraint not in source.audience:
                    broken.append(
                        f"{key} (audience={list(source.audience)}) -> "
                        f"{suggestion.target_wizard_key} constrained to {constraint!r}"
                    )
        self.assertEqual(broken, [], "suggestions that can never fire:\n  " + "\n  ".join(broken))

    def test_no_suggestion_points_at_a_wizard_the_reader_cannot_open(self):
        """Every audience that can SEE a chip must be admitted by its target.

        ``TenantWizardView.get`` refuses a wizard whose audience array excludes
        the user and redirects to ``/``. A chip that renders for an audience the
        target does not serve is therefore a bounce, not a next step.
        """
        reg = _registry()
        broken = []
        for key in wizard_next_steps.source_wizards():
            source = reg.get(key)
            if source is None:
                continue
            for audience in source.audience:
                for suggestion in wizard_next_steps.get_suggestions(key, audience=audience):
                    target = reg.get(suggestion.target_wizard_key)
                    if target is None:
                        continue
                    if audience not in target.audience:
                        broken.append(
                            f"{key} shown to {audience!r} -> {suggestion.target_wizard_key} "
                            f"(audience={list(target.audience)}) would redirect to /"
                        )
        self.assertEqual(broken, [], "suggestions that bounce the user:\n  " + "\n  ".join(broken))

    def test_a_suggestion_actually_fires_for_each_source_wizard(self):
        """Every registered source must yield at least one chip for some real audience.

        This is what caught ``cross_platform_whitelabel_branding``: it had an
        entry in the registry, so it did not read as a dead end, but no audience
        could ever see the chip.
        """
        reg = _registry()
        never_fires = []
        for key in wizard_next_steps.source_wizards():
            source = reg.get(key)
            if source is None:
                continue
            if not any(
                wizard_next_steps.get_suggestions(key, audience=audience)
                for audience in source.audience
            ):
                never_fires.append(f"{key} (audience={list(source.audience)})")
        self.assertEqual(
            never_fires, [], "source wizards whose chips never render:\n  " + "\n  ".join(never_fires)
        )
