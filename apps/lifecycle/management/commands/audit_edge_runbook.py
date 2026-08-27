"""Audit the edge-onboarding runbook by RUNNING it, not by reading it.

A runbook rots quietly. A step keeps naming a management command that was renamed
two waves ago; a help_doc points at a file somebody moved; a self_heal is added and
nothing is wired to call it. None of that fails a test, because there is no test --
the runbook is data, and data that describes actions is only correct if the actions
still exist.

So this asks, for every step:

  A  does the manage.py command it tells somebody to type actually exist?
  B  does its named_url resolve?
  C  does its help_doc file exist?
  D  does validate() return a verdict rather than raising, on a hostile input?
  E  does self_heal() (where present) do the same?
  F  can heal_step actually DISPATCH each heal, and does a bring-up path reach it?
  G  are the keys unique and the prose present?

It changes nothing. Every check is a read or a call against an object with no
fields, so it is safe on a live box -- and being safe on a live box is the point,
because that is where a rotted runbook does its damage.

    python manage.py audit_edge_runbook
    python manage.py audit_edge_runbook --strict   # exit 1 on any FAIL
"""

from __future__ import annotations

import pathlib
import re
from types import SimpleNamespace

from django.apps import apps as django_apps
from django.core.management import get_commands
from django.core.management.base import BaseCommand
from django.urls import NoReverseMatch, reverse

from apps.lifecycle import edge_onboarding as eo

#: `manage.py <name>` inside a step's command_template.
_MANAGE = re.compile(r"manage\.py\s+([a-z0-9_]+)")

#: Heals the bring-up reaches other than through the verification-suite loop.
#: `verify_and_sync_gate` is listed because run_edge_bringup runs that gate itself
#: (step 4) rather than routing it through heal_step -- deliberate, and NOT the same
#: thing as the heal being unreachable. Conflating those produced a false FAIL the
#: first time this audit ran.
_EXPLICIT_PHASE = frozenset({"live_sync_proof", "go_dark_checklist"})
_RUN_DIRECTLY = frozenset({"verify_and_sync_gate"})


