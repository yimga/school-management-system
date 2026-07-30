#!/usr/bin/env python3
"""Mechanically wrap static label text in {% trans %} for i18n burndown.

Reads ``var/security-audit-baseline-untranslated-template-text.json`` (or rescans)
and wraps label-bearing elements whose direct text is static English. Skips elements
that already contain ``{% trans %}`` / ``{% blocktrans %}`` or mixed ``{{ }}`` /
``{% %}`` (those need manual blocktrans — reported at end).

Usage:
  python scripts/codemod_wrap_untranslated_template_labels.py --dry-run
  python scripts/codemod_wrap_untranslated_template_labels.py --write
  python scripts/codemod_wrap_untranslated_template_labels.py --write --rescan-baseline
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
BASELINE_PATH = REPO_ROOT / "var" / "security-audit-baseline-untranslated-template-text.json"

# Import scanner helpers for live rescans.
sys.path.insert(0, str(REPO_ROOT / "scripts"))
from scan_untranslated_template_text import scan_file  # noqa: E402

_LABEL_TAGS = ("button", "a", "label", "th", "h1", "h2", "h3", "h4", "h5", "h6",
               "option", "legend", "summary", "figcaption", "caption")
_ELEMENT_RE = re.compile(
    r"<(" + "|".join(_LABEL_TAGS) + r")(\s[^>]*)?>(.*?)</\1>",
    re.IGNORECASE | re.DOTALL,
)
_NESTED_TAG_RE = re.compile(r"<[^>]+>")
_DJANGO_FRAG_RE = re.compile(r"{{.*?}}|{%.*?%}", re.DOTALL)
_ENTITY_RE = re.compile(r"&[#0-9a-zA-Z]+;")
_LOAD_I18N_RE = re.compile(r"{%\s*load\b[^%]*\bi18n\b")
_TRANS_RE = re.compile(r"{%\s*(?:trans|blocktrans|blocktranslate)\b")


def _normalize_ws(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def _escape_trans_string(text: str) -> str:
    """Double-quoted {% trans "..." %} string literal."""
    return text.replace("\\", "\\\\").replace('"', '\\"')


def _clean_inner(inner: str) -> str:
    inner = _NESTED_TAG_RE.sub(" ", inner)
    inner = _DJANGO_FRAG_RE.sub(" ", inner)
    inner = _ENTITY_RE.sub(" ", inner)
    return _normalize_ws(inner)


def _snippet(cleaned: str) -> str:
    return re.sub(r"\s+", " ", cleaned)[:60]


def _finding_matches(tag: str, cleaned: str, finding: dict) -> bool:
    if finding["tag"] != tag:
        return False
    ft = finding["text"].rstrip("…")
    snip = _snippet(cleaned)
    return snip == finding["text"] or cleaned.startswith(ft) or ft.startswith(snip.rstrip("…"))


def _ensure_load_i18n(text: str) -> str:
    if not USES_I18N_TAG.search(text):
        return text
    if _LOAD_I18N_RE.search(text):
        # Ensure load appears before first trans/blocktrans.
        first_use = USES_I18N_TAG.search(text)
        first_load = _LOAD_I18N_RE.search(text)
        if first_use and first_load and first_load.start() > first_use.start():
            # Misplaced load — strip standalone i18n load lines and re-insert at top.
            text = re.sub(r"^\s*{%\s*load\s+i18n\s*%}\s*\n", "", text, flags=re.MULTILINE)
        else:
            return text
    m = re.search(r"{%\s*extends\s+[^%]+%}", text)
    if m:
        insert = m.end()
        after = text[insert:]
        m_loads = re.match(r"(\s*(?:{%\s*load\b[^%]+%}\s*)+)", after)
        if m_loads and "i18n" not in m_loads.group(1):
            # Append i18n to an existing combined load tag when possible.
            block = m_loads.group(1)
            combined = re.sub(
                r"({%\s*load\b[^%]*)(%})",
                r"\1 i18n\2",
                block,
                count=1,
            )
            if combined != block:
                return text[:insert] + combined + text[insert + len(block):]
            insert += m_loads.end()
        return text[:insert] + "\n{% load i18n %}" + text[insert:]
    m_load = re.match(r"(\s*(?:{%\s*load\b[^%]+%}\s*)+)", text)
    if m_load and "i18n" not in m_load.group(1):
        block = m_load.group(1)
        combined = re.sub(r"({%\s*load\b[^%]*)(%})", r"\1 i18n\2", block, count=1)
        if combined != block:
            return combined + text[len(block):]
    return "{% load i18n %}\n" + text


USES_I18N_TAG = re.compile(r"{%\s*(?:trans|blocktrans|blocktranslate)\b")


def _wrap_static_inner(inner: str, label: str) -> str | None:
    if _TRANS_RE.search(inner):
        return None
    if "{{" in inner or "{%" in inner:
        return None
    cleaned = _normalize_ws(_clean_inner(inner))
    if cleaned != _normalize_ws(label):
        return None
    trans = '{% trans "' + _escape_trans_string(cleaned) + '" %}'
    if cleaned == _normalize_ws(re.sub(r"<[^>]+>", " ", inner)):
        # Plain text only (possibly with whitespace).
        lead = re.match(r"^\s*", inner).group(0)
        trail = re.search(r"\s*$", inner).group(0)
        return f"{lead}{trans}{trail}"
    # Nested tags (e.g. icon + label text) — replace the label substring once.
    idx = inner.find(cleaned)
    if idx >= 0:
        return inner[:idx] + trans + inner[idx + len(cleaned):]
    tags_only = _NESTED_TAG_RE.sub("", inner).strip()
    if _normalize_ws(tags_only) == cleaned:
        return inner.replace(tags_only, trans, 1)
    return None


_BLOCKTRANS_TAIL_RE = re.compile(
    r"^(\s*)" + r"(?P<prefix>.+?)" + r"(\s+)(\{\{(?P<var>[^}]+)\}\})(\s*)$",
    re.DOTALL,
)


def _wrap_blocktrans_inner(inner: str, cleaned: str) -> str | None:
    """Wrap mixed static + ``{{ }}`` labels in blocktrans."""
    if _TRANS_RE.search(inner):
        return None

    m = _BLOCKTRANS_TAIL_RE.match(inner)
    if m:
        prefix = _normalize_ws(m.group("prefix"))
        if prefix != _normalize_ws(cleaned):
            return None
        var_expr = m.group("var").strip()
        alias = "value"
        if "|" not in var_expr and "." not in var_expr:
            alias = var_expr
        return (
            f"{{% blocktrans with {alias}={var_expr} %}}"
            f"{prefix} {{{{ {alias} }}}}"
            f"{{% endblocktrans %}}"
        )

    # ``{{ var }} ago`` / ``Updated: {{ var }} ago``
    m2 = re.match(
        r"^(\s*)(?P<prefix>.*?)(\{\{(?P<var>[^}]+)\}\})(\s+ago\s*)$",
        inner,
        re.DOTALL,
    )
    if m2:
        prefix = m2.group("prefix")
        var_expr = m2.group("var").strip()
        trail = m2.group(4)
        alias = "timesince" if "timesince" in var_expr else "value"
        return (
            f"{m2.group(1)}{{% blocktrans with {alias}={var_expr} %}}"
            f"{prefix}{{{{ {alias} }}}}{trail}"
            f"{{% endblocktrans %}}"
        )

    # ``Static ({{ count }})`` e.g. Helpful ({{ faq.helpful_count }})
    m3 = re.search(
        r"^(\s*(?:<[^>]+>\s*)*)(?P<prefix>[A-Za-z][^<{]*?)\(\s*\{\{(?P<var>[^}]+)\}\}\s*\)\s*$",
        inner,
        re.DOTALL,
    )
    if m3:
        prefix = m3.group("prefix").strip()
        var_expr = m3.group("var").strip()
        lead = m3.group(1) or ""
        alias = "count"
        return (
            f"{lead}{{% blocktrans with {alias}={var_expr} %}}"
            f"{prefix} ({{{{ {alias} }}}})"
            f"{{% endblocktrans %}}"
        )

    # ``Welcome to RunMyCampus, {{ name }}!``
    m4 = re.search(
        r"^(\s*)(?P<prefix>Welcome to RunMyCampus,\s*)\{\{(?P<var>[^}]+)\}\}(\s*!?\s*)$",
        inner,
        re.DOTALL,
    )
    if m4:
        var_expr = m4.group("var").strip()
        return (
            f"{m4.group(1)}{{% blocktrans with name={var_expr} %}}"
            f"Welcome to RunMyCampus, {{{{ name }}}}{m4.group(4)}"
            f"{{% endblocktrans %}}"
        )

    return None


def _element_on_line(text: str, tag: str, line_no: int) -> re.Match[str] | None:
    """Return the label element whose opening tag starts on *line_no* (1-indexed)."""
    lines = text.splitlines(keepends=True)
    if line_no < 1 or line_no > len(lines):
        return None
    offset = sum(len(lines[i]) for i in range(line_no - 1))
    line_end = offset + len(lines[line_no - 1])
    for m in _ELEMENT_RE.finditer(text):
        if m.group(1).lower() != tag.lower():
            continue
        start = m.start()
        if offset <= start < line_end:
            return m
    # Opening tag may start on previous line for wrapped elements.
    for m in _ELEMENT_RE.finditer(text):
        if m.group(1).lower() != tag.lower():
            continue
        if m.start() <= line_end and m.end() >= offset:
            return m
    return None


def _wrap_element_match(m: re.Match[str], cleaned: str) -> str | None:
    tag = m.group(1).lower()
    attrs = m.group(2) or ""
    inner = m.group(3)
    new_inner = _wrap_static_inner(inner, cleaned)
    if new_inner is None:
        new_inner = _wrap_blocktrans_inner(inner, cleaned)
    if new_inner is None:
        new_inner = _wrap_nested_static_parts(inner)
    if new_inner is None:
        return None
    return f"<{tag}{attrs}>{new_inner}</{tag}>"


def _wrap_nested_static_parts(inner: str) -> str | None:
    """Wrap static text segments inside nested markup (icon + label + muted span)."""
    if _TRANS_RE.search(inner):
        return None
    if "{{" in inner or "{%" in inner:
        return None
    parts = re.split(r"(<[^>]+>)", inner)
    changed = False
    out: list[str] = []
    for part in parts:
        if not part or part.startswith("<"):
            out.append(part)
            continue
        text = _normalize_ws(part)
        if not text or not re.search(r"[A-Za-z]{3,}", text):
            out.append(part)
            continue
        trans = '{% trans "' + _escape_trans_string(text) + '" %}'
        out.append(part.replace(part.strip(), trans, 1) if part.strip() == text else trans)
        changed = True
    return "".join(out) if changed else None


def _target_matches(tag: str, cleaned: str, targets: set[tuple[str, str]]) -> bool:
    if (tag, cleaned) in targets:
        return True
    for t, lbl in targets:
        if t != tag:
            continue
        if cleaned.startswith(lbl.rstrip("…")) or lbl.startswith(cleaned[: max(len(lbl), 1)]):
            return True
    return False


def patch_file(path: Path, targets: set[tuple[str, str]] | None = None) -> tuple[int, list[tuple[str, str]]]:
    """Return (wrapped_count, skipped_targets)."""
    text = path.read_text(encoding="utf-8", errors="replace")
    skipped: list[tuple[str, str]] = []
    wrapped = 0
    live_findings = scan_file(path) if targets is None else None

    if live_findings:
        replacements: list[tuple[int, int, str]] = []
        for f in live_findings:
            cleaned = f.get("cleaned") or f["text"]
            line_no = f.get("line")
            if not line_no:
                skipped.append((f["tag"], cleaned))
                continue
            m = _element_on_line(text, f["tag"], line_no)
            if not m:
                skipped.append((f["tag"], cleaned))
                continue
            inner_cleaned = _clean_inner(m.group(3))
            replacement = _wrap_element_match(m, inner_cleaned)
            if replacement is None:
                skipped.append((f["tag"], cleaned))
                continue
            replacements.append((m.start(), m.end(), replacement))
        for start, end, replacement in sorted(replacements, key=lambda x: x[0], reverse=True):
            text = text[:start] + replacement + text[end:]
            wrapped += 1
        if wrapped:
            text = _ensure_load_i18n(text)
            path.write_text(text, encoding="utf-8")
        return wrapped, skipped

    def repl(m: re.Match[str]) -> str:
        nonlocal wrapped
        tag = m.group(1).lower()
        inner = m.group(3)
        cleaned = _clean_inner(inner)
        if targets is not None and not _target_matches(tag, cleaned, targets):
            return m.group(0)
        replacement = _wrap_element_match(m, cleaned)
        if replacement is None:
            skipped.append((tag, cleaned))
            return m.group(0)
        wrapped += 1
        return replacement

    new_text = _ELEMENT_RE.sub(repl, text)
    if wrapped:
        new_text = _ensure_load_i18n(new_text)
        path.write_text(new_text, encoding="utf-8")
    return wrapped, skipped


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--write", action="store_true")
    parser.add_argument("--rescan-baseline", action="store_true")
    parser.add_argument("--all-current", action="store_true", help="Wrap every finding from a live scan (not baseline keys)")
    args = parser.parse_args()
    if not args.dry_run and not args.write:
        parser.error("Specify --dry-run or --write")

    if args.all_current:
        from scan_untranslated_template_text import scan as scan_all, _iter_template_files

        live = scan_all(_iter_template_files())
        by_file = {}
        for f in live:
            by_file.setdefault(f["path"], None)
    else:
        if not BASELINE_PATH.is_file():
            print("Baseline missing — run scan_untranslated_template_text.py first", file=sys.stderr)
            return 1
        baseline = json.loads(BASELINE_PATH.read_text(encoding="utf-8"))
        findings = baseline.get("findings") or []
        by_file = {}
        for f in findings:
            by_file.setdefault(f["path"], set()).add((f["tag"], f["text"]))

    total_wrapped = 0
    all_skipped: list[tuple[str, str, str]] = []
    files_touched = 0

    for rel in sorted(by_file.keys()):
        path = REPO_ROOT / rel.replace("/", "\\") if "\\" in rel else REPO_ROOT / rel
        targets = by_file[rel]
        if not path.is_file():
            print(f"  SKIP missing {rel}")
            continue
        if args.dry_run:
            text = path.read_text(encoding="utf-8", errors="replace")
            count = 0
            if args.all_current:
                file_findings = scan_file(path)
            else:
                file_findings = None
            for m in _ELEMENT_RE.finditer(text):
                cleaned = _clean_inner(m.group(3))
                tag = m.group(1).lower()
                if args.all_current:
                    ok = any(_finding_matches(tag, cleaned, f) for f in file_findings)
                else:
                    ok = _target_matches(tag, cleaned, targets)
                if ok and (_wrap_static_inner(m.group(3), cleaned) or _wrap_blocktrans_inner(m.group(3), cleaned)):
                    count += 1
            if count:
                print(f"  would wrap {count:4d}  {rel}")
                total_wrapped += count
                files_touched += 1
        else:
            n, skipped = patch_file(path, None if args.all_current else targets)
            if n:
                print(f"  wrapped {n:4d}  {rel}")
                total_wrapped += n
                files_touched += 1
            for tag, label in skipped:
                all_skipped.append((rel, tag, label))

    print(f"\n{'Would wrap' if args.dry_run else 'Wrapped'} {total_wrapped} labels in {files_touched} files")
    if all_skipped:
        print(f"Skipped {len(all_skipped)} dynamic/mixed labels (need manual blocktrans)")

    if args.write and args.rescan_baseline:
        import subprocess

        subprocess.check_call(
            [sys.executable, str(REPO_ROOT / "scripts" / "scan_untranslated_template_text.py")],
            cwd=str(REPO_ROOT),
        )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
