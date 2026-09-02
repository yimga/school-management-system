"""Verify the Unified Wizard Framework Playwright spec is DERIVED from the registry.

What this gate used to check, and why that was not enough
---------------------------------------------------------
The previous revision compared a hand-typed ``WIZARD_REGISTRY_KEYS`` array in
``tests/e2e/unified-wizard-framework.spec.js`` against the wizard JSONs on disk.
It was correct about the drift (24 typed vs 38 registered) and it had been
reporting that drift into a log nobody read, because the gate is not wired into
any workflow. But the deeper problem was that the array it policed was **never
iterated to exercise a wizard**. Its only two uses were a uniqueness check and
``expect(WIZARD_REGISTRY_KEYS).toHaveLength(23)`` — off by one against its own
24 entries — and the browser test named "lists every registered wizard" asserted
``count() > 0``.

So pasting the 14 missing keys in would have added ZERO coverage and re-armed the
same trap. The spec now DERIVES its list from the registry
(``tests/e2e/helpers/wizard-registry.js``), and this gate verifies the derivation
instead of policing a list.

What it checks now
------------------
1. The spec exists and does not re-introduce a hand-typed wizard-key array, or a
   ``toHaveLength(<int>)`` count assertion over the derived constants.
2. The spec actually requires the registry helper and binds its constants to
   calls on it.
3. ``describeRegistry()`` is EXECUTED under Node and diffed against this script's
   own independent walk of ``apps/setup_studio/wizards/*.json``. The JS
   derivation is verified, not trusted. Node absent => exit 2 (cannot verify),
   never a pass.
4. Every ``OPERATOR_INDEX_EXCLUSIONS`` entry names a registered operator-audience
   wizard and carries a non-blank reason — an unexplained absence is what let the
   old list rot, so it is not spellable.
5. Both wizard index templates emit ``data-wizard-key`` on their card anchors.
   The spec locates cards by that attribute; before this wave the attribute
   existed in the spec's comments and NOWHERE in the product, so every browser
   assertion in the file was matching zero elements.

Exit codes::

    0 — clean
    1 — drift / contract violation
    2 — cannot verify (spec missing / structurally unreadable / Node unavailable)
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SPEC_PATH = ROOT / "tests" / "e2e" / "unified-wizard-framework.spec.js"
HELPER_PATH = ROOT / "tests" / "e2e" / "helpers" / "wizard-registry.js"
WIZARDS_DIR = ROOT / "apps" / "setup_studio" / "wizards"
INDEX_TEMPLATES = (
    ROOT / "templates" / "setup_studio" / "operator_wizard_index.html",
    ROOT / "templates" / "setup_studio" / "tenant_wizard_index.html",
)

# The attribute the spec's card locator depends on.
CARD_ATTRIBUTE = "data-wizard-key"

# A `const <NAME> = [ "a", "b", ... ]` binding: the hand-typed shape this gate
# exists to keep out. A derived binding is `const NAME = wizardKeys();`.
_LITERAL_ARRAY_RE = re.compile(
    r"const\s+(?P<name>[A-Z][A-Z0-9_]*)\s*=\s*\[(?P<body>[^\]]*)\]",
    re.MULTILINE | re.DOTALL,
)
_WIZARD_KEY_STRING_RE = re.compile(r'"([a-z][a-z0-9_]{6,})"')
# `toHaveLength(23)` over the derived constants — the magic-number shape.
_MAGIC_LENGTH_RE = re.compile(
    r"expect\(\s*(?P<name>WIZARD_REGISTRY_KEYS|OPERATOR_INDEX_WIZARD_KEYS)\s*\)"
    r"\s*\.\s*toHaveLength\(\s*\d+\s*\)"
)


def _registry_from_disk() -> dict[str, list[str]]:
    """Walk the wizard JSONs exactly as ``load_wizard_registry`` does.

    Returns wizard_key -> sorted audience list. This is INDEPENDENT of the JS
    helper on purpose: the two are diffed against each other so neither can
    drift silently.
    """
    out: dict[str, list[str]] = {}
    if not WIZARDS_DIR.exists():
        return out
    for json_path in sorted(WIZARDS_DIR.glob("*.json")):
        if json_path.name.startswith("_"):
            continue
        try:
            raw = json.loads(json_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if raw.get("feature_flag_disabled") is True:
            continue
        key = raw.get("wizard_key")
        if not isinstance(key, str) or not key:
            continue
        audience = raw.get("audience")
        out[key] = sorted(str(a) for a in audience) if isinstance(audience, list) else []
    return out


def _describe_registry_via_node() -> tuple[dict | None, str]:
    """Execute the JS helper and return its ``describeRegistry()`` output."""
    node = shutil.which("node")
    if node is None:
        return None, "node executable not found on PATH"
    program = (
        "const m=require(process.argv[1]);"
        "process.stdout.write(JSON.stringify(m.describeRegistry()));"
    )
    try:
        proc = subprocess.run(  # noqa: S603 — fixed argv, no shell
            [node, "-e", program, str(HELPER_PATH)],
            capture_output=True,
            text=True,
            timeout=120,
            cwd=str(ROOT),
        )
    except (OSError, subprocess.SubprocessError) as exc:
        return None, f"could not run node: {exc}"
    if proc.returncode != 0:
        return None, f"node exited {proc.returncode}: {proc.stderr.strip()[:800]}"
    try:
        return json.loads(proc.stdout), ""
    except json.JSONDecodeError as exc:
        return None, f"describeRegistry() did not emit JSON: {exc}"


def _check_spec_shape(body: str, failures: list[str]) -> None:
    """The spec must derive, not declare."""
    if "./helpers/wizard-registry" not in body:
        failures.append(
            "spec does not require ./helpers/wizard-registry — its wizard list is "
            "not derived from the registry"
        )
    for name, expected_call in (
        ("WIZARD_REGISTRY_KEYS", "wizardKeys()"),
        ("OPERATOR_INDEX_WIZARD_KEYS", "operatorIndexKeys()"),
    ):
        if not re.search(rf"const\s+{name}\s*=\s*{re.escape(expected_call)}", body):
            failures.append(
                f"spec must bind {name} to {expected_call} from the registry helper"
            )

    for match in _LITERAL_ARRAY_RE.finditer(body):
        keys = _WIZARD_KEY_STRING_RE.findall(match.group("body"))
        if len(keys) >= 3:
            failures.append(
                f"spec re-introduces a hand-typed wizard-key array: "
                f"const {match.group('name')} = [{', '.join(keys[:3])}, ...] "
                f"({len(keys)} entries). Derive it from the registry instead."
            )

    magic = _MAGIC_LENGTH_RE.search(body)
    if magic:
        failures.append(
            f"spec asserts a hand-maintained count over {magic.group('name')} "
            f"({magic.group(0)}). Compare SETS against the registry so the failure "
            f"names the wizard, not two integers."
        )


def _check_templates(failures: list[str]) -> None:
    """The card attribute the spec locates by must exist in the product."""
    for template in INDEX_TEMPLATES:
        if not template.exists():
            failures.append(f"wizard index template missing: {template}")
            continue
        text = template.read_text(encoding="utf-8")
        anchors = re.findall(r"<a\b[^>]*\bclass=\"rmc-wz-card\b[^>]*>", text)
        anchors += re.findall(r"<a\b[^>]*\bclass=\"rmc-wizard-card\b[^>]*>", text)
        if not anchors:
            failures.append(
                f"{template.name}: no wizard card anchor found — the spec's "
                f"[{CARD_ATTRIBUTE}] locator has nothing to match"
            )
            continue
        for anchor in anchors:
            if CARD_ATTRIBUTE not in anchor:
                failures.append(
                    f"{template.name}: wizard card anchor does not emit "
                    f"{CARD_ATTRIBUTE} — the spec locates cards by that attribute, "
                    f"so every browser assertion in the spec would match 0 elements: "
                    f"{anchor[:120]}"
                )


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Verify the wizard Playwright spec derivation.")
    ap.add_argument(
        "--strict",
        action="store_true",
        help="accepted for backwards compatibility; this gate is always strict",
    )
    ap.parse_args(argv)

    print("== verify_wizard_playwright_spec_coverage ==")

    if not SPEC_PATH.exists():
        print(f"FAIL: spec file missing at {SPEC_PATH}")
        return 2
    if not HELPER_PATH.exists():
        print(f"FAIL: registry helper missing at {HELPER_PATH}")
        return 2

    disk = _registry_from_disk()
    if not disk:
        print(f"FAIL: no wizard JSONs discovered at {WIZARDS_DIR}")
        return 1

    described, node_error = _describe_registry_via_node()
    if described is None:
        print(f"CANNOT VERIFY: {node_error}")
        print(
            "  This gate proves the spec's JS derivation by RUNNING it. Without "
            "Node it cannot make that claim, so it reports 2 rather than passing."
        )
        return 2

    failures: list[str] = []

    # 1. The JS derivation must agree with an independent Python walk.
    js_keys = set(described.get("wizard_keys") or [])
    py_keys = set(disk)
    for key in sorted(py_keys - js_keys):
        failures.append(f"registry derivation missed a registered wizard: {key}")
    for key in sorted(js_keys - py_keys):
        failures.append(f"registry derivation invented a wizard the JSONs do not have: {key}")

    js_audience = described.get("audience_by_key") or {}
    for key in sorted(py_keys & js_keys):
        if sorted(js_audience.get(key) or []) != disk[key]:
            failures.append(
                f"audience mismatch for {key}: JS derivation says "
                f"{sorted(js_audience.get(key) or [])}, JSON says {disk[key]}"
            )

    py_operator = {k for k, aud in disk.items() if "operator" in aud}
    js_operator = set(described.get("operator_audience_keys") or [])
    for key in sorted(py_operator - js_operator):
        failures.append(f"operator-audience derivation missed: {key}")
    for key in sorted(js_operator - py_operator):
        failures.append(f"operator-audience derivation over-claimed: {key}")

    # 2. Exclusions must be real, operator-audience, and justified.
    exclusions = described.get("operator_index_exclusions") or {}
    for key, reason in sorted(exclusions.items()):
        if key not in py_keys:
            failures.append(
                f"OPERATOR_INDEX_EXCLUSIONS names '{key}', which is not a registered "
                f"wizard — the exclusion is stale"
            )
        elif key not in py_operator:
            failures.append(
                f"OPERATOR_INDEX_EXCLUSIONS names '{key}', whose audience is "
                f"{disk[key]} and never included 'operator' — excluding it hides "
                f"nothing and weakens the check"
            )
        if not str(reason or "").strip():
            failures.append(f"OPERATOR_INDEX_EXCLUSIONS['{key}'] carries no reason")

    expected_index = sorted(py_operator - set(exclusions))
    if sorted(described.get("operator_index_keys") or []) != expected_index:
        failures.append(
            "operatorIndexKeys() does not equal (operator audience - exclusions): "
            f"derived {sorted(described.get('operator_index_keys') or [])} "
            f"vs expected {expected_index}"
        )
    if not expected_index:
        failures.append(
            "no operator-audience wizard survives the exclusion list — the spec's "
            "operator index assertion would be vacuous"
        )

    # 3. The spec must derive rather than declare.
    _check_spec_shape(SPEC_PATH.read_text(encoding="utf-8"), failures)

    # 4. The product must emit the attribute the spec locates by.
    _check_templates(failures)

    if failures:
        print(f"FAIL: {len(failures)} finding(s):")
        for item in failures:
            print(f"  - {item}")
        return 1

    print(
        f"PASS: spec derives all {len(py_keys)} registered wizards from the registry; "
        f"{len(expected_index)} operator-index wizards asserted by key "
        f"({len(exclusions)} explicit exclusion(s))"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
