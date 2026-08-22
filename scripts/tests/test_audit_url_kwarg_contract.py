"""The signature check behind `scripts/audit_url_kwarg_contract.py`.

The gate exists because a view that cannot accept its own URL kwargs is a certain
500 that every other gate misses: the URL resolves, the view exists, the permission
passes, and only calling it fails. These tests pin the two directions it checks and
the deliberate false-negative bias that keeps it a zero-baseline gate.
"""
from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "audit_url_kwarg_contract.py"
_spec = importlib.util.spec_from_file_location("audit_url_kwarg_contract", SCRIPT)
mod = importlib.util.module_from_spec(_spec)
sys.modules["audit_url_kwarg_contract"] = mod
_spec.loader.exec_module(mod)


class SignatureRejectionTests(unittest.TestCase):
    def test_accepts_named_kwarg(self):
        def view(request, shell):
            return shell

        self.assertEqual(mod._signature_rejects(view, {"shell"}), set())

    def test_rejects_missing_kwarg(self):
        def view(request):
            return request

        self.assertEqual(mod._signature_rejects(view, {"shell"}), {"shell"})

    def test_var_keyword_absorbs_anything(self):
        def view(request, **kwargs):
            return kwargs

        self.assertEqual(mod._signature_rejects(view, {"shell", "anything"}), set())

    def test_required_but_unfilled_is_also_a_finding(self):
        # The symmetric failure: the URL supplies nothing, the view demands one.
        def view(request, item_id):
            return item_id

        self.assertEqual(mod._signature_rejects(view, set()), {"item_id"})

    def test_default_makes_an_unfilled_param_fine(self):
        def view(request, item_id=None):
            return item_id

        self.assertEqual(mod._signature_rejects(view, set()), set())

    def test_var_keyword_does_not_excuse_a_required_positional(self):
        def view(request, item_id, **kwargs):
            return item_id, kwargs

        self.assertEqual(mod._signature_rejects(view, set()), {"item_id"})

    def test_self_and_request_are_never_treated_as_url_kwargs(self):
        class View:
            def get(self, request):
                return request

        self.assertEqual(mod._signature_rejects(View.get, set()), set())

    def test_uninspectable_callable_is_not_accused(self):
        # Anything inspect cannot read is skipped rather than guessed at -- guessing
        # is what makes a gate un-baselineable.
        self.assertEqual(mod._signature_rejects(object(), {"shell"}), set())


class ClassBasedViewTests(unittest.TestCase):
    def test_every_defined_handler_must_accept(self):
        # Django calls handler(request, *args, **kwargs) for whichever verb is used,
        # so a `get` without the kwarg 500s even when `post` has it.
        class View:
            def get(self, request):
                return request

            def post(self, request, item_id):
                return item_id

        callback = lambda: None  # noqa: E731 - stands in for as_view()
        callback.view_class = View
        self.assertEqual(mod._accepts(callback, {"item_id"}), {"item_id"})

    def test_class_with_all_handlers_accepting_is_clean(self):
        class View:
            def get(self, request, item_id=None):
                return item_id

            def post(self, request, item_id=None):
                return item_id

        callback = lambda: None  # noqa: E731
        callback.view_class = View
        self.assertEqual(mod._accepts(callback, {"item_id"}), set())


class DecoratorUnwrapTests(unittest.TestCase):
    def test_wrapped_function_is_inspected_not_the_wrapper(self):
        import functools

        def inner(request, shell):
            return shell

        @functools.wraps(inner)
        def wrapper(*args, **kwargs):
            return inner(*args, **kwargs)

        # functools.wraps sets __wrapped__; without unwrapping, *args/**kwargs would
        # make every decorated view look safe.
        self.assertEqual(mod._accepts(wrapper, {"shell"}), set())
        # Both directions at once: the URL offers `nope` (which the view cannot take)
        # and offers no `shell` (which the view requires). Both are real 500s.
        self.assertEqual(mod._accepts(wrapper, {"nope"}), {"nope", "shell"})


if __name__ == "__main__":
    unittest.main()
