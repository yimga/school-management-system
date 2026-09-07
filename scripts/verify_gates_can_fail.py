#!/usr/bin/env python
"""Meta-gate: prove every pre-push boundary gate can still FAIL.

WHY THIS EXISTS
---------------
This repository defends itself with 63 zero-baseline gates, and on a good day
every one of them prints PASS. But "PASS" answers two completely different
questions with the same word:

    1. the tree is clean, or
    2. the gate cannot see.

Nothing here could tell those apart, and case 2 is not hypothetical. Four gates
wired on 2026-08-27 had "existed, passed, and enforced nothing" written into
their own registry comment. ``verify_audit_log_append_only`` matched the last
two names of an attribute chain, so it could only ever see a bare
``AuditLog.objects.update()`` -- a form that is not valid Django and nobody
writes -- and printed PASS while a real ``filter(...).update()`` sat in
apps/compliance/privacy.py. ``scan_sms_template_length`` only opened files whose
NAME said sms. A scan reporting 0 hits was once found broken and returned 678
once fixed.

``verify_ci_gate_wiring.py`` closed the neighbouring hole: it proves a gate is
INVOKED. It cannot prove the gate, once invoked, does anything. This one can.

HOW
---
For every label in ``pre_push_boundary_check.GATES`` and ``DJANGO_GATES`` this
holds a mutation: a small, specific, real-world defect of exactly the class that
gate claims to catch. It plants the defect and runs the gate. A gate that still
exits 0 with its own defect sitting in the tree is DEAD, and that is a finding.

The completeness check is the other half. Every registered gate must have a
mutation or an explicit, reasoned entry in ``UNPROVEN``. A new gate cannot be
added to the pre-push runner and quietly skip its own proof -- the same
structural trick ``verify_ci_gate_wiring.REQUIRED_GATES`` uses.

ISOLATION
---------
Mutations are applied in a DETACHED GIT WORKTREE, never in the checkout you are
sitting in. Several agents share this working tree and it usually carries
uncommitted work; planting deliberate defects in it is how you lose someone
else's afternoon. Worktree isolation also makes the restore path non-critical:
if this harness is killed mid-case -- and a background timeout HAS killed a
mutation harness here before, after which ``finally`` never ran -- the damage is
confined to a scratch directory that gets deleted, rather than to real files
that ``finally`` failed to put back.

USAGE
-----
    python scripts/verify_gates_can_fail.py                 # all gates
    python scripts/verify_gates_can_fail.py --gate off-token-colors
    python scripts/verify_gates_can_fail.py --list          # coverage only
    python scripts/verify_gates_can_fail.py --keep-worktree # for debugging

Exit 0 when every gate proved it can fail. Exit 1 on any DEAD gate, missing
mutation, or stale anchor.
"""
from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "scripts") not in sys.path:
    sys.path.insert(0, str(ROOT / "scripts"))

import pre_push_boundary_check as ppbc  # noqa: E402

# A gate that takes longer than this is reported TIMEOUT, never DEAD. A timeout
# is a resource result, not a finding -- the pre-push runner says the same.
DEFAULT_GATE_TIMEOUT_S = 240


@dataclass(frozen=True)
class Mutation:
    """One planted defect, and the gate it must wake up.

    ``create`` is preferred over ``patch`` wherever the gate is a tree scan: a
    new file carrying the violation cannot go stale the way a byte anchor in
    someone else's file does. ``patch`` and ``delete`` are for gates that assert
    something is PRESENT, where the only way to trip them is to take it away.
    """

    kind: str  # "create" | "patch" | "delete"
    path: str  # repo-relative, POSIX separators
    defect: str  # the real-world failure this stands in for
    content: bytes = b""
    anchor: bytes = b""
    replacement: bytes = b""
    # Replace EVERY occurrence, not just the first. A gate that asks
    # `"marker" in text` is satisfied by any surviving copy, so removing one of
    # two leaves the gate green and the harness reports a false DEAD.
    all_occurrences: bool = False


def _crlf_variants(needle: bytes) -> list[bytes]:
    """Anchors must match the bytes on disk, and this repo is not consistent.

    Some files are committed CRLF and a handful carry ``\r\r\n``. A harness
    that only tries LF silently reports SKIP on exactly those files, which reads
    as 'nothing to prove here' rather than 'the proof did not run'.
    """
    out = [needle]
    if b"\n" in needle:
        out.append(needle.replace(b"\n", b"\r\n"))
        out.append(needle.replace(b"\n", b"\r\r\n"))
    return out


