"""
Build and merge Django gettext catalogs without requiring GNU xgettext/msguniq on PATH.

Scans Python (AST) and HTML/Django templates (regex) for common translation patterns,
then merges new msgids into locale/<lang>/LC_MESSAGES/django.po using polib.

Use: python manage.py sync_i18n_catalog [--compile] [--dry-run]
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

import polib

# Calls we treat as translatable string sources (first string positional).
_GETTEXT_NAMES = frozenset(
    {
        "_",
        "gettext",
        "gettext_lazy",
        "ugettext",
        "ugettext_lazy",
        "ngettext",
        "pgettext",
        "npgettext",
    }
)

_SKIP_DIR_NAMES = frozenset(
    {
        "__pycache__",
        ".git",
        ".venv",
        "venv",
        "node_modules",
        ".pytest_cache",
        ".ruff_cache",
        "htmlcov",
        "dist",
        "build",
        ".mypy_cache",
        "vendor",
    }
)

_TRANS_DOUBLE = re.compile(r"\{%\s*trans\s+\"([^\"]+)\"", re.MULTILINE)
_TRANS_SINGLE = re.compile(r"\{%\s*trans\s+\'([^\']+)\'", re.MULTILINE)
_BLOCKTRANS = re.compile(
    r"\{%\s*blocktrans\b[^%]*%\}(.*?)\{%\s*endblocktrans\s*%\}",
    re.DOTALL | re.IGNORECASE,
)
# {{ _("...") }} or {% verbatim %} not matched inside verbatim — rare
_VAR_UNDERSCORE = re.compile(r"\{\{\s*_\(\s*\"([^\"]+)\"\s*\)\s*\}\}")
_VAR_UNDERSCORE_SQ = re.compile(r"\{\{\s*_\(\s*\'([^\']+)\'\s*\)\s*\}\}")

# JavaScript (django gettext / future catalog); keep patterns narrow to avoid noise.
_JS_GETTEXT_DQ = re.compile(r"(?:gettext|django\.gettext)\(\s*\"([^\"\\]*(?:\\.[^\"\\]*)*)\"")
_JS_GETTEXT_SQ = re.compile(r"(?:gettext|django\.gettext)\(\s*\'([^\'\\]*(?:\\.[^\'\\]*)*)\'")
_JS_NGETTEXT = re.compile(
    r"(?:ngettext|django\.ngettext)\(\s*\"([^\"]+)\"\s*,\s*\"([^\"]+)\""
)


def _should_skip_dir(path: Path) -> bool:
    return path.name in _SKIP_DIR_NAMES


def _iter_files(base: Path, suffixes: tuple[str, ...]) -> list[Path]:
    out: list[Path] = []
    if not base.is_dir():
        return out
    for path in base.rglob("*"):
        if not path.is_file():
            continue
        if any(part in _SKIP_DIR_NAMES for part in path.parts):
            continue
        if path.suffix not in suffixes:
            continue
        try:
            if path.stat().st_size > 2_000_000:
                continue
        except OSError:
            continue
        out.append(path)
    return out


def _func_call_name(node: ast.Call) -> str | None:
    f = node.func
    if isinstance(f, ast.Name):
        return f.id
    if isinstance(f, ast.Attribute):
        return f.attr
    return None


def _string_arg(node: ast.expr) -> str | None:
    if isinstance(node, ast.Constant) and isinstance(node.value, str) and node.value:
        return node.value
    return None


def _collect_from_py(path: Path) -> set[str]:
    found: set[str] = set()
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return found
    if "/tests/" in str(path).replace("\\", "/") or path.name.startswith("test_"):
        return found
    try:
        tree = ast.parse(text, filename=str(path))
    except SyntaxError:
        return found

    class V(ast.NodeVisitor):
        def visit_Call(self, node: ast.Call) -> None:
            name = _func_call_name(node)
            if not name or not node.args:
                return
            if name in _GETTEXT_NAMES or name == "_":
                if name == "ngettext" and len(node.args) >= 2:
                    for i in range(2):
                        s = _string_arg(node.args[i])
                        if s:
                            found.add(s)
                elif name == "pgettext" and len(node.args) >= 2:
                    s = _string_arg(node.args[1])
                    if s:
                        found.add(s)
                elif name == "npgettext" and len(node.args) >= 3:
                    for i in range(1, 3):
                        s = _string_arg(node.args[i])
                        if s:
                            found.add(s)
                else:
                    s = _string_arg(node.args[0])
                    if s:
                        found.add(s)
            self.generic_visit(node)

    V().visit(tree)
    return found


def _normalize_blocktrans_inner(raw: str) -> str:
    lines = [ln.strip() for ln in raw.splitlines() if ln.strip()]
    return " ".join(lines)


def _collect_from_template(path: Path) -> set[str]:
    found: set[str] = set()
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return found
    for m in _TRANS_DOUBLE.finditer(text):
        found.add(m.group(1))
    for m in _TRANS_SINGLE.finditer(text):
        found.add(m.group(1))
    for m in _BLOCKTRANS.finditer(text):
        inner = _normalize_blocktrans_inner(m.group(1))
        if inner and not inner.startswith("{%"):
            if re.search(r"[A-Za-z\u00c0-\u024f]", inner):
                found.add(inner)
    for m in _VAR_UNDERSCORE.finditer(text):
        found.add(m.group(1))
    for m in _VAR_UNDERSCORE_SQ.finditer(text):
        found.add(m.group(1))
    return found


def _collect_from_js(path: Path) -> set[str]:
    found: set[str] = set()
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return found
    for m in _JS_GETTEXT_DQ.finditer(text):
        found.add(m.group(1).replace('\\"', '"').replace("\\n", "\n"))
    for m in _JS_GETTEXT_SQ.finditer(text):
        found.add(m.group(1).replace("\\'", "'").replace("\\n", "\n"))
    for m in _JS_NGETTEXT.finditer(text):
        found.add(m.group(1))
        found.add(m.group(2))
    return found


def collect_translatable_strings(base_dir: Path) -> set[str]:
    """
    Scan templates/, apps/*/templates/, apps/**/*.py, config/**/*.py, services/**/*.py,
    and static/**/*.js (gettext/ngettext patterns; vendor paths skipped).
    """
    strings: set[str] = set()
    templates_root = base_dir / "templates"
    if templates_root.is_dir():
        for p in _iter_files(templates_root, (".html", ".txt")):
            strings |= _collect_from_template(p)

    apps_dir = base_dir / "apps"
    if apps_dir.is_dir():
        for app in apps_dir.iterdir():
            if not app.is_dir():
                continue
            tpl = app / "templates"
            if tpl.is_dir():
                for p in _iter_files(tpl, (".html", ".txt")):
                    strings |= _collect_from_template(p)
            for p in _iter_files(app, (".py",)):
                strings |= _collect_from_py(p)

    config_dir = base_dir / "config"
    if config_dir.is_dir():
        for p in _iter_files(config_dir, (".py",)):
            strings |= _collect_from_py(p)

    services_dir = base_dir / "services"
    if services_dir.is_dir():
        for p in _iter_files(services_dir, (".py",)):
            strings |= _collect_from_py(p)

    static_dir = base_dir / "static"
    if static_dir.is_dir():
        for p in _iter_files(static_dir, (".js",)):
            strings |= _collect_from_js(p)

    # Drop noise / oversized
    return {s for s in strings if s and len(s) < 5000 and not s.isspace()}


def _default_po_metadata(lang: str) -> dict[str, str]:
    return {
        "Project-Id-Version": "RunMyCampus",
        "Report-Msgid-Bugs-To": "",
        "POT-Creation-Date": "",
        "PO-Revision-Date": "",
        "Last-Translator": "",
        "Language-Team": lang,
        "Language": lang,
        "MIME-Version": "1.0",
        "Content-Type": "text/plain; charset=UTF-8",
        "Content-Transfer-Encoding": "8bit",
        "Plural-Forms": (
            "nplurals=1; plural=0;"
            if lang in ("en", "pid")
            else "nplurals=2; plural=(n != 1);"
        ),
    }


def merge_locale_catalogs(
    *,
    base_dir: Path,
    languages: list[tuple[str, str]],
    discovered: set[str],
    dry_run: bool = False,
    compile_mo: bool = False,
    prune_stale: bool = False,
) -> tuple[dict[str, int], dict[str, int]]:
    """
    Merge discovered msgids into locale/<code>/LC_MESSAGES/django.po.
    Returns (added_per_locale, pruned_per_locale). When prune_stale, drops entries whose
    msgid is not in discovered (preserves header msgid "").
    """
    locale_root = base_dir / "locale"
    added: dict[str, int] = {}
    pruned: dict[str, int] = {}
    keep = set(discovered)

    for code, _name in languages:
        lc_dir = locale_root / code / "LC_MESSAGES"
        po_path = lc_dir / "django.po"
        mo_path = lc_dir / "django.mo"

        if po_path.exists():
            po = polib.pofile(str(po_path))
        else:
            if not dry_run:
                lc_dir.mkdir(parents=True, exist_ok=True)
            po = polib.POFile()
            po.metadata = _default_po_metadata(code)

        n_pruned = 0
        if prune_stale:
            for entry in po:
                if entry.msgid and entry.msgid not in keep:
                    n_pruned += 1
            if not dry_run:
                kept_entries: list[polib.POEntry] = [
                    e
                    for e in po
                    if (not e.msgid) or (e.msgid in keep)
                ]
                po[:] = kept_entries
        pruned[code] = n_pruned

        existing = {e.msgid for e in po if e.msgid}
        n_new = 0
        for msgid in sorted(discovered):
            if msgid in existing:
                continue
            msgstr = msgid if code == "en" else ""
            po.append(polib.POEntry(msgid=msgid, msgstr=msgstr))
            existing.add(msgid)
            n_new += 1

        added[code] = n_new
        if dry_run:
            continue
        po.save(str(po_path))
        if compile_mo and mo_path:
            po.save_as_mofile(str(mo_path))

    return added, pruned


def run_sync(
    *,
    base_dir: Path,
    languages: list[tuple[str, str]],
    dry_run: bool = False,
    compile_mo: bool = False,
    prune_stale: bool = False,
) -> tuple[set[str], dict[str, int], dict[str, int]]:
    discovered = collect_translatable_strings(base_dir)
    added, pruned = merge_locale_catalogs(
        base_dir=base_dir,
        languages=languages,
        discovered=discovered,
        dry_run=dry_run,
        compile_mo=compile_mo,
        prune_stale=prune_stale,
    )
    return discovered, added, pruned


def verify_en_catalog_against_codebase(base_dir: Path) -> tuple[set[str], set[str]]:
    """
    Compare scanned strings to locale/en/LC_MESSAGES/django.po.
    Returns (missing_from_po, stale_in_po). ``stale_in_po`` excludes the header entry msgid "".
    """
    discovered = collect_translatable_strings(base_dir)
    po_path = base_dir / "locale" / "en" / "LC_MESSAGES" / "django.po"
    if not po_path.is_file():
        return discovered, set()
    po = polib.pofile(str(po_path))
    in_po = {e.msgid for e in po if e.msgid}
    missing = discovered - in_po
    stale = in_po - discovered - {""}
    return missing, stale
