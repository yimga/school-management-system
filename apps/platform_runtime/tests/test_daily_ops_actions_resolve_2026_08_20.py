"""The click-saving engine must not itself be a dead end.

``tenant_daily_ops`` is the platform's next-best-action registry: each entry
carries a ``clicks_saved`` figure, which makes it the one place where "fewer
clicks" is an actual number rather than an aspiration.

Twelve of its fifteen entries pointed at URL names that no longer existed —
every action for teachers, parents and students, plus half the admin set. The
names had drifted as apps were reorganised (``evals:teacher_gradebook`` became
``portal:teacher_gradebook``, ``finance:parent_payments`` became
``portal:parent_finance``, and so on) and nothing ever checked them.

``resolve_action_urls`` then returned ``url: ""`` for each one, so a caller
rendering these would draw a button that goes nowhere: the dead-end defect,
produced by the engine meant to prevent it.

Two things are pinned here. Every registered name must reverse, and an
unresolvable action must be DROPPED rather than emitted with an empty URL —
showing one fewer action costs a click, showing a broken one costs trust.
"""

from __future__ import annotations

from django.test import SimpleTestCase, override_settings
from django.urls import clear_url_caches, reverse

from apps.platform_runtime.tenant_daily_ops import (
    WORKFLOW_ACTIONS,
    resolve_action_urls,
)


@override_settings(ROOT_URLCONF="config.tenant_urls")
class EveryRegisteredActionResolvesTests(SimpleTestCase):
    def setUp(self):
        clear_url_caches()

    def test_every_daily_ops_action_resolves(self):
        dead: list[str] = []
        for role, actions in WORKFLOW_ACTIONS.items():
            for action in actions:
                name = action.get("url_name", "")
                try:
                    reverse(name)
                except Exception:  # noqa: BLE001 — any failure to reverse is the defect
                    dead.append(f"{role}/{action.get('key', '?')} -> {name}")
        self.assertEqual(
            dead,
            [],
            "next-best actions point at URL names that do not resolve, so the "
            "engine that exists to save clicks would render buttons to nowhere:\n"
            + "\n".join(f"  {row}" for row in dead),
        )

    def test_every_action_declares_the_clicks_it_saves(self):
        """The metric is the point — an action without it cannot be measured."""
        for role, actions in WORKFLOW_ACTIONS.items():
            for action in actions:
                with self.subTest(role=role, key=action.get("key")):
                    self.assertGreaterEqual(
                        int(action.get("clicks_saved", 0)),
                        1,
                        "an action that saves no clicks does not belong in the registry",
                    )

    def test_every_role_keeps_at_least_one_working_action(self):
        """Dropping unresolvable actions must not silently empty a role."""
        for role, actions in WORKFLOW_ACTIONS.items():
            with self.subTest(role=role):
                resolved = resolve_action_urls([dict(a) for a in actions])
                self.assertTrue(
                    resolved,
                    f"{role} has no working next-best action left after resolution",
                )


@override_settings(ROOT_URLCONF="config.tenant_urls")
class UnresolvableActionsAreDroppedTests(SimpleTestCase):
    def setUp(self):
        clear_url_caches()

    def test_an_unresolvable_action_is_dropped_not_emitted_empty(self):
        rows = resolve_action_urls(
            [{"key": "ghost", "label": "Nowhere", "url_name": "no_such:route"}]
        )
        self.assertEqual(
            rows, [], "an action with no destination was emitted instead of dropped"
        )

    def test_an_action_with_no_url_name_is_dropped(self):
        rows = resolve_action_urls([{"key": "bare", "label": "No destination"}])
        self.assertEqual(rows, [])

    def test_a_resolvable_action_survives_with_a_real_url(self):
        rows = resolve_action_urls(
            [{"key": "fees", "label": "Invoices", "url_name": "finance:invoices"}]
        )
        self.assertEqual(len(rows), 1)
        self.assertTrue(
            rows[0]["url"].startswith("/"), "a surviving action must carry a real path"
        )
        self.assertNotIn("url_name", rows[0], "the raw name should not leak to callers")

    def test_no_surviving_action_ever_carries_an_empty_url(self):
        """The invariant the caller depends on."""
        for role, actions in WORKFLOW_ACTIONS.items():
            for row in resolve_action_urls([dict(a) for a in actions]):
                with self.subTest(role=role, key=row.get("key")):
                    self.assertTrue(row.get("url"), "empty URL survived resolution")
