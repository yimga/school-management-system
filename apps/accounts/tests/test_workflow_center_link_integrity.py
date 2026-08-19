"""Every Workflow Center menu item must actually resolve.

`_workflow_link` swallows ``NoReverseMatch`` and returns ``None`` so a step never
renders a dead button. The cost of that defence is silence: a typo, a renamed route,
or a model that was never registered in the admin makes the menu item simply *vanish*,
and nothing anywhere fails. The Workflow Center is the platform's front door — "the
place where everything concerning the platform can be accessed from" — so a step
quietly shipping 2 of its 3 links is a real, invisible product regression.

That is not hypothetical: ``admin:evals_gradeapprovalrequest_changelist`` named a
model `apps/evals/admin.py` never registers, so step 3 "Marks entry + OCR" shipped
without its "Approval requests" row on every host — while the step's own tip told
operators to use approval requests.

The existing `verify_url_name_integrity` gate cannot catch this class: it scans for
literals passed to ``reverse()`` / ``{% url %}``, and these names are arguments to a
helper. This module closes that blind spot by reading the URL names straight out of
the view source, so a link added tomorrow is covered without touching this file.
"""

from __future__ import annotations

import ast
import inspect
from pathlib import Path

from django.test import SimpleTestCase, override_settings
from django.urls import NoReverseMatch, get_resolver, reverse

from apps.accounts import views_workflow

TENANT_URLCONF = "config.tenant_urls"

#: Names whose absence is a deliberate, host-scoped degradation rather than a bug.
#: Keep this EMPTY unless you can explain why the row should disappear silently.
KNOWN_HOST_SCOPED: frozenset[str] = frozenset()


def _workflow_link_url_names() -> set[str]:
    """Second positional argument of every ``_workflow_link(...)`` call in the view."""
    source = Path(inspect.getfile(views_workflow)).read_text(encoding="utf8")
    tree = ast.parse(source)
    names: set[str] = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if not (isinstance(func, ast.Name) and func.id == "_workflow_link"):
            continue
        if len(node.args) < 2:
            continue
        target = node.args[1]
        if isinstance(target, ast.Constant) and isinstance(target.value, str):
            names.add(target.value)
    return names


def _registered_url_names(urlconf: str) -> set[str]:
    """Every ``namespace:name`` (and bare ``name``) registered on ``urlconf``.

    Membership — not ``reverse()`` — is the right question here. Some Workflow Center
    destinations are argument-taking routes (``portal:portal_feature`` needs a
    ``feature`` kwarg), and the view supplies those kwargs at call time. Asking
    "is this route registered?" covers both shapes without hard-coding arguments.
    """

    def walk(resolver, prefix: str, seen: set[str]) -> None:
        for key in resolver.reverse_dict:
            if isinstance(key, str):
                seen.add(f"{prefix}{key}")
        for namespace, (_p, sub) in resolver.namespace_dict.items():
            walk(sub, f"{prefix}{namespace}:", seen)

    names: set[str] = set()
    walk(get_resolver(urlconf), "", names)
    return names


class WorkflowLinkNameExtractionTests(SimpleTestCase):
    """The extractor itself must not silently find nothing."""

    def test_extractor_finds_the_expected_shape_of_call_sites(self):
        names = _workflow_link_url_names()
        self.assertGreater(
            len(names),
            25,
            "AST extraction found suspiciously few _workflow_link call sites — "
            "if the helper was renamed or the calls restructured, update this test "
            "rather than letting the coverage evaporate.",
        )
        self.assertIn("accounts:clone_year_setup", names)


class WorkflowCenterLinkResolutionTests(SimpleTestCase):
    """Every advertised destination resolves on the tenant urlconf."""

    @override_settings(ROOT_URLCONF=TENANT_URLCONF)
    def test_every_workflow_link_resolves(self):
        # Two acceptance paths, because Workflow Center links come in two shapes:
        # argument-free routes must reverse outright, while argument-taking ones
        # (portal:portal_feature) only need to be REGISTERED — the view supplies
        # their kwargs at call time.
        registered = _registered_url_names(TENANT_URLCONF)
        unresolved = []
        for name in sorted(_workflow_link_url_names()):
            if name in KNOWN_HOST_SCOPED:
                continue
            try:
                reverse(name, urlconf=TENANT_URLCONF)
                continue
            except (NoReverseMatch, AttributeError, TypeError, ValueError):
                pass
            if name not in registered:
                unresolved.append(name)
        self.assertEqual(
            unresolved,
            [],
            "Workflow Center links that silently vanish from the menu because the "
            f"URL name is not registered on {TENANT_URLCONF}: {unresolved}",
        )

    @override_settings(ROOT_URLCONF=TENANT_URLCONF)
    def test_grade_approvals_row_is_reachable(self):
        """Pins the specific row that shipped missing from step 3."""
        self.assertTrue(reverse("evals:grade_approval_list", urlconf=TENANT_URLCONF))
        self.assertNotIn(
            "admin:evals_gradeapprovalrequest_changelist",
            _workflow_link_url_names(),
            "GradeApprovalRequest is not registered in apps/evals/admin.py, so this "
            "name can only ever resolve to nothing.",
        )
