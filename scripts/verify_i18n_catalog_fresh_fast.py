#!/usr/bin/env python3
"""Catalog-freshness seal, fast enough to sit on every push.

WHY A SECOND SCRIPT
-------------------
``verify_i18n_catalog_fresh.py`` answers the right question -- is every string the
i18n scanner can see actually present in ``locale/en/LC_MESSAGES/django.po``? -- and
is deliberately NOT wired into ``scripts/pre_push_boundary_check.py`` because it
costs minutes (170.5s measured on 2026-08-31 on an otherwise-idle machine; its own
docstring in the hook says ~7 min on a busy one). That call was right: a multi-minute
check on a shared clone's push path is a check people turn off.

The cost was never in the *question*, it was in three implementation details:

  1. ``django.setup()`` -- 16.9s -- for a scanner that imports nothing from Django.
     ``apps/siteconfig/i18n_catalog_builder.py`` is pure ``ast`` + ``re`` + ``polib``,
     so it is loaded here BY PATH and Django is never started.
  2. ``ast.parse`` on all 7,670 Python files. Only 747 of them contain ``_(`` or
     ``gettext`` at all; a byte-level prefilter over bytes we have already read skips
     the other 6,923 (0.12s to decide, 5.3s saved).
  3. ``polib.pofile()`` on the 2 MB ``en`` catalog (0.7s) where a msgid-only scan of
     the same bytes answers the membership question in 0.06s.

It is the SAME question over the SAME corpus with the SAME extractor functions --
imported, not copied, so the two cannot drift -- and
``apps/siteconfig/tests/test_i18n_fast_gate_parity.py`` asserts the two produce a
byte-identical missing-msgid set. This is not a cheaper approximation; it is the
same answer computed without the waste.

MEASURED (2026-08-31, this repository, warm page cache):

    verify_i18n_catalog_fresh.py --compare        170.5s
    verify_i18n_catalog_fresh_fast.py --compare    11.0s

No cache is kept on disk on purpose. A cache is the one way this check could report
a false green, and a gate that can be silently wrong is worth less than the seconds
it saves.

    python scripts/verify_i18n_catalog_fresh_fast.py            # binary: any gap fails
    python scripts/verify_i18n_catalog_fresh_fast.py --compare  # ratchet vs baseline
    python scripts/verify_i18n_catalog_fresh_fast.py --json
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
import re
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

#: Shared with verify_i18n_catalog_fresh.py -- ONE baseline for one contract, so a
#: gap frozen for the slow gate is frozen for this one and neither can be greener
#: than the other by accident.
BASELINE_PATH = ROOT / "var" / "security-audit-baseline-i18n-catalog-fresh.json"

#: Exit code the pre-push runner reads as "my toolchain is not installed here".
SKIPPED_EXIT_CODE = 2

# Byte needles. A file that contains none of these cannot produce a msgid under the
# builder's own patterns, so it is skipped before any parse. Deliberately WIDER than
# the patterns themselves (a bare ``_(`` catches every gettext alias) -- this may
# admit files that yield nothing, and must never exclude one that would.
_PY_NEEDLES = (b"_(", b"gettext")
_TPL_NEEDLES = (b"trans", b"_(")
_JS_NEEDLES = (b"gettext",)

_MSGID_LINE = re.compile(rb'^msgid "(.*)"\s*$', re.M)
_CONT_LINE = re.compile(rb'^"(.*)"\s*$', re.M)


def _load_builder(root: Path):
    """Import the catalog builder BY PATH so no Django app registry is needed."""
    path = root / "apps" / "siteconfig" / "i18n_catalog_builder.py"
    if not path.is_file():
        return None
    spec = importlib.util.spec_from_file_location("_rmc_i18n_catalog_builder", path)
    if spec is None or spec.loader is None:
        return None
    module = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(module)
    except Exception:  # noqa: BLE001 - a missing polib means SKIP, never a false pass
        return None
    return module


def _walk(base: Path, suffixes: tuple[str, ...], skip: frozenset[str]) -> list[Path]:
    """os.scandir walk (0.15s for 10k files) rather than Path.rglob + per-file stat."""
    out: list[Path] = []
    if not base.is_dir():
        return out
    stack = [str(base)]
    while stack:
        current = stack.pop()
        try:
            with os.scandir(current) as entries:
                for entry in entries:
                    if entry.is_dir(follow_symlinks=False):
                        if entry.name not in skip:
                            stack.append(entry.path)
                    elif entry.name.endswith(suffixes):
                        out.append(Path(entry.path))
        except OSError:
            continue
    return out


def _read(path: Path) -> bytes | None:
    try:
        if path.stat().st_size > 2_000_000:
            return None  # mirrors the builder's own size cap
        return path.read_bytes()
    except OSError:
        return None


def collect_translatable_strings_fast(root: Path, builder) -> set[str]:
    """Same result as ``builder.collect_translatable_strings``, without the waste."""
    skip = builder._SKIP_DIR_NAMES
    strings: set[str] = set()

    template_dirs = [root / "templates"]
    py_dirs = [root / "config", root / "services"]
    apps_dir = root / "apps"
    app_py: list[Path] = []
    if apps_dir.is_dir():
        for app in apps_dir.iterdir():
            if not app.is_dir():
                continue
            if (app / "templates").is_dir():
                template_dirs.append(app / "templates")
            app_py += _walk(app, (".py",), skip)

    for directory in template_dirs:
        for path in _walk(directory, (".html", ".txt"), skip):
            blob = _read(path)
            if blob is None or not any(n in blob for n in _TPL_NEEDLES):
                continue
            strings |= builder._collect_from_template(path)

    py_files = app_py + [p for d in py_dirs for p in _walk(d, (".py",), skip)]
    for path in py_files:
        blob = _read(path)
        if blob is None or not any(n in blob for n in _PY_NEEDLES):
            continue
        strings |= builder._collect_from_py(path)

    for path in _walk(root / "static", (".js",), skip):
        blob = _read(path)
        if blob is None or not any(n in blob for n in _JS_NEEDLES):
            continue
        strings |= builder._collect_from_js(path)

    return {s for s in strings if s and len(s) < 5000 and not s.isspace()}


def _unescape(raw: bytes) -> str:
    text = raw.decode("utf-8", "replace")
    out: list[str] = []
    i = 0
    while i < len(text):
        ch = text[i]
        if ch == "\\" and i + 1 < len(text):
            nxt = text[i + 1]
            out.append({"n": "\n", "t": "\t", "r": "\r", '"': '"', "\\": "\\"}.get(nxt, nxt))
            i += 2
            continue
        out.append(ch)
        i += 1
    return "".join(out)


def po_msgids(po_path: Path) -> set[str]:
    """msgid set of a .po, handling gettext's multi-line continuation form.

    polib gives the same answer in 0.7s; this is 0.06s and needs no dependency at
    all, which keeps this gate runnable on a clone that has not installed polib.
    """
    try:
        blob = po_path.read_bytes()
    except OSError:
        return set()
    out: set[str] = set()
    lines = blob.split(b"\n")
    i = 0
    while i < len(lines):
        line = lines[i].rstrip(b"\r")
        m = _MSGID_LINE.match(line)
        if not m:
            i += 1
            continue
        parts = [m.group(1)]
        i += 1
        while i < len(lines):
            cont = _CONT_LINE.match(lines[i].rstrip(b"\r"))
            if not cont:
                break
            parts.append(cont.group(1))
            i += 1
        msgid = _unescape(b"".join(parts))
        if msgid:
            out.add(msgid)
    return out


def missing_msgids(root: Path, builder) -> set[str]:
    discovered = collect_translatable_strings_fast(root, builder)
    return discovered - po_msgids(root / "locale" / "en" / "LC_MESSAGES" / "django.po")


def _load_baseline(path: Path) -> set[str] | None:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return set(data.get("missing", []))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", default=str(ROOT), help="Repository root.")
    parser.add_argument(
        "--compare",
        action="store_true",
        help="Ratchet: fail only on a msgid missing NOW and absent from the baseline.",
    )
    parser.add_argument("--baseline", default=str(BASELINE_PATH))
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--quiet", action="store_true")
    args = parser.parse_args(argv)

    root = Path(args.base).resolve()
    if not root.is_dir():
        print(f"--base is not a directory: {root}", file=sys.stderr)
        return 1

    # The extractor always comes from THIS repository, never from --base: --base
    # names the tree to scan (a fixture tree in the parity tests), not the tree the
    # scanner lives in.
    builder = _load_builder(ROOT)
    if builder is None:
        # SKIP, never PASS: reporting green for a check that did not run is the
        # exact failure this repository keeps finding in its own gates.
        print(
            "SKIP: apps/siteconfig/i18n_catalog_builder.py could not be loaded "
            "(missing polib?); this gate did NOT run.",
            file=sys.stderr,
        )
        return SKIPPED_EXIT_CODE

    started = time.time()
    missing = missing_msgids(root, builder)
    elapsed = time.time() - started

    if args.compare:
        frozen = _load_baseline(Path(args.baseline).resolve())
        if frozen is None:
            print(
                f"FAIL: --compare needs a baseline at {args.baseline}; create it with "
                "verify_i18n_catalog_fresh.py --update-baseline.",
                file=sys.stderr,
            )
            return 1
        offending = sorted(missing - frozen)
    else:
        offending = sorted(missing)

    if args.json:
        print(
            json.dumps(
                {
                    "finding_count": len(offending),
                    "missing_total": len(missing),
                    "seconds": round(elapsed, 2),
                    "findings": offending,
                },
                indent=2,
                ensure_ascii=False,
            )
        )
    elif not args.quiet:
        print(f"scanned in {elapsed:.1f}s; {len(missing)} msgid(s) missing from en django.po")

    if offending:
        print(
            f"FAIL: {len(offending)} translatable string(s) wrapped in the codebase but "
            "absent from locale/en/LC_MESSAGES/django.po.",
            file=sys.stderr,
        )
        print(
            "Fix: python manage.py sync_i18n_catalog --compile  (then commit locale/).",
            file=sys.stderr,
        )
        for m in offending[:40]:
            print(f"  {m[:120]!r}", file=sys.stderr)
        if len(offending) > 40:
            print(f"  ... and {len(offending) - 40} more", file=sys.stderr)
        return 1

    print(f"OK: en django.po covers every scanned translatable string ({elapsed:.1f}s).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(None))