class Workspace:
    """A detached worktree at HEAD that mutations are applied inside."""

    def __init__(self, path: Path, keep: bool = False) -> None:
        self.path = path
        self.keep = keep
        self._created = False

    @staticmethod
    def _head(path: Path) -> str:
        """The commit a checkout is actually on, or "" if it cannot be read."""
        proc = subprocess.run(
            ["git", "-C", str(path), "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
        )
        return proc.stdout.strip() if proc.returncode == 0 else ""

    def __enter__(self) -> "Workspace":
        if self.path.exists() and (self.path / "manage.py").exists():
            # Reuse is cheaper than a 20s checkout, but only to the commit
            # THIS repo is on. A bare ``git reset --hard`` resets to the
            # WORKTREE's own HEAD, and a scratch worktree left behind by a
            # killed run is still detached at the commit it was made for --
            # so the next gate measured the PREVIOUS commit and printed a
            # clean number for a tree that did not contain the change under
            # test. Measured: a run reported 0 findings against a HEAD it
            # had never checked out. Reset to an explicit sha, then prove it
            # took; anything else falls through to a fresh checkout.
            wanted = self._head(ROOT)
            if wanted:
                subprocess.run(
                    [
                        "git",
                        "-C",
                        str(self.path),
                        "reset",
                        "--hard",
                        "--quiet",
                        wanted,
                    ],
                    capture_output=True,
                )
                subprocess.run(
                    ["git", "-C", str(self.path), "clean", "-fdq"],
                    capture_output=True,
                )
                if self._head(self.path) == wanted:
                    return self
            # Could not read a sha, or the reset did not take. Rebuilding is
            # slow; measuring the wrong commit is wrong.
            subprocess.run(
                ["git", "-C", str(ROOT), "worktree", "remove", "--force", str(self.path)],
                capture_output=True,
            )
        if self.path.exists():
            shutil.rmtree(self.path, ignore_errors=True)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        subprocess.run(["git", "-C", str(ROOT), "worktree", "prune"], capture_output=True)
        proc = subprocess.run(
            ["git", "-C", str(ROOT), "worktree", "add", "--detach", str(self.path), "HEAD"],
            capture_output=True,
            text=True,
        )
        if proc.returncode != 0:
            raise SystemExit(f"could not create worktree at {self.path}:\n{proc.stderr}")
        self._created = True
        # Untracked-but-required local config. Django gates import settings, and
        # settings reads .env; without it they fail for a reason that has
        # nothing to do with the mutation under test.
        for name in (".env", ".env.local"):
            src = ROOT / name
            if src.exists():
                shutil.copy2(src, self.path / name)
        return self

    def __exit__(self, *exc: object) -> None:
        # A REUSED worktree is torn down too. Leaving it is what let a stale
        # one survive from run to run in the first place.
        if self.keep:
            return
        subprocess.run(
            ["git", "-C", str(ROOT), "worktree", "remove", "--force", str(self.path)],
            capture_output=True,
        )
        subprocess.run(["git", "-C", str(ROOT), "worktree", "prune"], capture_output=True)

    # -- mutation application -------------------------------------------------

    def apply(self, mutation: Mutation) -> tuple[bool, str, object]:
        """Plant one defect. Returns (applied, explanation, restore_token)."""
        target = self.path / mutation.path
        if mutation.kind == "create":
            if target.exists():
                return False, f"{mutation.path} already exists; pick an unused path", None
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(mutation.content)
            # Intent-to-add, or half these scanners never see the file. Several
            # enumerate with `git ls-files` rather than walking the filesystem
            # -- scan_duplicate_dict_keys says so in its own docstring -- so an
            # untracked planted defect is invisible and the gate reports a
            # truthful, useless zero. That is the same "the scan could not see"
            # failure this harness exists to catch, and it bit the harness first.
            subprocess.run(
                ["git", "-C", str(self.path), "add", "-N", "--", mutation.path],
                capture_output=True,
            )
            return True, "created", None
        if not target.exists():
            return False, f"{mutation.path} is missing (mutation spec has drifted)", None
        original = target.read_bytes()
        if mutation.kind == "delete":
            target.unlink()
            return True, "deleted", original
        for needle in _crlf_variants(mutation.anchor):
            if needle in original:
                repl = mutation.replacement
                if needle != mutation.anchor and b"\n" in repl:
                    # Match the line endings actually on disk, or the patched
                    # file becomes a whole-file diff and the gate may fail for
                    # the rewrite rather than for the planted defect.
                    sep = needle[needle.index(b"\n") - 1 : needle.index(b"\n") + 1]
                    repl = repl.replace(b"\n", b"\r\n" if sep.startswith(b"\r") else b"\n")
                count = -1 if mutation.all_occurrences else 1
                patched = original.replace(needle, repl, count)
                if patched == original:
                    return False, f"replacement is a no-op in {mutation.path}", None
                target.write_bytes(patched)
                return True, "patched", original
        return False, f"anchor not found in {mutation.path} (spec has drifted)", None

    def reset(self) -> None:
        """Put the worktree back to HEAD, whatever the last gate did to it.

        Per-file restore is not enough. Several scanners WRITE while they run --
        sweep_django_admin_platformwide_layout rewrites
        var/admin-surface-platformwide-sweep.json on a bare invocation. If that
        happens during the mutated run, the unmutated confirmation run then
        compares against a baseline that already contains the planted defect,
        and a perfectly healthy gate is reported BASELINE-RED. A scanner that
        authors its own reference is the exact shape this harness exists to
        catch; it must not be allowed to corrupt the harness too.
        """
        # reset --hard, not checkout: an intent-to-add entry survives both
        # `checkout -- .` and `clean -fd`, so a planted file would leak into the
        # next gate's corpus and be read as a pre-existing violation.
        subprocess.run(
            ["git", "-C", str(self.path), "reset", "--hard", "--quiet"], capture_output=True
        )
        subprocess.run(["git", "-C", str(self.path), "clean", "-fdq"], capture_output=True)

    def restore(self, mutation: Mutation, token: object) -> None:
        target = self.path / mutation.path
        if mutation.kind == "create":
            target.unlink(missing_ok=True)
            return
        if isinstance(token, bytes):
            target.write_bytes(token)


def _run_gate(workspace: Workspace, argv: list[str], python: str, timeout: int) -> tuple[int, str]:
    cmd = [python, str(workspace.path / "scripts" / argv[0]), *argv[1:]]
    env = dict(os.environ)
    env.setdefault("PYTHONIOENCODING", "utf-8")
    env["PYTHONPATH"] = str(workspace.path)
    try:
        proc = subprocess.run(
            cmd,
            cwd=str(workspace.path),
            capture_output=True,
            text=True,
            errors="replace",
            timeout=timeout,
            env=env,
        )
    except subprocess.TimeoutExpired:
        return -9, "TIMEOUT"
    return proc.returncode, ((proc.stdout or "") + (proc.stderr or ""))[-1200:]


# ---------------------------------------------------------------------------
# The registry. One entry per label in pre_push_boundary_check.GATES /
# DJANGO_GATES. Each mutation is the smallest defect of the class that gate
# exists to catch -- not a random edit that happens to make it unhappy.
# ---------------------------------------------------------------------------

_PROOF = "_gateproof"  # every planted file carries this, so a stray one is obvious

MUTATIONS: dict[str, Mutation] = {
    # -- the four floor gates: code that does not parse or does not close -----
    "python-files-parse": Mutation(
        kind="create",
        path=f"apps/schools/{_PROOF}_syntax.py",
        defect="a module with a syntax error, which makes every gate below it answer about a tree that does not run",
        content=b"def broken(:\n    return 1\n",
    ),
    "javascript-files-parse": Mutation(
        kind="create",
        path=f"static/js/{_PROOF}_syntax.js",
        defect="JS that does not parse: the tag 200s, the console throws, one feature is dead and nothing else notices",
        content=b"function broken( {\n  return 1;\n}\n",
    ),
    # A JSON island is assembled as TEXT, so an unescaped value carrying a double
    # quote closes the string early and the island stops parsing. The page is
    # still 200 and still renders -- one feature is simply dead, in the locale
    # whose catalog happens to hold the quote, which is why English never shows
    # it. The planted template puts a bare {% trans %} inside a JSON string,
    # exactly the shape the cmdk palette shipped on every shell.
    "json-island-escaping": Mutation(
        kind="create",
        path=f"templates/portal/{_PROOF}_json_island.html",
        defect="an unescaped {% trans %} inside a JSON island: one quoted translation empties the feature silently",
        content=(
            b'<script type="application/json" id="rmc-gateproof-island">{\n'
            b'  "label": "{% trans "Open command palette" %}"\n'
            b"}</script>\n"
        ),
    ),
    "template-html-structure": Mutation(
        kind="create",
        # A partial, not a root-level file, and an unclosed DIV rather than a
        # span: the balance walker deliberately tolerates phrasing elements a
        # browser auto-closes, and the class it exists for is the unclosed
        # block-level container.
        path=f"templates/portal/{_PROOF}_unclosed.html",
        defect="an unclosed <div> - the page 200s and the browser silently reparents everything after it",
        content=b'<section>\n  <div class="wrap">text\n</section>\n',
    ),
    "duplicate-dict-keys": Mutation(
        kind="create",
        path=f"apps/schools/{_PROOF}_dupe.py",
        defect="a dict literal declaring the same key twice - Python keeps the last and discards the first in silence",
        content=b'SETTINGS = {\n    "timeout": 30,\n    "retries": 2,\n    "timeout": 60,\n}\n',
    ),
    # -- CSS / template token discipline --------------------------------------
    "off-token-colors": Mutation(
        kind="create",
        path=f"static/css/{_PROOF}_offtoken.css",
        defect="a raw hex colour outside the design-token cascade, which renders the wrong hue on every theme",
        content=b".gateproof-card {\n  color: #ab12cd;\n  background-color: rgba(12, 34, 56, 0.8);\n}\n",
    ),
    "undefined-css-classes": Mutation(
        kind="create",
        path=f"templates/{_PROOF}_undefined_class.html",
        defect="a class referenced in markup that no stylesheet defines - the element renders unstyled",
        content=b'<div class="rmc-gateproof-class-that-no-stylesheet-defines">x</div>\n',
    ),
    "inline-style-off-token": Mutation(
        kind="create",
        path=f"templates/{_PROOF}_inline_style.html",
        defect="a style= attribute carrying a hard-coded colour and pixel value, bypassing the token system",
        content=b'<div style="color: #ab12cd; padding: 13px;">x</div>\n',
    ),
    "inline-event-handlers": Mutation(
        kind="create",
        path=f"templates/{_PROOF}_onclick.html",
        defect="an inline onclick=, which a strict script-src with no 'unsafe-inline' silently blocks",
        content=b'<button type="button" onclick="doThing()">Go</button>\n',
    ),
    "theme-locked-token-text": Mutation(
        kind="create",
        path=f"static/css/{_PROOF}_locked.css",
        defect="text colour locked to a fixed light-mode token, which turns invisible in dark mode",
        content=b".gateproof-locked {\n  color: var(--gray-900);\n}\n",
    ),
    "undefined-color-token-fallback": Mutation(
        kind="create",
        path=f"static/css/{_PROOF}_undefined_token.css",
        defect="var(--never-declared) with no fallback - not an error, the element just inherits and the control goes invisible",
        content=b".gateproof-invisible {\n  color: var(--rmc-gateproof-token-never-declared);\n}\n",
    ),
    "theme-hue-coherence": Mutation(
        kind="create",
        path=f"static/css/{_PROOF}_hue.css",
        defect="a theme whose surfaces come from a different hue family than its ground - contrast gates stay green while it does",
        content=(
            b'[data-theme="gateproof"] {\n'
            b"  --bg-app: #f2f6ff;\n"
            b"  --surface-1: #fff5ec;\n"
            b"  --surface-2: #fff1e2;\n"
            b"  --text-primary: #1a1d29;\n"
            b"}\n"
        ),
    ),
    # -- template render safety ------------------------------------------------
    "template-render-safety": Mutation(
        kind="create",
        path=f"templates/{_PROOF}_multiline_comment.html",
        defect="a MULTI-LINE {# #} comment - Django only supports single-line, so the rest renders onto the page",
        content=b"<div>\n{# this comment\n   keeps going onto a second line #}\n</div>\n",
    ),
    "attribute-context-includes": Mutation(
        kind="create",
        path=f"templates/{_PROOF}_attr_include.html",
        defect="an {% include %} inside a tag's attribute list, whose partial emits a top-level element",
        content=b'<div {% include "partials/gateproof_attrs.html" %}>x</div>\n',
    ),
    "include-with-default-context-var": Mutation(
        kind="create",
        path=f"templates/{_PROOF}_eager_default.html",
        defect="|default: with a bare context var - Django resolves filter ARGS eagerly, so a missing var is a 500",
        content=b'{% include "partials/x.html" with title=page_title|default:fallback_title %}\n',
    ),
    "raw-token-in-ui": Mutation(
        kind="create",
        path=f"templates/{_PROOF}_cut.html",
        defect='|cut:"_" on a token - cut DELETES the character, so funding_type became "fundingtype" on a live banner',
        content=b'<p>Next: {{ evidence_key|cut:"_" }}</p>\n',
    ),
    # -- Python correctness / tenancy -----------------------------------------
    "broad-except-baseline": Mutation(
        kind="create",
        path=f"apps/schools/{_PROOF}_broad_except.py",
        defect="a bare except Exception that swallows the failure it was not written for",
        content=b"def probe():\n    try:\n        return compute()\n    except Exception:\n        return None\n",
    ),
    "school-in-defaults-not-lookup": Mutation(
        kind="create",
        path=f"apps/schools/{_PROOF}_defaults.py",
        defect="school inside defaults= not the lookup - update_or_create matches ANOTHER tenant's row and re-parents it",
        content=(
            b"def upsert(model, school, key, value):\n"
            b"    return model.objects.update_or_create(\n"
            b"        field_key=key,\n"
            b'        defaults={"school": school, "value": value},\n'
            b"    )\n"
        ),
    ),
    "unregistered-middleware": Mutation(
        kind="create",
        path=f"apps/schools/{_PROOF}_middleware.py",
        defect="a middleware defined, correct, and in no MIDDLEWARE list - it imports cleanly and never runs",
        content=(
            b"class GateProofAutosyncMiddleware:\n"
            b"    def __init__(self, get_response):\n"
            b"        self.get_response = get_response\n\n"
            b"    def __call__(self, request):\n"
            b"        return self.get_response(request)\n"
        ),
    ),
}

MUTATIONS.update({
    # -- the admin surface family ---------------------------------------------
    # These assert markers are PRESENT, so the only way to trip them is to take
    # something away. Where the mutation removes a whole subject file it is
    # marked "subject-removal": it proves the gate still reads its own input,
    # which is the failure mode that actually happened here (a gate policing
    # assets that no longer existed), but it does not prove marker-level acuity.
    "admin-canvas-contract": Mutation(
        kind="delete",
        path="static/css/rmc-admin-emergency-full-canvas-v17.css",
        defect="subject-removal: the full-canvas stylesheet the contract is written about is gone",
    ),
    "admin-surface-leftovers": Mutation(
        kind="delete",
        path="static/css/admin-cp-parity.css",
        defect="subject-removal: the parity sheet the leftover scan reads is gone",
    ),
    "admin-os-empty-space": Mutation(
        kind="delete",
        path="static/css/rmc-admin-django-canvas-contract.css",
        defect="subject-removal: the canvas contract sheet that seals full-bleed is gone",
    ),
    "admin-os-sections-restore": Mutation(
        kind="delete",
        path="static/css/rmc-admin-approval-surface-v15.css",
        defect="subject-removal: the v15 approval surface sheet the section restore is sealed against is gone",
    ),
    "admin-os-three-click-sla": Mutation(
        kind="delete",
        path="templates/admin/index_superadmin.html",
        defect="the operator index is gone, so Discover -> changelist cannot be <=3 interactions",
    ),
    "admin-production-upgrade": Mutation(
        kind="delete",
        path="static/css/rmc-admin-production-polish-v18.css",
        defect="subject-removal: the v18 production polish sheet the fail-closed upgrade contract requires is gone",
    ),
    "admin-miss-nothing": Mutation(
        kind="delete",
        path="static/css/admin-cp-parity.css",
        defect="subject-removal: the parity sheet the authoritative layout audit reads is gone",
    ),
    "admin-platformwide-sweep": Mutation(
        kind="create",
        path=f"templates/admin/{_PROOF}_layout_page.html",
        defect="an admin content page with no workspace marker - the layout class this sweep owns",
        content=b'{% extends "admin/base_site.html" %}\n{% block content %}\n  <p>gateproof</p>\n{% endblock %}\n',
    ),
    "admin-change-form-product-links": Mutation(
        kind="create",
        path=f"templates/admin/{_PROOF}/change_form.html",
        defect="a tenant change_form with no product-surface link and no exemption marker - a dead-end admin page",
        content=b'{% extends "admin/change_form.html" %}\n{% block content %}{{ block.super }}{% endblock %}\n',
    ),
    "admin-sidebar-v3": Mutation(
        kind="patch",
        path="templates/admin/sidebar_v3_body.html",
        defect="the work-areas region removed from the shared sidebar body - one of the seven IA regions gone",
        anchor=b"data-rmc-admin-work-areas",
        replacement=b"data-rmc-gateproof-region-removed",
    ),
    "admin-super-help-nav-bridge": Mutation(
        kind="patch",
        path="templates/admin/sidebar_v3_body.html",
        defect="the manager help centre link dropped from admin chrome - exactly what shrinking app_list.html did on 2026-08-27",
        anchor=b"manager_help_center",
        replacement=b"gateproof_removed_namespace",
        all_occurrences=True,
    ),
    "admin-replacement-roadmap": Mutation(
        kind="patch",
        path="scripts/verify_admin_replacement_roadmap.py",
        defect="the roadmap artifact path repointed at nothing - the gate must fail when its artifact is absent",
        anchor=b"docs/generated/",
        replacement=b"docs/generated/gateproof_absent/",
    ),
    "django-admin-preview-parity": Mutation(
        kind="delete",
        path="templates/admin/base_site.html",
        defect="the admin shell the approval HTML is compared against is gone - the 'CSS-only commit looks unchanged after deploy' class",
    ),
    "admin-unmounted-site": Mutation(
        kind="create",
        path=f"apps/schools/{_PROOF}_admin_site.py",
        defect="an admin registered on a site no urlconf mounts - a page nobody can open",
        content=(
            b"from django.contrib.admin import AdminSite, ModelAdmin\n\n"
            b'gateproof_site = AdminSite(name="gateproof_unmounted")\n\n\n'
            b"class GateProofAdmin(ModelAdmin):\n"
            b"    pass\n"
        ),
    ),
    "rls-bypass": Mutation(
        kind="create",
        path=f"apps/schools/{_PROOF}_rls_bypass.py",
        defect=(
            "a raw cursor.execute() outside set_rls_school_id() - it reads past the "
            "row policies that ARE the isolation mechanism on a single-schema edge box"
        ),
        content=(
            b"from django.db import connection\n\n\n"
            b"def gateproof_unscoped_read():\n"
            b"    with connection.cursor() as cursor:\n"
            b'        cursor.execute("SELECT id FROM people_student")\n'
            b"        return cursor.fetchall()\n"
        ),
    ),
    # -- wiring / pipeline contracts -------------------------------------------
    "ota-pipeline-wiring": Mutation(
        kind="patch",
        path="apps/api/urls.py",
        defect="a cut wire in the cascading-OTA pipeline: every piece still imports and tests green, and it upgrades nobody",
        anchor=b"ota",
        replacement=b"gateproof_ota_disconnected",
    ),
    "nav-engine-coverage-static": Mutation(
        kind="delete",
        path="templates/portal_base.html",
        defect="the tenant shell the nav projector is wired into is gone",
    ),
    "control-plane-registry-drift": Mutation(
        kind="create",
        path=f"templates/{_PROOF}_control_plane.html",
        defect="a page extending control_plane_base that joins neither PHASE7 nor the exempt set - registry drift",
        content=b'{% extends "control_plane_base.html" %}\n{% block cp_content %}<p>x</p>{% endblock %}\n',
    ),
    "shell-url-namespace-contract": Mutation(
        kind="patch",
        path="templates/portal_base.html",
        defect="shell chrome hard-reversing a namespace its host does not mount - a 500 AFTER the page rendered",
        anchor=b"{% block",
        replacement=b"<a href=\"{% url 'super:dashboard' %}\">x</a>\n{% block",
    ),
    "operator-landing-header-order": Mutation(
        kind="create",
        path=f"templates/{_PROOF}_operator_landing.html",
        defect="cockpit chrome stacked above the page title, so operators scroll past empty rules to reach the heading",
        content=(
            b'{% extends "control_plane_base.html" %}\n'
            b"{% block cp_content %}\n"
            b'  {% include "partials/cp_pulse_strip.html" %}\n'
            b"  <h1>Platform Command Center</h1>\n"
            b"{% endblock %}\n"
        ),
    ),
    "actionless-attention-surfaces": Mutation(
        kind="create",
        path=f"templates/{_PROOF}_attention.html",
        defect='"6 access requests awaiting approval" with no link - an attention row that leads nowhere',
        content=(
            b'<div class="rmc-attention-item">\n'
            b"  <span>6 access requests awaiting approval</span>\n"
            b"</div>\n"
        ),
    ),
})

MUTATIONS.update({
    # -- Migration Cloud lander contracts --------------------------------------
    "lander-row-error-contract": Mutation(
        kind="create",
        path=f"apps/migration_cloud/landers/{_PROOF}_lander.py",
        defect="a lander that discards the row it rejected - you cannot replay a row you did not keep",
        content=(
            b"from apps.migration_cloud.landers.base import BaseLander\n\n\n"
            b"class GateProofLander(BaseLander):\n"
            b"    def land(self, canonical_rows):\n"
            b"        for row in canonical_rows:\n"
            b"            try:\n"
            b"                self.write(row)\n"
            b"            except ValueError:\n"
            b"                continue\n"
        ),
    ),
    "lander-row-streaming": Mutation(
        kind="create",
        path=f"apps/migration_cloud/landers/{_PROOF}_buffered.py",
        defect="list(canonical_rows) - a non-streaming lander freezes rows_processed and trips SystemicStallError on a box",
        content=(
            b"from apps.migration_cloud.landers.base import BaseLander\n\n\n"
            b"class GateProofBufferedLander(BaseLander):\n"
            b"    def land(self, canonical_rows):\n"
            b"        rows = list(canonical_rows)\n"
            b"        for row in rows:\n"
            b"            self.write(row)\n"
        ),
    ),
    # -- security / tenancy ratchets -------------------------------------------
    "ratchet-baselines-present": Mutation(
        kind="delete",
        path="var/security-audit-baseline-rls-force-coverage.json",
        defect="a --compare ratchet with its baseline deleted: most scanners then author one from whatever they find and exit 0 forever",
    ),
    "audit-log-append-only": Mutation(
        kind="create",
        path=f"apps/compliance/{_PROOF}_mutate_audit.py",
        defect="filter(...).update() on the AuditLog - the exact form the first version of this guard could not see",
        content=(
            b"from apps.compliance.models import AuditLog\n\n\n"
            b"def scrub(actor_id):\n"
            b"    AuditLog.objects.filter(actor_id=actor_id).update(actor_id=None)\n"
        ),
    ),
    "rls-force-coverage": Mutation(
        kind="create",
        path="apps/schools/migrations/9998_%s_enable_rls.py" % _PROOF,
        defect="a table switched to RLS with no FORCE - Postgres exempts the OWNER, and Django connects AS the owner",
        content=b'from django.db import connection, migrations\n\n\nTABLES = ["schools_gateproofprobetable"]\n\n\ndef enable(apps, schema_editor):\n    with connection.cursor() as cursor:\n        for table in TABLES:\n            cursor.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY;")\n\n\nclass Migration(migrations.Migration):\n    dependencies = []\n    operations = [migrations.RunPython(enable, migrations.RunPython.noop)]\n',
    ),
    "migration-school-addfield-guard": Mutation(
        kind="create",
        # number 9997 > the people healer (0067), model studentguardian created
        # long before it, so a bare AddField(school) here is the exact front-run
        # shape. In apps/people because that is a healer app; a school AddField
        # in a non-healer app cannot collide and is not a finding.
        path="apps/people/migrations/9997_%s_bare_school_addfield.py" % _PROOF,
        defect="a bare school AddField AFTER the app's live-model healer - DuplicateColumn on a fresh migrate, so a new tenant/box cannot provision",
        content=(
            b"from django.db import migrations, models\n"
            b"import django.db.models.deletion\n\n\n"
            b"class Migration(migrations.Migration):\n"
            b'    dependencies = [("people", "0077_rls_force_and_null_arm_postgresql")]\n'
            b"    operations = [\n"
            b"        migrations.AddField(\n"
            b'            model_name="studentguardian",\n'
            b'            name="school",\n'
            b"            field=models.ForeignKey(\n"
            b"                blank=True, null=True,\n"
            b"                on_delete=django.db.models.deletion.CASCADE,\n"
            b'                related_name="+", to="schools.school",\n'
            b"            ),\n"
            b"        ),\n"
            b"    ]\n"
        ),
    ),
    "rls-policy-coverage": Mutation(
        kind="patch",
        path="apps/academics/migrations/0038_rls_policy_default_deny.py",
        defect="a migration NAMED for a default-deny policy that attaches none - the filename check cannot tell",
        anchor=b"CREATE POLICY",
        replacement=b"SELECT 1; -- gateproof: no policy here",
        all_occurrences=True,
    ),
    "rls-null-school-arm": Mutation(
        kind="patch",
        path="apps/feedback/migrations/0010_rls_fk_scoped_children.py",
        defect="an RLS policy on a NULLABLE school FK missing its school_id IS NULL arm",
        anchor=b"IS NULL",
        replacement=b"IS NOT NULL",
    ),
    "rls-table-coverage": Mutation(
        kind="patch",
        path="apps/schools/models.py",
        defect="a new tenant-scoped table enumerated in no enable_rls migration - the shape that went red the moment PR #184 merged",
        anchor=b"from django.db import models\n",
        replacement=(
            b"from django.db import models\n\n\n"
            b"class GateProofUnprotectedRow(models.Model):\n"
            b'    school = models.ForeignKey("schools.School", on_delete=models.CASCADE)\n'
            b"    note = models.CharField(max_length=64)\n"
        ),
    ),
    "rls-relation-coverage": Mutation(
        kind="patch",
        path="apps/schools/models.py",
        defect="a tenant table reaching its school through a RELATION with no policy of its own",
        anchor=b"from django.db import models\n",
        replacement=(
            b"from django.db import models\n\n\n"
            b"class GateProofRelationScoped(models.Model):\n"
            b'    parent = models.ForeignKey("schools.SchoolProfile", on_delete=models.CASCADE)\n'
            b"    note = models.CharField(max_length=64)\n"
        ),
    ),
    "blank-unique-text-fields": Mutation(
        kind="patch",
        path="apps/schools/models.py",
        defect='blank=True AND unique=True is optional exactly ONCE, because "" collides under a unique index',
        anchor=b"from django.db import models\n",
        replacement=(
            b"from django.db import models\n\n\n"
            b"class GateProofBlankUnique(models.Model):\n"
            b"    code = models.CharField(max_length=32, blank=True, unique=True)\n"
        ),
    ),
    "single-migration-leaf": Mutation(
        kind="create",
        path=f"apps/schools/migrations/9999_{_PROOF}_second_leaf.py",
        defect="a second migration leaf in one app - what two agents working this repo concurrently produce",
        content=(
            b"from django.db import migrations\n\n\n"
            b"class Migration(migrations.Migration):\n"
            b'    dependencies = [("schools", "0001_initial")]\n'
            b"    operations = []\n"
        ),
    ),
    "upload-validation-coverage": Mutation(
        kind="create",
        path=f"apps/schools/{_PROOF}_upload.py",
        defect="a direct request.FILES intake that skips the shared upload validator",
        content=(
            b"def receive(request):\n"
            b'    upload = request.FILES["document"]\n'
            b"    return upload.read()\n"
        ),
    ),
    "sms-template-length": Mutation(
        kind="patch",
        path="apps/communication/template_catalog.py",
        defect="an SMS body over 160 chars after substitution - carrier multipart charge plus delivery truncation",
        anchor=b"contact the school office.",
        replacement=(
            b"contact the school office as soon as you are able so that the attendance "
            b"register can be corrected before the end of the current reporting period."
        ),
    ),
    "middleware-topology-parity": Mutation(
        kind="patch",
        path="config/settings.py",
        defect="a middleware in the base MIDDLEWARE only - config builds it twice and prod runs the second list",
        anchor=b"MIDDLEWARE = [\n",
        replacement=b'MIDDLEWARE = [\n    "apps.schools.gateproof_middleware.GateProofMiddleware",\n',
    ),
    "gilead-tree-classification": Mutation(
        kind="create",
        path=f"apps/schools/{_PROOF}_pilot.py",
        defect="a pilot-school reference outside its classified bucket",
        content=b'PILOT_SCHOOL_NAME = "Gilead Tech High"\n',
    ),
    "eager-filter-arg-completion-static": Mutation(
        kind="create",
        path=f"templates/{_PROOF}_eager_arg.html",
        defect="an eager filter arg that is a bare context var - VariableDoesNotExist 500 even on the branch not taken",
        content=b"<p>{{ label|default:missing_context_var }}</p>\n",
    ),
    "service-worker-version": Mutation(
        kind="delete",
        path="static/js/service-worker.js",
        defect="subject-removal: the service worker whose CACHE_VERSION shape and monotonicity this gate pins is gone",
    ),
})

MUTATIONS["i18n-catalog-fresh-fast"] = Mutation(
    kind="create",
    path=f"templates/{_PROOF}_i18n_drift.html",
    defect=(
        "a translatable string wrapped in a template but never extracted into "
        "locale/en/LC_MESSAGES/django.po - every locale renders it in English "
        "and no translator is ever asked for it"
    ),
    content=(
        b"{% load i18n %}"
        b"<span>{% trans 'gateproof planted i18n drift 2026-08-31' %}</span>"
    ),
)

MUTATIONS["gates-can-fail-coverage"] = Mutation(
    kind="patch",
    path="scripts/pre_push_boundary_check.py",
    defect="a new gate added to the pre-push runner with no mutation and no exemption - the proof silently skipped",
    anchor=b'GATES: list[tuple[str, list[str]]] = [',
    replacement=(
        b'GATES: list[tuple[str, list[str]]] = ['
        + chr(10).encode()
        + b'    ("gateproof-unproven-newcomer", ["verify_python_files_parse.py"]),'
    ),
)

MUTATIONS["marketing-axe-ratchet-coverage"] = Mutation(
    kind="patch",
    path="scripts/run_marketing_axe_sweep.mjs",
    defect=(
        "a page quietly dropped from the axe sweep's PAGES list - the sweep "
        "then reports the marketing surface CLEAN for the same reason a broken "
        "detector does, and in CI the two are indistinguishable. This is not "
        "hypothetical: the sweep was built against one spec's 15-path list and "
        "reported zero while /platform/analytics/ and /platform/security/ were "
        "failing color-contrast at 1.08:1 on both viewports"
    ),
    anchor=b'"/platform/security/",',
    replacement=b"// gateproof: page removed from the sweep",
)

MUTATIONS["ci-shell-command-integrity"] = Mutation(
    kind="create",
    path=f"scripts/{_PROOF}_truncated.sh",
    defect=(
        "a backslash continuation followed by a blank line - the shell joins the "
        "backslash with the EMPTY line, so the command ends there and every "
        "remaining argument is parsed as its own command"
    ),
    # Trips both arms at once: the truncation, and the bare `manage.py test`
    # the truncation leaves behind.
    #
    # ONE backslash byte, written as `\\` in a bytes literal. Two would be an
    # ESCAPED backslash to the shell -- a literal character, not a line
    # continuation -- so the planted file would carry no defect and the harness
    # would report this gate DEAD when it is working perfectly.
    content=(
        b"#!/bin/sh" + chr(10).encode()
        + b"python manage.py test \\" + chr(10).encode()
        + chr(10).encode()
        + b"    apps.schools.tests.test_gateproof" + chr(10).encode()
    ),
)

MUTATIONS["test-host-fidelity"] = Mutation(
    kind="create",
    path=f"apps/schools/tests/{_PROOF}_host_fidelity.py",
    defect=(
        "a test that names config.tenant_urls and then issues a request with no "
        "Host header - so it is served by config.urls, the DEVELOPER urlconf, which "
        "mounts a superset of every tenant route; the test passes, request.school is "
        "None, and a route deleted from the tenant urlconf stays green here while "
        "every real school 404s"
    ),
    # The plant must use the shape the scanner cannot forgive: a host urlconf on the
    # decorator, a real client request inside the decorated scope, and NO host
    # anywhere in it. Deliberately not `reverse(urlconf=...)` and not a request
    # carrying HTTP_HOST -- both are correct as written and are exactly what the
    # scanner was taught to leave alone, so a plant using one would leave this gate
    # looking dead when it is working.
    content=(
        b"from django.test import TestCase, override_settings" + chr(10).encode()
        + chr(10).encode()
        + chr(10).encode()
        + b"@override_settings(ROOT_URLCONF=\"config.tenant_urls\")" + chr(10).encode()
        + b"class PlantedHostFidelityTests(TestCase):" + chr(10).encode()
        + b"    def test_reaches_the_tenant_surface(self):" + chr(10).encode()
        + b"        self.client.get(\"/finance/reports/\")" + chr(10).encode()
    ),
)

# Re-introduces the defect verbatim: `tbody.template` is EVERY inline form
# without an `original`, not just the __prefix__ prototype, so hiding it takes
# the row the admin just offered. A patch, not a create -- the gate renders
# from the live admin registry, so a planted file is never reached.
#
# It must be the LONG selector. The same file forces `table > :is(tbody, tfoot)
# { display: table-row-group !important }` at (0,5,3) two hundred lines above,
# so restoring `tbody.template` on the short `[data-rmc-shell-root=...]`
# selector at (0,2,2) is overridden and plants nothing -- measured, the gate
# stayed green on it. The selector that shipped, and that CDP measured winning,
# is this one at (0,6,3).
MUTATIONS["admin-rendered-form-layout"] = Mutation(
    kind="patch",
    path="static/css/rmc-admin-django-canvas-contract.css",
    defect="a rule that hides every NEW inline row, not just the prototype:"
           " the add form offers a column header with no row under it",
    anchor=b".inline-group :is(.tabular, .inline-related.tabular)"
           b" table > tbody:has(> tr.empty-form),",
    replacement=b".inline-group :is(.tabular, .inline-related.tabular)"
                b" table > tbody.template,",
)

MUTATIONS["workflow-swallowed-exit-codes"] = Mutation(
    kind="create",
    path=f".github/workflows/{_PROOF}-swallowed-exit-code.yml",
    defect=(
        "a CI step whose LAST command ends in `|| echo` - the shell exits 0 "
        "whatever the tool found, so the step, and every gate inside it, draws "
        "a green check on a failure it has already seen. The shape that let "
        "the help-center browser lane report success on every failure while a "
        "comment directly above it declared the lane enforcing"
    ),
    # A whole workflow file rather than a patch: the gate enumerates with
    # `git ls-files -- .github/workflows`, which the harness satisfies with
    # `git add -N`, and a new file cannot go stale the way a byte anchor in
    # someone else's workflow does.
    #
    # The swallow must be the LAST line. The gate deliberately does not flag a
    # `|| true` that is followed by real work -- a cleanup before an `exit 1`,
    # a readiness sentinel whose loop enforces -- so a plant that buried the
    # swallow mid-block would report this gate DEAD while it is working
    # exactly as designed.
    content=(
        b"name: gateproof swallowed exit code" + chr(10).encode()
        + b"on:" + chr(10).encode()
        + b"  workflow_dispatch: {}" + chr(10).encode()
        + b"jobs:" + chr(10).encode()
        + b"  proof:" + chr(10).encode()
        + b"    runs-on: ubuntu-latest" + chr(10).encode()
        + b"    steps:" + chr(10).encode()
        + b"      - name: A gate that cannot report its own failure"
        + chr(10).encode()
        + b"        run: |" + chr(10).encode()
        + b"          python scripts/some_gate.py "
        + b'|| echo "skipped - run it locally"' + chr(10).encode()
    ),
)

MUTATIONS["dangling-static-reference"] = Mutation(
    kind="create",
    path=f"static/css/{_PROOF}_dangling.css",
    defect=(
        "a stylesheet that asks for an asset nobody shipped - the storage subclass "
        "forgives the unresolvable reference by design, so the deploy stays green "
        "and the icon is simply absent for every user; this is the shape that put a "
        "bootstrap-icons .woff fallback into production with only .woff2 vendored"
    ),
    # A .css file, a real url(), and a target that is neither a data: URI nor a
    # .map -- the three shapes the scanner was taught NOT to forgive. A plant using
    # a forgiven one (a url() call inside JavaScript, a nested url(%23n) in an
    # inline SVG, a missing source map) would leave this gate looking dead when it
    # is working exactly as designed. url() without quotes is valid CSS.
    content=(
        b"@font-face{font-family:GateProof;" + chr(10).encode()
        + b"src:url(fonts/gateproof-never-shipped.woff2) format(woff2)}" + chr(10).encode()
    ),
)

MUTATIONS["super-route-authorization"] = Mutation(
    kind="patch",
    path="apps/schools/super_urls.py",
    defect=(
        "a /super/ route mounted with no authorization gate -- the operator "
        "control plane is the one surface where that is unrecoverable, and "
        "nothing else in the repository can see it: audit_role_permission_matrix "
        "discovers urlconfs with a PREFIX glob that never matches super_urls.py, "
        "so all 255 entries are absent from the matrix rather than filtered out"
    ),
    # Deliberately a `patch` where this file prefers `create`: the scanner reads
    # ONE named urlconf, so a new file carrying the violation would never be
    # opened and the gate would report DEAD while working perfectly. The
    # urlpatterns opener is the most stable anchor the file has.
    #
    # RedirectView.as_view(...) is scored UNRESOLVED, which this scanner counts
    # as unclassified rather than safe -- exactly so a resolver gap makes it
    # louder, not quieter. A plant pointing at any real view would be scored
    # AUTHZ_PROVEN (all 224 common-wrapper routes also carry a def-site
    # decorator) and would prove nothing.
    anchor=b"urlpatterns = [\n",
    replacement=(
        b"urlpatterns = [\n"
        b"    path(\n"
        b'        "gate-proof-unguarded/",\n'
        b'        RedirectView.as_view(pattern_name="super:super_dashboard"),\n'
        b'        name="gate_proof_unguarded",\n'
        b"    ),\n"
    ),
)


MUTATIONS["tenant-queryset-safety"] = Mutation(
    kind="create",
    path=f"apps/schools/{_PROOF}_unscoped_queryset.py",
    defect=(
        "a read of a tenant-owned model with no school bound to it - on the "
        "shared-schema edge that returns every school's invoices, and the page "
        "renders them without an error anywhere"
    ),
    # Invoice carries a school FK, so it is in the scanner's tenant-model set,
    # and `status=` is a plain non-scoping kwarg. Deliberately NOT pk= or
    # `__school`: those are the shapes the scanner was taught to forgive, so a
    # plant using one would leave this gate looking dead when it is working.
    content=(
        b"from apps.finance.models import Invoice" + chr(10).encode()
        + chr(10).encode()
        + chr(10).encode()
        + b"def every_tenants_open_invoices():" + chr(10).encode()
        + b"    return list(Invoice.objects.filter(status=\"OPEN\"))" + chr(10).encode()
    ),
)

MUTATIONS["edge-rail-coverage"] = Mutation(
    kind="create",
    path="apps/student360/migrations/0002_gateproof_undeclared_tenant_model.py",
    defect=(
        "a new tenant model added with no edge-rail posture - nobody ever decided whether "
        "it crosses the cloud/box boundary, and on a sovereign box it simply would not"
    ),
    # A MIGRATION, not a models.py class, and that is the whole point of the gate.
    # rail_coverage.tenant_models() reads MIGRATION STATE rather than the runtime app
    # registry, precisely because the registry is not import-order-proof: three migrated
    # portal forum models were invisible to a registry walk because their module is
    # imported lazily, and the gate reported a truthful-looking "0 undeclared" against an
    # incomplete denominator. Planting a bare class in models.py would therefore prove
    # nothing here -- it would not be seen, and a DEAD verdict would be the harness's own
    # fault, which is the failure mode this file's own notes warn about at length.
    content=(
        b'"""Planted by verify_gates_can_fail. Never commit this file."""'
        + chr(10).encode()
        + b"from django.db import migrations, models"
        + chr(10).encode() * 2
        + chr(10).encode()
        + b"class Migration(migrations.Migration):"
        + chr(10).encode()
        + b'    dependencies = [("student360", "0001_immutable_transcript")]'
        + chr(10).encode()
        + b"    operations = ["
        + chr(10).encode()
        + b"        migrations.CreateModel("
        + chr(10).encode()
        + b'            name="GateProofUndeclaredTenantModel",'
        + chr(10).encode()
        + b"            fields=["
        + chr(10).encode()
        + b'                ("id", models.BigAutoField(primary_key=True, serialize=False)),'
        + chr(10).encode()
        + b'                ("note", models.CharField(max_length=64)),'
        + chr(10).encode()
        + b"            ],"
        + chr(10).encode()
        + b"        ),"
        + chr(10).encode()
        + b"    ]"
        + chr(10).encode()
    ),
)

MUTATIONS["lander-write-targets"] = Mutation(
    kind="patch",
    path="apps/migration_cloud/landers/write_targets.py",
    defect=(
        "the declared write-target table drifts away from what the landers actually "
        "write - the edge pre-import guard then tells an operator an import is clean "
        "while it lands rows on a model no rail carries"
    ),
    # Deleting a DECLARED model is the drift that matters and the one a reviewer
    # would not notice: the resolver still finds schoolops.Route in transport_lander,
    # the table no longer claims it, and the guard stops counting the bus roster as
    # box-resident. The anchor is one line of a generated table, so it cannot go
    # stale against someone else's edit the way a prose anchor would.
    anchor=b'        "schoolops.Route",',
    replacement=b'        # gate-proof: this line was removed to plant the drift',
)

MUTATIONS["companion-server-contract"] = Mutation(
    kind="create",
    # A sibling source file, not a test: the gate deliberately skips tests/, so a
    # plant there would prove the opposite of what it looks like it proves.
    path=f"companion-tauri/src/{_PROOF}_dead_path.ts",
    defect=(
        "a companion client calling a server path that resolves on no urlconf -- "
        "the fetch 404s, the client swallows it, and the feature is simply dead"
    ),
    content=b'const GATEPROOF = "/api/v1/gateproof/never-mounted/";\n',
)

MUTATIONS["global-country-ingestion-coverage"] = Mutation(
    kind="patch",
    path="apps/migration_cloud/ingestion_lexicon.py",
    defect="offline ingestion manifest missing lexicon_mappings for a country compile",
    anchor=b'    "lexicon_mappings",',
    replacement=b'    "lexicon_mappings_removed_gateproof",',
)

MUTATIONS["ingestion-lexicon-offline-wiring"] = Mutation(
    kind="patch",
    path="static/js/rmc-offline-ingestion-lexicon.js",
    defect="client lexicon module missing IndexedDB read path for cold-offline preflight",
    anchor=b"ensureManifestReady",
    replacement=b"ensureManifestReadyGateproofRemoved",
)

MUTATIONS["global-local-first-ingestion-chain"] = Mutation(
    kind="patch",
    path="apps/sync_engine/tenant_manifest_resolver.py",
    defect="tenant offline manifest missing operational_context.ingestion_lexicon",
    anchor=b'operational_context["ingestion_lexicon"]',
    replacement=b'operational_context["ingestion_lexicon_gateproof_removed"]',
)

MUTATIONS["global-platform-country-readiness"] = Mutation(
    kind="patch",
    path="scripts/verify_global_platform_country_readiness.py",
    defect="country readiness gate no longer checks service-worker precache for lexicon JS",
    anchor=b'"rmc-offline-ingestion-lexicon.js"',
    replacement=b'"rmc-offline-ingestion-lexicon-gateproof.js"',
)

MUTATIONS["global-platform-country-readiness-django"] = Mutation(
    kind="patch",
    path="scripts/verify_global_local_first_ingestion_chain.py",
    defect="ingestion chain gate no longer requires tenant manifest ingestion_lexicon",
    anchor=b'"ingestion_lexicon"',
    replacement=b'"ingestion_lexicon_gateproof_removed"',
)

MUTATIONS["platform-back-to-top"] = Mutation(
    kind="patch",
    path="templates/admin/base.html",
    defect=(
        "the Django admin shell stops mounting the platform chrome bundle, so "
        "five of its seven scripts never execute on any admin page and the "
        "back-to-top control renders inside the fixed-height scroll canvas"
    ),
    # The include PATH, not any script name inside the partial: the partial's
    # contents change as chrome is added, and a mutation anchored on one of its
    # scripts would go stale the next time that script is renamed. This path is
    # what the gate itself asserts, so the two can only move together.
    anchor=b"partials/rmc_platform_chrome_scripts.html",
    replacement=b"partials/rmc_platform_chrome_scripts_gateproof.html",
)

MUTATIONS["cp-v8-operator-closeout"] = Mutation(
    kind="patch",
    path="var/large-collection-unbounded-baseline.json",
    defect=(
        "the large-collection burndown loses its entry list, so the 37 tables "
        "that render an unbounded collection stop being known debt and a "
        "thirty-eighth could land with nothing noticing"
    ),
    # The ratchet's own contract key, not any one filename in the list: the list
    # is meant to shrink, so anchoring on a member would break the proof the
    # first time somebody fixes that table -- and a mutation that no longer
    # applies is a standing proof that has quietly stopped proving anything.
    anchor=b'"known_unbounded"',
    replacement=b'"known_unbounded_gateproof"',
)

MUTATIONS["theme-dual-plane-shell"] = Mutation(
    kind="patch",
    path="static/css/rmc-theme-experience-dual-plane.css",
    defect=(
        "the dual-plane stylesheet stops declaring which wave it belongs to, so "
        "nothing can tell whether the shipped service-worker cache generation "
        "still covers it and returning browsers keep the pre-wave sheet"
    ),
    # The banner FILENAME, not its version: a version anchor goes stale the next
    # time the sheet is revised, and a mutation that no longer applies is a
    # standing proof that quietly stops proving anything. The filename can only
    # change in a rename, which also moves the gate's own MARKER constant.
    anchor=b"rmc-theme-experience-dual-plane.css",
    replacement=b"rmc-theme-experience-dual-plane-gateproof.css",
)

MUTATIONS["admin-autofill-coverage"] = Mutation(
    kind="patch",
    path="apps/siteconfig/admin_smart_initials.py",
    defect="the smart-initials builder registry emptied - every admin add form silently stops prefilling",
    anchor=b"INITIAL_BUILDERS = {",
    replacement=b"INITIAL_BUILDERS: dict = {}" + chr(10).encode() + b"_GATEPROOF_RETIRED_BUILDERS = {",
)

MUTATIONS["no-placeholder-copy"] = Mutation(
    kind="create",
    path="templates/_gate_proof_undeclared_placeholder.html",
    defect=(
        "a template ships stub copy that no human ever declared -- exactly the state "
        "docs/generated/no_placeholder_audit.json certified as clean while covering a "
        "corpus 824 templates smaller than the tree it was describing"
    ),
    # create, not patch: the gate is a tree scan, and a new file carrying the
    # violation cannot go stale the way a byte anchor in someone else's file
    # does. The harness marks it intent-to-add, so a corpus built from
    # `git ls-files` would see it too.
    content=(
        b"{% comment %}Planted by verify_gates_can_fail; not a real page.{% endcomment %}"
        + chr(10).encode()
        + b"<p>Lorem ipsum dolor sit amet, consectetur adipiscing elit.</p>"
        + chr(10).encode()
    ),
)


MUTATIONS["operator-siteconfig-cp-shell"] = Mutation(
    kind="create",
    path=f"apps/siteconfig/views{_PROOF}_stem_kwarg.py",
    defect=(
        "a view calls render_siteconfig_stem() with a keyword the function does "
        "not accept -- no **kwargs absorbs it, so it is a TypeError 500 on every "
        "request. apps/schools/views_tenant_self_offboarding.py did exactly this "
        "with page_title= from 2026-05-22 until 2026-09-02, on a view no test "
        "covers, while the gate spent that time reporting 17 findings about "
        "pages that render correctly"
    ),
    # create, not patch: the gate walks apps/ for call sites, so a new file
    # carrying the defect cannot go stale the way a byte anchor would. The
    # harness marks it intent-to-add, which the walk does not need but the
    # git-ls-files scanners around it do.
    content=(
        b'"""Planted by verify_gates_can_fail; not a real view."""'
        + chr(10).encode()
        + b"from apps.siteconfig.control_plane_render import render_siteconfig_stem"
        + (chr(10) * 3).encode()
        + b"def gateproof_view(request):"
        + chr(10).encode()
        + b'    return render_siteconfig_stem(request, "user_preferences", {}, page_title="x")'
        + chr(10).encode()
    ),
)


# DEAD verdicts that have been INDEPENDENTLY CONFIRMED, with the evidence that
# confirmed them.
#
# A DEAD verdict is a hypothesis, not a finding. By far the most common cause of
# one is a bad mutation -- a defect planted somewhere the gate does not look, or
# in a form it deliberately tolerates. Three of the first nineteen DEAD verdicts
# this harness produced were its own fault: it planted UNTRACKED files, and
# several scanners enumerate with `git ls-files`, so the defect was invisible
# and the gate returned a truthful, useless zero.
#
# So a gate is only reported as broken once someone has reproduced the blindness
# a second way, by hand, and written down how. Everything else is reported as
# UNADJUDICATED: real work to do, not a conclusion.
CONFIRMED_DEAD: dict[str, str] = {
    # Empty, and that is the goal state -- the three that were here on
    # 2026-08-28 (rls-force-coverage, rls-policy-coverage,
    # broad-except-baseline) were fixed rather than documented, and now
    # prove they can fail. The evidence that convicted them is kept in
    # docs/audits/GATE_DETECTOR_INTEGRITY_AUDIT_2026_08_28.md.
}


# Gates with no mutation, and the reason. An entry here is a REVIEWED exemption,
# not a skip: the completeness check still fails if a gate appears in neither
# table, so a new gate cannot quietly arrive unproven.
UNPROVEN: dict[str, str] = {
    "report-entity-coverage": "subject is the entity catalog crossed with live report registrations; a synthetic entity models the bookkeeping, not the coverage claim",
    "migration-apply-stall-contract": "the contract spans a pulse producer, LoopWatchdog and a tier-scaled timeout; no single-file defect stands in for it",
    "rail-fk-portability": "needs a rail model whose FK targets a SHARED table, which requires the sync-rail registry to be loaded",
    "render-online-ai-posture": "asserts deployment posture across settings and AI Center copy; a planted defect would only restate the assertion",
    "tenant-scoping-burndown": "a date-based forward-progress gate: the only defect is the calendar moving, which no file mutation simulates",
    "finance-payment-atomicity": "a hand-maintained list of four named mutators; its own docstring says it is not coverage of apps/finance",
    "unscoped-shared-tenant-admin": "needs a SHARED model registered on the tenant admin, which requires the admin registry to be loaded",
    "url-kwarg-contract": "needs a view AND an include(..., kwargs) pointing at it; the defect only exists once both sides are wired",
    "test-asserts-behaviour": "this harness plants UNCOMMITTED files; the gate measures a git worktree created at HEAD, so a planted test is not in it. Proved by hand instead on 2026-09-01 with a committed vacuous test: the gate reported NEW vacuous test in a changed file and exited 1 -- see the commit that wired it",
}


# ---------------------------------------------------------------------------
# Completeness: the half that stops a new gate arriving unproven
# ---------------------------------------------------------------------------


def registered_gates() -> list[tuple[str, list[str], bool]]:
    """(label, argv, needs_django) for every gate the pre-push runner enforces."""
    gates = [(label, argv, False) for label, argv in ppbc.GATES]
    gates += [(label, argv, True) for label, argv in ppbc.DJANGO_GATES]
    return gates


def completeness_problems() -> list[str]:
    labels = {label for label, _, _ in registered_gates()}
    problems: list[str] = []
    for label in sorted(labels - set(MUTATIONS) - set(UNPROVEN)):
        problems.append(
            f"{label}: registered as a pre-push gate with no mutation and no reasoned "
            f"exemption. Add one to MUTATIONS, or to UNPROVEN with the reason."
        )
    for label in sorted((set(MUTATIONS) | set(UNPROVEN)) - labels):
        problems.append(
            f"{label}: has a mutation/exemption but is not a registered gate any more. "
            f"Retired? Delete the entry so this file keeps describing reality."
        )
    for label in sorted(set(MUTATIONS) & set(UNPROVEN)):
        problems.append(f"{label}: both proven and exempt; delete one.")
    return problems


# ---------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--gate", action="append", help="prove only this gate (repeatable)")
    parser.add_argument("--list", action="store_true", help="print coverage and exit")
    parser.add_argument("--worktree", help="reuse this worktree path instead of a temp one")
    parser.add_argument("--keep-worktree", action="store_true", help="leave the worktree for debugging")
    parser.add_argument("--timeout", type=int, default=DEFAULT_GATE_TIMEOUT_S)
    parser.add_argument(
        "--skip-baseline",
        action="store_true",
        help="do not re-run each gate unmutated. Faster, but a gate that was ALREADY red "
        "then reads as PROVEN.",
    )
    args = parser.parse_args(argv)

    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass

    gates = registered_gates()
    problems = completeness_problems()

    if args.list:
        print(f"registered gates: {len(gates)}")
        print(f"  with a mutation: {len(set(MUTATIONS) & {g[0] for g in gates})}")
        print(f"  reasoned exempt: {len(set(UNPROVEN) & {g[0] for g in gates})}")
        for label in sorted(UNPROVEN):
            print(f"    EXEMPT  {label}: {UNPROVEN[label]}")
        for problem in problems:
            print(f"    PROBLEM {problem}")
        return 1 if problems else 0

    selected = set(args.gate or [])
    todo = [g for g in gates if g[0] in MUTATIONS and (not selected or g[0] in selected)]
    if selected:
        unknown = selected - {g[0] for g in gates}
        if unknown:
            print(f"unknown gate(s): {', '.join(sorted(unknown))}")
            return 2

    django_python = ppbc._django_python() if any(g[2] for g in todo) else None
    plain_python = sys.executable

    worktree = Path(args.worktree) if args.worktree else (
        ROOT.parent / f".gateproof-worktree-{os.getpid()}"
    )

    results: list[tuple[str, str, str]] = []
    started = time.time()

    with Workspace(worktree, keep=args.keep_worktree or bool(args.worktree)) as workspace:
        print(f"mutation workspace: {workspace.path}")
        print(f"proving {len(todo)} gate(s) can fail\n")
        for label, gate_argv, needs_django in todo:
            mutation = MUTATIONS[label]
            python = django_python if needs_django else plain_python
            if needs_django and not python:
                results.append((label, "SKIP", "Django is not importable in this environment"))
                print(f"  SKIP     {label}")
                continue

            applied, explanation, token = workspace.apply(mutation)
            if not applied:
                results.append((label, "DRIFTED", explanation))
                print(f"  DRIFTED  {label}  ({explanation})")
                continue
            try:
                code, output = _run_gate(workspace, gate_argv, python, args.timeout)
            finally:
                workspace.restore(mutation, token)
                workspace.reset()

            if code == -9:
                results.append((label, "TIMEOUT", f"no verdict in {args.timeout}s"))
                print(f"  TIMEOUT  {label}")
                continue
            if code == 0:
                # Keep what the gate SAID. A DEAD verdict is a serious claim and
                # the most common cause is a bad mutation, not a dead gate --
                # the output usually shows straight away whether the scanner
                # even looked at the file the defect was planted in.
                results.append((label, "DEAD", mutation.defect + chr(10) + "    gate said: " + _tail(output, 4)))
                mark = "confirmed" if label in CONFIRMED_DEAD else "UNADJUDICATED"
                print(f"  DEAD     {label}  <-- passed with its own defect planted [{mark}]")
                continue

            if args.skip_baseline:
                results.append((label, "PROVEN", mutation.defect))
                print(f"  PROVEN   {label}")
                continue
            workspace.reset()
            base_code, base_output = _run_gate(workspace, gate_argv, python, args.timeout)
            if base_code == 0:
                results.append((label, "PROVEN", mutation.defect))
                print(f"  PROVEN   {label}")
            elif base_code == -9:
                results.append((label, "TIMEOUT", f"unmutated run had no verdict in {args.timeout}s"))
                print(f"  TIMEOUT  {label}  (unmutated)")
            else:
                results.append((label, "BASELINE-RED", _tail(base_output)))
                print(f"  BASE-RED {label}  <-- already failing on HEAD, proves nothing")

    elapsed = int(time.time() - started)
    counts: dict[str, int] = {}
    for _, status, _ in results:
        counts[status] = counts.get(status, 0) + 1

    print(f"\n{'-' * 70}")
    print(
        "verify_gates_can_fail: "
        + ", ".join(f"{status} {count}" for status, count in sorted(counts.items()))
        + f"  ({elapsed}s)"
    )

    findings = [r for r in results if r[1] in {"DEAD", "DRIFTED", "BASELINE-RED"}]
    if findings:
        print("\nFINDINGS")
        for label, status, detail in findings:
            print(f"\n  [{status}] {label}")
            if status == "DEAD":
                print(f"    planted: {detail}")
                if label in CONFIRMED_DEAD:
                    print("    CONFIRMED broken. Evidence:")
                    print(f"    {CONFIRMED_DEAD[label]}")
                else:
                    print("    UNADJUDICATED. The gate exited 0, but a DEAD verdict is")
                    print("    a hypothesis until the mutation is confirmed to be a valid")
                    print("    instance of this gate's class -- a defect planted where the")
                    print("    gate does not look produces exactly this result. Reproduce")
                    print("    it by hand before calling the gate broken.")
            else:
                print(f"    {detail}")
    if problems:
        print("\nCOVERAGE PROBLEMS")
        for problem in problems:
            print(f"  - {problem}")

    exempt = sorted(set(UNPROVEN) & {g[0] for g in gates})
    if exempt and not selected:
        print(f"\n{len(exempt)} gate(s) carry a reasoned exemption (see UNPROVEN):")
        for label in exempt:
            print(f"  - {label}")

    return 1 if (findings or problems) else 0


def _tail(text: str, lines: int = 6) -> str:
    return "\n    ".join((text or "").strip().splitlines()[-lines:])



# A TransactionTestCase truncates every table at teardown and does not roll it
# back. Against the persisted --keepdb database that is permanent: the seed
# migrations stay recorded as applied and never re-run, so the RBAC catalog is
# gone for every later test AND every later run. The failure surfaces as 403s in
# unrelated suites, and the flush need not even be in the same run as the
# failure -- which is why bisecting the failing file never finds it.
#
# The plant is a bare TransactionTestCase with no mixin and no marker: the exact
# shape all fifteen classes had before 2026-09-06. It must be `create` plus the
# harness's `git add -N`, because the scanner discovers candidates with
# `git grep` -- an untracked plant would be invisible and this gate would look
# dead while working perfectly.
MUTATIONS["unrestored-flush-testcase"] = Mutation(
    kind="create",
    path=f"apps/schools/tests/{_PROOF}_unrestored_flush.py",
    defect=(
        "a test class that truncates the seeded RBAC catalog at teardown and does "
        "not put it back, poisoning the persisted keepdb database for every later "
        "run on that machine"
    ),
    content=(
        b"from django.test import TransactionTestCase" + chr(10).encode()
        + chr(10).encode()
        + chr(10).encode()
        + b"class GateProofUnrestoredFlushTests(TransactionTestCase):" + chr(10).encode()
        + b"    def test_nothing(self):" + chr(10).encode()
        + b"        pass" + chr(10).encode()
    ),
)

# MUST stay ABOVE the __main__ guard. An entry appended below it is present on
# import and DEAD when the file runs as a script, so gates-can-fail-coverage
# reports the gate as registered-with-no-mutation and aborts the push. That
# happened with the entry above on 2026-09-06; do not repeat it.
MUTATIONS["refusal-only-authorization"] = Mutation(
    kind="create",
    path=f"apps/schools/tests/{_PROOF}_refusal_only.py",
    defect=(
        "an authorization test whose only assertion is a refusal status code, so "
        "it passes when the request is refused for ANY reason -- a permission "
        "gap, an MFA redirect, a renamed URL -- and cannot fail when the thing it "
        "claims to test breaks"
    ),
    content=(
        b"from django.test import TestCase" + chr(10).encode()
        + chr(10).encode()
        + chr(10).encode()
        + b"class GateProofRefusalOnlyTests(TestCase):" + chr(10).encode()
        + b"    def test_cross_tenant_blocked(self):" + chr(10).encode()
        + b"        self.assertEqual(self.client.get(chr(47)).status_code, 403)"
        + chr(10).encode()
    ),
)


if __name__ == "__main__":
    raise SystemExit(main())