class Command(BaseCommand):
    help = "Audit the edge-onboarding runbook for internal soundness. Changes nothing."

    def add_arguments(self, parser):
        parser.add_argument(
            "--strict",
            action="store_true",
            help="Exit 1 when any check FAILs (for CI or a pre-rebuild gate).",
        )

    def handle(self, *args, **options):
        self.ok_msgs: list[str] = []
        self.warn_msgs: list[str] = []
        self.fail_msgs: list[str] = []

        steps = eo.EDGE_ONBOARDING_STEPS
        w = self.stdout.write
        w("=" * 70)
        w("EDGE ONBOARDING RUNBOOK AUDIT — %d steps" % len(steps))
        w("=" * 70)

        broken = SimpleNamespace()  # a school with no fields at all

        self._commands_exist(steps)
        self._urls_resolve(steps)
        self._help_docs_exist(steps)
        self._validators_return_verdicts(steps, broken)
        healable = self._heals_return_verdicts(steps, broken)
        self._heals_are_reachable(steps, healable, broken)
        self._structure(steps)

        w("")
        w("=" * 70)
        w(
            "  %d OK, %d WARN, %d FAIL"
            % (len(self.ok_msgs), len(self.warn_msgs), len(self.fail_msgs))
        )
        for m in self.warn_msgs:
            w(self.style.WARNING("  [WARN] %s" % m))
        for m in self.fail_msgs:
            w(self.style.ERROR("  [FAIL] %s" % m))
        if self.fail_msgs:
            w(self.style.ERROR("  VERDICT: %d defect(s) above." % len(self.fail_msgs)))
        else:
            w(self.style.SUCCESS("  VERDICT: the runbook is internally sound."))
        w("=" * 70)

        if options["strict"] and self.fail_msgs:
            raise SystemExit(1)

    # --- checks ------------------------------------------------------------
    def _commands_exist(self, steps):
        self.stdout.write("\n=== A. the commands the runbook tells people to type")
        known = set(get_commands())
        for s in steps:
            for name in _MANAGE.findall(s.command_template or ""):
                if name in known:
                    self._ok("%s -> manage.py %s exists" % (s.key, name))
                else:
                    self._bad(
                        "%s -> manage.py %s DOES NOT EXIST; the runbook names a "
                        "command nobody can run" % (s.key, name)
                    )

    def _urls_resolve(self, steps):
        self.stdout.write("\n=== B. named URLs the runbook links to")
        for s in steps:
            if not s.named_url_name:
                continue
            try:
                reverse(s.named_url_name)
                self._ok("%s -> %s resolves" % (s.key, s.named_url_name))
            except NoReverseMatch:
                # Host-split urlconf: a name absent HERE may be mounted on another
                # host, so this is not a defect on its own.
                self._warn(
                    "%s -> %s does not resolve on this host (host-split urlconf)"
                    % (s.key, s.named_url_name)
                )
            except Exception as exc:  # noqa: BLE001
                self._bad(
                    "%s -> %s raised %s" % (s.key, s.named_url_name, type(exc).__name__)
                )

    def _help_docs_exist(self, steps):
        self.stdout.write("\n=== C. help documents")
        root = pathlib.Path(django_apps.get_app_config("lifecycle").path).parents[1]
        for s in steps:
            if not s.help_doc:
                continue
            if (root / s.help_doc).exists():
                self._ok("%s -> %s exists" % (s.key, s.help_doc))
            else:
                self._bad("%s -> help_doc %s IS MISSING" % (s.key, s.help_doc))

    def _validators_return_verdicts(self, steps, broken):
        self.stdout.write("\n=== D. validate() on a hostile input (must never raise)")
        for s in steps:
            self._verdict(s.key, s.validate, broken, "validate")

    def _heals_return_verdicts(self, steps, broken):
        self.stdout.write("\n=== E. self-heals")
        healable = [s for s in steps if s.self_heal is not None]
        self.stdout.write(
            "    %d of %d steps carry a self-heal" % (len(healable), len(steps))
        )
        for s in healable:
            self._verdict(s.key, s.self_heal, broken, "heal")
        return healable

    def _heals_are_reachable(self, steps, healable, broken):
        self.stdout.write("\n=== F. reachability")
        preview = {s.key for s in steps if s.cloud_preview}
        for s in healable:
            res = eo.heal_step(broken, s.key)
            if "no self-heal" in str(res.get("detail", "")):
                self._bad("%s -> heal_step cannot dispatch it; the heal is dead" % s.key)
            else:
                self._ok("%s -> heal_step dispatches it" % s.key)
            if s.key in preview:
                self._ok("%s -> bring-up reaches it via the verification loop" % s.key)
            elif s.key in _EXPLICIT_PHASE:
                self._ok("%s -> bring-up reaches it via the go-dark phase" % s.key)
            elif s.key in _RUN_DIRECTLY:
                self._ok("%s -> bring-up runs this gate itself (step 4)" % s.key)
            else:
                self._warn(
                    "%s -> no bring-up path routes this heal; only a console call "
                    "reaches it" % s.key
                )

    def _structure(self, steps):
        self.stdout.write("\n=== G. structure")
        keys = [s.key for s in steps]
        if len(keys) == len(set(keys)):
            self._ok("all %d step keys are unique" % len(keys))
        else:
            self._bad(
                "duplicate step keys: %s" % sorted({k for k in keys if keys.count(k) > 1})
            )
        fields = ("title", "purpose", "category", "workaround")
        empty = [
            (s.key, f) for s in steps for f in fields if not getattr(s, f, "")
        ]
        if empty:
            for key, field in empty:
                self._bad("%s -> %s is empty" % (key, field))
        else:
            self._ok("every step carries title/purpose/category/workaround")

    # --- helpers -----------------------------------------------------------
    def _verdict(self, key, fn, school, label):
        try:
            res = fn(school)
        except Exception as exc:  # noqa: BLE001
            self._bad("%s -> %s RAISED %s: %s" % (key, label, type(exc).__name__, exc))
            return
        if isinstance(res, tuple) and len(res) == 2 and isinstance(res[0], bool):
            self._ok("%s -> %s returned a verdict, did not raise" % (key, label))
        else:
            self._bad("%s -> %s returned %r, not (bool, str)" % (key, label, res))

    def _ok(self, m):
        self.ok_msgs.append(m)

    def _warn(self, m):
        self.warn_msgs.append(m)

    def _bad(self, m):
        self.fail_msgs.append(m)
