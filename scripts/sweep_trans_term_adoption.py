#!/usr/bin/env python
"""Wave O3 — bulk `{% trans %}` → `{% trans_term %}` adoption sweep.

For every template under ``templates/``, find ``{% trans "<Noun>" %}``
calls where ``<Noun>`` (case-sensitive singular/plural) is a canonical
lexicon registry default, and convert them to the hybrid
``{% trans_term "<Noun>" key="<noun_key>" %}`` form (with ``plural=True``
when matching the plural).

Adds ``{% load terminology_tags %}`` near the existing ``{% load i18n %}``
directive when the file doesn't already load it.

The script is idempotent — running it twice produces the same diff as
running it once.

Conservative inclusion rules:

* Only ``{% trans "Word" %}`` form with simple double-quoted strings.
  Not ``{% trans 'Word' %}`` single-quoted (Django supports both, but
  scanning gets noisier).
* Not ``{% blocktrans %}`` blocks (different syntax, often interpolate).
* Only canonical registry defaults (Student, Students, Teacher, …)
  to satisfy Wave M's "coherence rule": ``source`` must match the
  registry default for the no-override branch to render coherently.

Usage:
    python scripts/sweep_trans_term_adoption.py             # apply changes
    python scripts/sweep_trans_term_adoption.py --dry-run   # report only
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
TEMPLATES_ROOT = REPO_ROOT / "templates"


def _load_canonical_map() -> dict[str, tuple[str, bool]]:
    """Build {"Student": ("student", False), "Students": ("student", True), …}
    from the lexicon registry. Singular maps to (key, plural=False); plural to
    (key, plural=True).
    """
    sys.path.insert(0, str(REPO_ROOT))
    try:
        from apps.siteconfig.lexicon_catalog import LEXICON_REGISTRY
    except ImportError:
        raise
    finally:
        sys.path.pop(0)

    out: dict[str, tuple[str, bool]] = {}
    for key, (sing, plur, _cat, _desc) in LEXICON_REGISTRY.items():
        # Singular wins if multiple keys map to the same singular form;
        # this is rare in practice. Iteration order in dict is insertion
        # order, so the registry's canonical key wins.
        out.setdefault(sing, (key, False))
        if plur and plur != sing:
            out.setdefault(plur, (key, True))
    return out


# Match `{% trans "Word" %}` exactly. Word is alpha (allow spaces for
# multi-word entries like "Head teacher" / "Staff member"). Conservative
# regex — won't match `{% trans 'Word' %}` or interpolated forms.
_TRANS_RE = re.compile(r'\{%\s*trans\s+"([A-Za-z][A-Za-z\- ]+)"\s*%\}')

_LOAD_TERMINOLOGY_RE = re.compile(r"\{%\s*load\s+[^%]*\bterminology_tags\b[^%]*%\}")
_LOAD_I18N_RE = re.compile(r"(\{%\s*load\s+[^%]*\bi18n\b[^%]*%\})")


def _ensure_load_terminology_tags(source: str) -> str:
    """Insert ``{% load terminology_tags %}`` on its own line after the
    first ``{% load …i18n… %}`` if it's not already loaded. Idempotent.
    """
    if _LOAD_TERMINOLOGY_RE.search(source):
        return source
    match = _LOAD_I18N_RE.search(source)
    if not match:
        # Template doesn't load i18n either — out of scope for this sweep.
        return source
    insert_at = match.end()
    return source[:insert_at] + "\n{% load terminology_tags %}" + source[insert_at:]


def _convert_file(path: Path, canonical: dict[str, tuple[str, bool]]) -> tuple[str, int]:
    """Return (new_content, num_conversions). If 0 conversions, content
    is unchanged.
    """
    try:
        source = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return "", 0

    count = 0

    def _replace(match: re.Match) -> str:
        nonlocal count
        word = match.group(1)
        entry = canonical.get(word)
        if entry is None:
            return match.group(0)
        key, is_plural = entry
        count += 1
        plural_part = " plural=True" if is_plural else ""
        return f'{{% trans_term "{word}" key="{key}"{plural_part} %}}'

    new_source = _TRANS_RE.sub(_replace, source)
    if count:
        new_source = _ensure_load_terminology_tags(new_source)
    return new_source, count


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true",
                        help="Report changes without writing files.")
    args = parser.parse_args()

    canonical = _load_canonical_map()

    total_files = 0
    total_conversions = 0
    files_changed: list[tuple[Path, int]] = []

    if not TEMPLATES_ROOT.exists():
        print(f"templates dir not found: {TEMPLATES_ROOT}", file=sys.stderr)
        return 2

    for path in TEMPLATES_ROOT.rglob("*.html"):
        total_files += 1
        new_content, n = _convert_file(path, canonical)
        if n == 0:
            continue
        files_changed.append((path, n))
        total_conversions += n
        if not args.dry_run:
            path.write_text(new_content, encoding="utf-8")

    print(f"Scanned {total_files} templates.")
    print(f"Converted {total_conversions} `{{% trans %}}` -> `{{% trans_term %}}` calls "
          f"across {len(files_changed)} files.")
    if files_changed:
        print()
        for path, n in sorted(files_changed):
            print(f"  {n:3d}  {path.relative_to(REPO_ROOT)}")
    if args.dry_run:
        print("\n(dry-run; no files written)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
