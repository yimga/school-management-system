#!/usr/bin/env python3
"""verify_companion_server_contract.py -- every RMC server path a companion
sibling targets must actually resolve on at least one urlconf.

The four ``companion-*/`` siblings are separate programs that talk to this
Django server over HTTP. Nothing in this repository ever checked that the
paths they hardcode exist. On 2026-09-02 a resolve of every such literal
against all four urlconfs returned **404 for every single one** -- including
``/api/v1/auth/login/``, so the shipped desktop app cannot complete step 1 of
its own four-step flow. Both the Tauri desktop app and the Docker appliance
are built and released by GitHub workflows in this repo.

The contract is not folklore: ``docs/COMPANION_SIBLINGS_HANDSHAKE_AND_CSV_INGEST.md``
specifies these exact paths ("Endpoint: ``POST /api/v1/auth/login/``",
"``GET /api/v1/migration/maa/text/``", ...). The clients implement the spec.
The server never mounted it. The equivalent views DO exist -- but only under
``/super/migration/companion/`` and ``/portal/configure/migration/companion/``,
which are session-gated HTML shells: ``maa_text_view`` is ``@login_required``
and ``MAASignView`` / ``CompanionUploadView`` are ``LoginRequiredMixin``, so a
Bearer JWT (which is all a companion has) authenticates none of them.

**Why nobody noticed.** Each client failure is silent by construction. The
Tauri pubkey fetch is commented "Best-effort" and wrapped in ``if (pubResp.ok)``,
so a 404 leaves ``serverPubkeyB64`` null and the user gets "Cannot ingest:
complete login + MAA + server pubkey fetch first" -- advice they cannot act on,
because the only assignment to that variable is the dead fetch.

This gate closes the class, not just the instance: it extracts every ``/api/...``
path literal from the sibling sources, resolves each against
``config.urls`` / ``config.tenant_urls`` / ``config.manager_urls`` /
``config.public_urls``, and fails on any that resolves nowhere.

Baseline (``var/companion-server-contract-baseline.json``) records the paths
already dead when the gate landed, each with a written reason. It is a RATCHET,
not a mute button:

  * a dead path NOT in the baseline  -> FAIL (a new one was introduced)
  * a baselined path that now RESOLVES -> FAIL (stale entry, delete it)
  * a baseline entry with no ``reason`` -> FAIL (no silent absences)

and every baselined path is printed in full on every run, so the outstanding
work stays visible instead of decaying into a number.

Usage::

    python scripts/verify_companion_server_contract.py            # gate
    python scripts/verify_companion_server_contract.py --json     # machine-readable
    python scripts/verify_companion_server_contract.py --self-check   # prove it can fail

Exit codes::

    0 -- every targeted path resolves, or is an unchanged baselined known-dead
    1 -- a new dead path, a stale baseline entry, or a reason-less baseline entry
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(_HERE)

BASELINE_PATH = os.path.join(REPO_ROOT, "var", "companion-server-contract-baseline.json")

SIBLINGS = (
    "companion-tauri",
    "companion-docker",
    "companion-extension",
    "companion-capacitor",
)

# Only source the clients actually execute. Markdown is deliberately excluded:
# the spec being right is not in question, the mount is.
SOURCE_EXT = {".rs", ".ts", ".tsx", ".js", ".jsx", ".py"}

SKIP_DIRS = {
    "node_modules", "target", "dist", "build", "__pycache__",
    ".git", ".venv", "venv", "coverage", "test-results",
}

# A path literal is anchored on /api/ so we never pick up a sibling's OWN local
# routes (the Docker appliance serves /handshake/login itself -- that one is not
# an RMC server path and must not be resolved against this project's urlconfs).
PATH_RE = re.compile(r"/api/v[0-9]+/[A-Za-z0-9/_.<>:-]*")

# Substituted before resolving so a documented capture group still resolves.
PLACEHOLDER_RE = re.compile(r"<[A-Za-z_][A-Za-z0-9_]*>")

URLCONFS = (
    "config.urls",
    "config.tenant_urls",
    "config.manager_urls",
    "config.public_urls",
)


def _is_test_path(rel: str) -> bool:
    parts = rel.replace("\\", "/").split("/")
    return any(p in ("tests", "test", "__tests__", "e2e") for p in parts) or any(
        p.startswith("test_") or p.endswith(".test.ts") or p.endswith(".spec.ts")
        for p in parts
    )


def collect_targets(root: str = REPO_ROOT) -> dict:
    """Return {path_literal: sorted[source rel-paths]} across every sibling."""
    found: dict = {}
    for sib in SIBLINGS:
        base = os.path.join(root, sib)
        if not os.path.isdir(base):
            continue
        for dirpath, dirnames, filenames in os.walk(base):
            dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
            for fn in filenames:
                if os.path.splitext(fn)[1] not in SOURCE_EXT:
                    continue
                full = os.path.join(dirpath, fn)
                rel = os.path.relpath(full, root).replace("\\", "/")
                if _is_test_path(rel):
                    continue
                try:
                    with open(full, "r", encoding="utf-8", errors="replace") as fh:
                        text = fh.read()
                except OSError:
                    continue
                for m in PATH_RE.finditer(text):
                    literal = m.group(0)
                    # `/api/v1/...` in prose is not a path.
                    if "..." in literal:
                        continue
                    # Trim a trailing separator picked up from prose/format strings.
                    literal = literal.rstrip(".,:")
                    if not literal.endswith("/"):
                        literal += "/"
                    found.setdefault(literal, set()).add(rel)
    return {k: sorted(v) for k, v in sorted(found.items())}


def resolve_everywhere(literal: str) -> list:
    """Return the urlconfs on which ``literal`` resolves."""
    from django.urls import Resolver404, resolve

    probe = PLACEHOLDER_RE.sub("1", literal)
    hits = []
    for uc in URLCONFS:
        try:
            resolve(probe, urlconf=uc)
        except Resolver404:
            continue
        except Exception:
            # A resolver that raises anything else cannot be said to serve the
            # path; treat it as a miss rather than inventing a pass.
            continue
        hits.append(uc)
    return hits


def load_baseline() -> dict:
    if not os.path.isfile(BASELINE_PATH):
        return {}
    with open(BASELINE_PATH, "r", encoding="utf-8") as fh:
        doc = json.load(fh)
    return {e["path"]: e for e in doc.get("known_dead", [])}


def scan() -> dict:
    targets = collect_targets()
    dead, live = {}, {}
    for literal, sources in targets.items():
        hits = resolve_everywhere(literal)
        (live if hits else dead)[literal] = {"sources": sources, "urlconfs": hits}
    return {"targets": targets, "dead": dead, "live": live}


def evaluate(result: dict, baseline: dict) -> dict:
    dead = result["dead"]
    live = result["live"]

    new_dead = {p: v for p, v in dead.items() if p not in baseline}
    stale = [p for p in baseline if p in live]
    reasonless = [p for p, e in baseline.items() if not (e.get("reason") or "").strip()]
    known_dead = {p: v for p, v in dead.items() if p in baseline}

    return {
        "new_dead": new_dead,
        "stale_baseline": sorted(stale),
        "reasonless_baseline": sorted(reasonless),
        "known_dead": known_dead,
        "live_count": len(live),
        "target_count": len(result["targets"]),
        "ok": not (new_dead or stale or reasonless),
    }


# --------------------------------------------------------------------------
# self-check: prove the gate can fail, without touching the working tree
# --------------------------------------------------------------------------

SELF_CHECK_CASES = (
    # (label, dead, live, baseline, expect_ok)
    (
        "clean tree: everything resolves",
        {}, {"/api/v1/x/": {}}, {}, True,
    ),
    (
        "a new dead path with no baseline entry",
        {"/api/v1/new/": {"sources": ["companion-tauri/src/a.ts"], "urlconfs": []}},
        {}, {}, False,
    ),
    (
        "a dead path that IS baselined, with a reason",
        {"/api/v1/known/": {"sources": ["x"], "urlconfs": []}},
        {},
        {"/api/v1/known/": {"path": "/api/v1/known/", "reason": "not built yet"}},
        True,
    ),
    (
        "a baselined path that now resolves -> stale entry",
        {}, {"/api/v1/known/": {}},
        {"/api/v1/known/": {"path": "/api/v1/known/", "reason": "not built yet"}},
        False,
    ),
    (
        "a baseline entry with an empty reason",
        {"/api/v1/known/": {"sources": ["x"], "urlconfs": []}},
        {},
        {"/api/v1/known/": {"path": "/api/v1/known/", "reason": "   "}},
        False,
    ),
    (
        "a baseline entry with no reason key at all",
        {"/api/v1/known/": {"sources": ["x"], "urlconfs": []}},
        {},
        {"/api/v1/known/": {"path": "/api/v1/known/"}},
        False,
    ),
)


def self_check() -> int:
    failures = 0
    for label, dead, live, baseline, expect_ok in SELF_CHECK_CASES:
        verdict = evaluate(
            {"dead": dead, "live": live, "targets": dict(dead, **live)}, baseline
        )
        got = verdict["ok"]
        mark = "ok  " if got == expect_ok else "FAIL"
        if got != expect_ok:
            failures += 1
        print("  %s  expect_ok=%-5s got_ok=%-5s  %s" % (mark, expect_ok, got, label))

    # The extractor must also be provably able to see a path.
    extracted = list(PATH_RE.finditer('const P = "/api/v1/migration/maa/text/";'))
    if len(extracted) != 1 or extracted[0].group(0) != "/api/v1/migration/maa/text/":
        print("  FAIL  extractor did not find the path in a plain literal")
        failures += 1
    else:
        print("  ok    extractor finds a path in a plain literal")

    if PATH_RE.search('format!("{}/api/v1/migration/companion/upload/", base)') is None:
        print("  FAIL  extractor missed a path inside a format! string")
        failures += 1
    else:
        print("  ok    extractor finds a path inside a format! string")

    if [m for m in PATH_RE.finditer("targets the /api/v1/... endpoints")
            if "..." not in m.group(0)]:
        print("  FAIL  extractor treated prose `/api/v1/...` as a path")
        failures += 1
    else:
        print("  ok    extractor ignores prose `/api/v1/...`")

    print()
    if failures:
        print("COMPANION_SERVER_CONTRACT_SELFCHECK_FAIL: %d case(s)" % failures)
        return 1
    print("COMPANION_SERVER_CONTRACT_SELFCHECK_PASS: %d cases"
          % (len(SELF_CHECK_CASES) + 3))
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description="companion <-> server path contract")
    ap.add_argument("--json", action="store_true", help="machine-readable output")
    ap.add_argument("--self-check", action="store_true",
                    help="prove the gate can fail; no Django, no tree access")
    args = ap.parse_args()

    if args.self_check:
        return self_check()

    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings_test")
    if REPO_ROOT not in sys.path:
        sys.path.insert(0, REPO_ROOT)
    import django

    django.setup()

    result = scan()
    baseline = load_baseline()
    verdict = evaluate(result, baseline)

    if args.json:
        print(json.dumps(
            {
                "target_count": verdict["target_count"],
                "live_count": verdict["live_count"],
                "new_dead": sorted(verdict["new_dead"]),
                "stale_baseline": verdict["stale_baseline"],
                "reasonless_baseline": verdict["reasonless_baseline"],
                "known_dead": sorted(verdict["known_dead"]),
                "ok": verdict["ok"],
            },
            indent=2, sort_keys=True,
        ))
        return 0 if verdict["ok"] else 1

    print("companion server-path contract: %d path(s) targeted, %d resolve"
          % (verdict["target_count"], verdict["live_count"]))

    if verdict["known_dead"]:
        print()
        print("KNOWN-DEAD (baselined, still outstanding -- these clients cannot work):")
        for path in sorted(verdict["known_dead"]):
            entry = baseline[path]
            print("  %s" % path)
            print("      reason: %s" % entry.get("reason", ""))
            for src in verdict["known_dead"][path]["sources"]:
                print("      called by: %s" % src)

    if verdict["new_dead"]:
        print()
        print("FAIL -- a companion targets a server path that resolves on NO urlconf,")
        print("        and it is not in the baseline:")
        for path in sorted(verdict["new_dead"]):
            print("  %s" % path)
            for src in verdict["new_dead"][path]["sources"]:
                print("      called by: %s" % src)

    if verdict["stale_baseline"]:
        print()
        print("FAIL -- these baseline entries now RESOLVE; delete them from")
        print("        var/companion-server-contract-baseline.json:")
        for path in verdict["stale_baseline"]:
            print("  %s" % path)

    if verdict["reasonless_baseline"]:
        print()
        print("FAIL -- these baseline entries carry no reason. A known-dead path")
        print("        without a written reason is the silent absence this gate exists")
        print("        to prevent:")
        for path in verdict["reasonless_baseline"]:
            print("  %s" % path)

    print()
    if verdict["ok"]:
        print("COMPANION_SERVER_CONTRACT_PASS")
        return 0
    print("COMPANION_SERVER_CONTRACT_FAIL")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
