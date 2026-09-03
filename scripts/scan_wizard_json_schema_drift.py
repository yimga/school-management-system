#!/usr/bin/env python
"""scan_wizard_json_schema_drift.py — zero-tolerance gate (baseline 0).

Validates every wizard JSON file against the documented schema invariants.
Mirrors the architectural-boundaries.yml pattern: exits 1 on any drift.

Invariants enforced (per docs/plans/UNIFIED_WIZARD_FRAMEWORK_IMPLEMENTATION_DETAIL.md §2):
* wizard_key matches ``^[a-z][a-z0-9_]*$``
* version >= 1
* audience non-empty list, values in known set
* steps non-empty list, max 8 steps
* each step has key + input_type
* input_type in known set
* branches and next_step_resolver mutually exclusive
* options_resolver / next_step_resolver / persistence.writer use ``module::callable`` format
* label_token is REACHABLE BY A TRANSLATOR -- it is a msgid in a shipped
  catalog, or it is listed in var/wizard-label-token-baseline.json with a
  written reason. See _label_token_error for why the old spelling rule was
  exactly backwards.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
WIZARDS_DIR = REPO_ROOT / "apps" / "setup_studio" / "wizards"

_VALID_INPUT_TYPES = {
    "single_choice", "multi_choice", "text", "long_text", "number", "decimal",
    "boolean", "file_upload", "image_upload", "color_picker", "domain_input",
    "structured_form", "draw_on_map", "csv_mapping", "rich_select",
    "ranked_list", "key_value_pairs", "datetime", "duration",
}
_VALID_AUDIENCES = {"operator", "tenant_admin", "teacher", "parent", "student", "staff"}

_WIZARD_KEY_RE = re.compile(r"^[a-z][a-z0-9_]*$")
_STEP_KEY_RE = re.compile(r"^[a-z][a-z0-9_]*$")
_TOKEN_PREFIX_RE = re.compile(r"^wizards\.")
_MSGID_RE = re.compile(r'^msgid "((?:[^"\\\\]|\\\\.)*)"', re.MULTILINE)

LABEL_BASELINE_PATH = REPO_ROOT / "var" / "wizard-label-token-baseline.json"


def _catalog_msgids() -> set[str]:
    """Every msgid a translator can see, across all shipped catalogs.

    Reachability, not translatedness: whether a given locale has actually
    filled the msgstr in is a separate question from whether the string is
    exposed to translators at all. This gate asks the second one.
    """
    seen: set[str] = set()
    for po in sorted((REPO_ROOT / "locale").glob("*/LC_MESSAGES/django.po")):
        try:
            text = po.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        seen |= set(_MSGID_RE.findall(text))
    return seen


_CACHE: dict = {}


def _label_token_error(wizard_key: str, token: object) -> str | None:
    """A wizard label passes if a translator can actually reach it.

    The rule this replaced required the token to START WITH "wizards.", which
    is a fact about the spelling and not about whether anyone can translate it.
    Measured against the shipped catalogs: ZERO wizards.* msgids exist in any of
    the 20 of them. humanize_wizard_token calls gettext(token) first, gets the
    token back unchanged, and falls through to title-casing the last slug
    segment -- so all 37 tokenised labels render English ("Academic Year Setup")
    on every locale, forever, with nothing for a translator to translate.

    Meanwhile the single wizard the old rule FLAGGED, mfa_setup, carries
    "Set up two-factor authentication" -- which IS a msgid in the catalog, and
    is therefore the only wizard label the i18n pipeline can reach at all.
    Tokenising it to make the gate green would have made the label LESS
    translatable: the definition of satisfying a gate's letter while damaging
    the thing it was written to protect.

    Whether wizard labels SHOULD be wizards.* tokens emitted into the catalog by
    sync_i18n_catalog, or real English msgids as mfa_setup uses, is an i18n
    architecture decision that belongs to the operator. This gate does not pick;
    it refuses to let the choice go unrecorded.
    """
    if not isinstance(token, str) or not token:
        return f"{wizard_key}: label_token missing or not a string"
    if "msgids" not in _CACHE:
        _CACHE["msgids"] = _catalog_msgids()
    if token in _CACHE["msgids"]:
        return None
    if "baseline" not in _CACHE:
        _CACHE["baseline"] = _load_label_baseline()
    listed = {e.get("label_token") for e in _CACHE["baseline"].get("unreachable", [])}
    if token in listed:
        return None
    return (
        f"{wizard_key}: label_token {token!r} is not a msgid in any shipped "
        f"catalog and is not listed in {LABEL_BASELINE_PATH.name} -- no "
        f"translator can reach it, so it renders English on every locale"
    )


def _icon_rule_active() -> bool:
    if "icon_rendered" not in _CACHE:
        _CACHE["icon_rendered"] = _icon_class_is_rendered()
    return bool(_CACHE["icon_rendered"])


def _load_label_baseline() -> dict:
    try:
        return json.loads(LABEL_BASELINE_PATH.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def _icon_class_is_rendered() -> bool:
    """Does any template actually put icon_class on the page?

    Measured 2026-09-03: no. icon_class is parsed into the Wizard dataclass and
    copied into two payloads (wizard_ai, wizard_analytics), and reaches no page.
    The convention it was policing names .rmc-icon-* classes that are defined in
    NO stylesheet in this repository. So the rule made exactly one wizard fail
    for spelling a class name differently from 37 others, where all 38 name
    classes that do not exist and nobody ever sees -- the definition of
    satisfying a gate's letter.

    The rule is not deleted, it is DORMANT: the moment a template renders
    icon_class this returns True and the naming convention is enforced again.
    """
    templates = REPO_ROOT / "templates"
    if not templates.is_dir():
        return False
    for path in templates.rglob("*.html"):
        try:
            if "icon_class" in path.read_text(encoding="utf-8", errors="replace"):
                return True
        except OSError:
            continue
    return False
_DOTTED_PATH_RE = re.compile(r"^apps\.[a-z_.]+::[a-z_]+$")
_ICON_RE = re.compile(r"^rmc-icon-[a-z-]+$")


def scan_file(path: Path) -> list[str]:
    errors: list[str] = []

    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return [f"{path.name}: cannot parse: {exc}"]

    if not isinstance(data, dict):
        return [f"{path.name}: top-level must be object"]

    wizard_key = data.get("wizard_key")
    if not isinstance(wizard_key, str) or not _WIZARD_KEY_RE.match(wizard_key):
        errors.append(f"{path.name}: wizard_key {wizard_key!r} does not match pattern")
        return errors

    if path.stem != wizard_key:
        errors.append(f"{path.name}: filename does not match wizard_key {wizard_key!r}")

    version = data.get("version")
    if not isinstance(version, int) or version < 1:
        errors.append(f"{wizard_key}: version must be integer >= 1")

    audience = data.get("audience")
    if not isinstance(audience, list) or not audience:
        errors.append(f"{wizard_key}: audience must be non-empty list")
    else:
        for a in audience:
            if a not in _VALID_AUDIENCES:
                errors.append(f"{wizard_key}: invalid audience {a!r}")

    label_error = _label_token_error(wizard_key, data.get("label_token"))
    if label_error:
        errors.append(label_error)

    icon = data.get("icon_class")
    if isinstance(icon, str) and _icon_rule_active() and not _ICON_RE.match(icon):
        errors.append(f"{wizard_key}: icon_class {icon!r} should match ^rmc-icon-[a-z-]+$")

    em = data.get("estimated_minutes")
    if not isinstance(em, int) or em < 1 or em > 60:
        errors.append(f"{wizard_key}: estimated_minutes must be integer in 1..60")

    steps = data.get("steps")
    if not isinstance(steps, list) or not steps:
        errors.append(f"{wizard_key}: steps must be non-empty list")
        return errors
    if len(steps) > 8:
        errors.append(f"{wizard_key}: max 8 steps per wizard ({len(steps)} found)")

    step_keys_seen: set[str] = set()
    for i, step in enumerate(steps):
        if not isinstance(step, dict):
            errors.append(f"{wizard_key}.[step #{i}]: not an object")
            continue
        sk = step.get("key")
        if not isinstance(sk, str) or not _STEP_KEY_RE.match(sk):
            errors.append(f"{wizard_key}.[step #{i}]: invalid step key {sk!r}")
            continue
        if sk in step_keys_seen:
            errors.append(f"{wizard_key}.{sk}: duplicate step key")
        step_keys_seen.add(sk)

        it = step.get("input_type")
        if it not in _VALID_INPUT_TYPES:
            errors.append(f"{wizard_key}.{sk}: invalid input_type {it!r}")

        has_branches = bool(step.get("branches"))
        has_resolver = bool(step.get("next_step_resolver"))
        if has_branches and has_resolver:
            errors.append(f"{wizard_key}.{sk}: branches AND next_step_resolver both set")

        for fname in ("options_resolver", "next_step_resolver"):
            val = step.get(fname)
            if val is not None and not _DOTTED_PATH_RE.match(str(val)):
                errors.append(f"{wizard_key}.{sk}.{fname}: invalid dotted path {val!r}")

        persistence = step.get("persistence") or {}
        if isinstance(persistence, dict):
            writer = persistence.get("writer")
            if writer is not None and not _DOTTED_PATH_RE.match(str(writer)):
                errors.append(f"{wizard_key}.{sk}.persistence.writer: invalid dotted path {writer!r}")

        fields = step.get("fields") or []
        for fld in fields:
            if not isinstance(fld, dict):
                errors.append(f"{wizard_key}.{sk}.fields: entry is not object")
                continue
            fn = fld.get("name")
            if not isinstance(fn, str) or not _STEP_KEY_RE.match(fn):
                errors.append(f"{wizard_key}.{sk}.fields: invalid field name {fn!r}")

    return errors


def main(argv: list[str]) -> int:
    print("== scan_wizard_json_schema_drift (baseline 0) ==")
    all_errors: list[str] = []
    for path in sorted(WIZARDS_DIR.glob("*.json")):
        if path.name.startswith("_"):
            continue
        all_errors.extend(scan_file(path))

    # Ratchet, same contract as var/companion-server-contract-baseline.json: the
    # list may only shrink. A label that becomes reachable must leave the file,
    # or the backlog decays into a number nobody rereads; an entry with no reason
    # is not a decision, it is a silence.
    baseline = _load_label_baseline()
    unreachable = baseline.get("unreachable", [])
    if "msgids" not in _CACHE:
        _CACHE["msgids"] = _catalog_msgids()
    for entry in unreachable:
        token = entry.get("label_token")
        if token in _CACHE["msgids"]:
            all_errors.append(
                f"{entry.get('wizard_key')}: label_token {token!r} is now a real "
                f"msgid -- delete this entry from {LABEL_BASELINE_PATH.name}"
            )
        if not str(entry.get("reason") or "").strip():
            all_errors.append(
                f"{entry.get('wizard_key')}: baseline entry carries no reason"
            )

    if unreachable:
        print(
            f"  NOTE {len(unreachable)} wizard label(s) are unreachable by i18n and "
            f"render English on every locale; see {LABEL_BASELINE_PATH.name}"
        )
    if not _icon_rule_active():
        print(
            "  NOTE icon_class reaches no template, and no .rmc-icon-* class is "
            "defined in any stylesheet; its naming rule stays dormant until "
            "something renders the field"
        )

    if all_errors:
        print(f"\nFAILED — {len(all_errors)} schema drift finding(s):")
        for e in all_errors:
            print(f"  - {e}")
        return 1
    print(f"\nscan_wizard_json_schema_drift: PASS (0 findings)")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
