#!/usr/bin/env python3
"""Compile EVERY project template through Django and flag ``TemplateSyntaxError``.

This is the runtime sibling of ``audit_template_render_safety.py`` and the final
member of the "template that ships broken" defense. It closes a real gate seam
that let a live ``/help/`` 500 reach production (``61fee3237``):

    templates/feedback/help_center.html used ``{% trans 'What's new' %}`` — the
    apostrophe closed the single-quoted string literal, so Django could not
    COMPILE the template ("Could not parse the remainder: 's' from ''What's'").
    Every visitor got a 500 at ``render()``.

Why neither existing gate caught it:

* ``verify_template_reference_integrity.py`` DOES ``get_template(name)`` (which
  compiles) for every ``render()`` target — but its ``exists()`` helper does
  ``except Exception: return True  # syntax is another gate's job``, so it
  deliberately SWALLOWS ``TemplateSyntaxError`` and only reports
  ``TemplateDoesNotExist``.
* ``audit_template_render_safety.py`` — the "another gate" it defers to — is
  stdlib-only (it runs in the deps-free ``architectural-boundaries`` job) and
  only does regex/structural checks (tag balance, orphan tokens, missing
  includes). It never runs Django's tag-argument compiler, so a malformed
  ``{% trans '…' %}`` argument — which is structurally *balanced* — is invisible
  to it.

A bad tag ARGUMENT (``{% trans %}`` / ``{% blocktrans %}`` / a bad filter
expression / a wrong ``{% load %}`` / any custom-tag compile error) therefore
fell straight through the seam. This gate is ground truth: it asks Django's own
engine to compile each template file's exact on-disk source via
``backend.from_string(source)``. A ``TemplateSyntaxError`` (or any other
compile-time failure) is a finding.

Compiling the source directly — rather than resolving names through the loader —
means every file is checked exactly once with no shadowing ambiguity, and
include-only partials (never named by a Python ``render()`` literal) are covered
too. ``{% extends %}`` / ``{% include %}`` targets are resolved lazily at RENDER
time, not compile time, so a child compiles standalone; their existence is
already the job of ``audit_template_render_safety`` / the reference-integrity
gates.

Needs Django (live engine + installed templatetag libraries) → runs in
``ci.yml::django-tests`` after the other reference-integrity gates, NOT the
deps-free boundary job.

Zero-tolerance: any template that does not compile is a live 500 waiting to
happen, so the baseline is fixed at zero (like ``audit_template_render_safety``)
— no baseline JSON. A template that legitimately cannot compile standalone (a
genuine non-Django ``.html``, say) is excused with a
``{# template-compile-allow: <reason> #}`` marker anywhere in the file.

Scope: ``templates/**/*.html`` + ``apps/*/templates/**/*.html`` (mirrors
``audit_template_render_safety``'s discovery). ``.txt`` / ``.eml`` render
targets (email/SMS bodies) are a deliberate follow-up, not covered here.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
TEMPLATE_ROOTS = [REPO_ROOT / "templates"]
for _app_tpl in sorted((REPO_ROOT / "apps").glob("*/templates")):
    TEMPLATE_ROOTS.append(_app_tpl)

EXCLUDE_PARTS = {"node_modules", "staticfiles", ".git", "venv", ".venv"}
ALLOW_MARKER = "template-compile-allow:"


# --------------------------------------------------------------------------
# Discovery
# --------------------------------------------------------------------------
def iter_templates() -> list[Path]:
    out: list[Path] = []
    seen: set[Path] = set()
    for root in TEMPLATE_ROOTS:
        if not root.exists():
            continue
        for p in root.rglob("*.html"):
            if any(part in EXCLUDE_PARTS for part in p.parts):
                continue
            rp = p.resolve()
            if rp in seen:
                continue
            seen.add(rp)
            out.append(p)
    return sorted(out)


# --------------------------------------------------------------------------
# Core compile (engine injected so the unit tests can pass a minimal backend)
# --------------------------------------------------------------------------
def compile_source(source: str, backend) -> str | None:
    """Return an error string if ``source`` fails to compile, else ``None``."""
    from django.template import TemplateSyntaxError

    try:
        backend.from_string(source)
        return None
    except TemplateSyntaxError as e:
        return "TemplateSyntaxError: " + str(e)[:300]
    except Exception as e:  # any compile-time failure is a real, shippable bug
        return type(e).__name__ + ": " + str(e)[:300]


def _get_django_backend():
    from django.template import engines
    from django.template.backends.django import DjangoTemplates

    for engine in engines.all():
        if isinstance(engine, DjangoTemplates):
            return engine
    raise SystemExit(
        "verify_template_compiles: no DjangoTemplates engine configured in settings"
    )


def _run() -> list[dict]:
    import django

    sys.path.insert(0, str(REPO_ROOT))
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
    django.setup()
    backend = _get_django_backend()

    findings: list[dict] = []
    for p in iter_templates():
        try:
            source = p.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        if ALLOW_MARKER in source:
            continue
        error = compile_source(source, backend)
        if error is not None:
            findings.append({"path": p.relative_to(REPO_ROOT).as_posix(), "error": error})
    findings.sort(key=lambda f: f["path"])
    return findings


# --------------------------------------------------------------------------
# CLI (zero-tolerance, mirrors audit_template_render_safety's --compare parity)
# --------------------------------------------------------------------------
def _payload(findings: list[dict], scanned: int) -> dict:
    return {
        "rule": "every templates/**/*.html must compile via Django's engine "
        "(backend.from_string); a TemplateSyntaxError is a live 500. Guard a "
        "genuine non-Django .html with {# template-compile-allow: <reason> #}",
        "scanned": scanned,
        "finding_count": len(findings),
        "findings": findings,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    # --compare / --json exist for parity with the other django-tests gates;
    # this gate is zero-tolerance (no baseline file), so --compare just runs.
    parser.add_argument("--compare", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    files = iter_templates()
    findings = _run()

    if args.json:
        print(json.dumps(_payload(findings, len(files)), indent=2, sort_keys=True))
        return 1 if findings else 0

    print(
        f"template-compile: {len(files)} template(s) checked, "
        f"{len(findings)} do not compile"
    )
    for f in findings:
        print(f"  {f['path']}  {f['error']}")
    if findings:
        print(
            "\nEach template above raises at COMPILE time — a guaranteed 500 the "
            "first time it renders. Fix the template, or mark a genuine "
            "non-Django .html with {# template-compile-allow: <reason> #}."
        )
    return 1 if findings else 0


if __name__ == "__main__":
    sys.exit(main())
