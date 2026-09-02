#!/usr/bin/env python
"""A stylesheet that asks for an asset nobody shipped fails silently, in production.

``ForgivingCompressedManifestStaticFilesStorage`` deliberately refuses to fail a
deploy over a reference it cannot resolve -- that forgiveness is the only reason
hashed static files could be turned on at all. The cost is that a genuinely
missing asset never stops anything. It logs, the deploy goes green, and the icon
is simply absent for every user.

On 2026-09-02 the production deploy log carried this line:

    leaving 'vendor/bootstrap-icons/css/fonts/bootstrap-icons.woff?dd670306...'
    un-hashed (missing reference: ...)

The vendored bootstrap-icons CSS declared a ``.woff`` fallback; only ``.woff2``
was ever copied into ``static/``. It survived unnoticed because it was printed at
the same WARNING level as eight source-map misses, repeated across three
post-processing passes -- roughly two dozen identical-looking lines, one of which
was real.

Two things came out of that. ``apps/siteconfig/staticfiles_storage.py`` now logs
a missing ``.map`` at INFO and everything else at WARNING, so the level carries
the meaning. And this gate, so the class does not come back.

**Zero-tolerance, no baseline JSON.** The tree was measured at 0 on introduction
(899 CSS/JS files, 9 dev-only ``.map`` misses, 0 shipped-asset gaps), so there is
nothing to grandfather. A finding here is always a real missing file.

Deliberately narrow, because a gate that cries wolf gets switched off:

* **``url()`` and ``@import`` are read from CSS only.** In JavaScript ``url(x)``
  is a function call. The first cut of this scanner read both grammars from both
  file types and reported 40+ hits like ``url(credential.rawId)`` and
  ``url(response.signature)`` -- every one of them a local variable.
* **``data:`` payloads are stripped before matching.** An inline SVG data URI
  contains its own nested ``filter='url(%23n)'``. The outer ``url()`` is skipped
  correctly as a data URI, but the nested one matched on its own and was reported
  as a missing asset in two files. Both were false.
* **Query strings and fragments are stripped, and the reference is rstripped.**
  Upstream writes cache-busting refs (``x.woff?dd670306``), and the vendored
  bootstrap CSS really does carry a trailing space after
  ``sourceMappingURL=bootstrap.min.css.map`` -- verified with ``cat -A``.
* **A ``.map`` is never a finding.** Source maps are development artifacts and
  are legitimately not shipped. They are counted and reported separately so the
  number stays visible rather than silently dropped.
* **Absolute refs resolve from the repo root, relative ones from the referring
  file** -- the same way the CSS itself is served.

Run ``--compare`` for the gate (exit 1 on any shipped-asset gap), or bare for the
full report including the dev-only tally.
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
STATIC_DIRNAME = "static"

URL_RE = re.compile(rb"url\(\s*['\"]?([^'\")]+)['\"]?\s*\)")
IMPORT_RE = re.compile(rb"@import\s+['\"]([^'\"]+)['\"]")
SMAP_RE = re.compile(rb"sourceMappingURL\s*=\s*([^\s*'\"]+)")

# Quoted and bare inline data URIs. Replaced wholesale so a nested url() inside
# an SVG payload cannot be mistaken for a reference of its own.
DATA_URI_QUOTED_RE = re.compile(rb"url\(\s*(['\"])data:.*?\1\s*\)", re.S)
DATA_URI_BARE_RE = re.compile(rb"url\(\s*data:[^)]*\)")
DATA_URI_PLACEHOLDER = b"url(about:stripped)"

NOT_A_LOCAL_FILE = (
    "http://",
    "https://",
    "//",
    "data:",
    "#",
    "about:",
    "chrome-extension:",
    "moz-extension:",
)

DEV_ONLY_SUFFIXES = (".map",)


def normalise(reference: str) -> str:
    """Strip query, fragment and trailing whitespace -- what the storage sees."""
    return reference.split("?", 1)[0].split("#", 1)[0].strip()


def is_dev_only(clean_reference: str) -> bool:
    return clean_reference.endswith(DEV_ONLY_SUFFIXES)


def references_in(path: Path, blob: bytes) -> set[str]:
    blob = DATA_URI_QUOTED_RE.sub(DATA_URI_PLACEHOLDER, blob)
    blob = DATA_URI_BARE_RE.sub(DATA_URI_PLACEHOLDER, blob)
    is_css = path.suffix.lower() == ".css"
    rules = (URL_RE, IMPORT_RE, SMAP_RE) if is_css else (SMAP_RE,)
    found = set()
    for rule in rules:
        for match in rule.finditer(blob):
            found.add(match.group(1).decode("utf-8", "replace"))
    return found


def scan(repo_root: Path):
    """Return (dev_only, shipped_gaps, files_scanned)."""
    static_root = repo_root / STATIC_DIRNAME
    dev_only: list[tuple[str, str]] = []
    shipped: list[tuple[str, str]] = []
    scanned = 0
    if not static_root.is_dir():
        return dev_only, shipped, scanned
    for path in sorted(static_root.rglob("*")):
        if not path.is_file() or path.suffix.lower() not in (".css", ".js"):
            continue
        scanned += 1
        try:
            blob = path.read_bytes()
        except OSError:
            continue
        for reference in references_in(path, blob):
            clean = normalise(reference)
            if not clean or clean.startswith(NOT_A_LOCAL_FILE):
                continue
            if clean.startswith("/"):
                target = repo_root / clean.lstrip("/")
            else:
                target = path.parent / clean
            try:
                if target.resolve().is_file():
                    continue
            except OSError:
                pass
            record = (str(path.relative_to(repo_root)).replace("\\", "/"), reference)
            (dev_only if is_dev_only(clean) else shipped).append(record)
    return dev_only, shipped, scanned


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--compare",
        action="store_true",
        help="gate mode: exit 1 if any shipped asset is referenced but absent",
    )
    parser.add_argument("--root", default=str(REPO_ROOT))
    args = parser.parse_args(argv)

    dev_only, shipped, scanned = scan(Path(args.root).resolve())

    print("dangling-static-reference: %d CSS/JS file(s) under %s/" % (scanned, STATIC_DIRNAME))
    print("  dev-only (.map, expected absent in production): %d" % len(dev_only))
    print("  shipped assets referenced but NOT present:      %d" % len(shipped))
    for referrer, reference in sorted(shipped):
        print("    %s" % referrer)
        print("        -> %s" % reference)
    if shipped:
        print(
            "\nEach line above is an asset the browser will request and not get.\n"
            "Ship the file, or drop the reference -- do not silence the warning."
        )
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
