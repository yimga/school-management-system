#!/usr/bin/env python3
"""Studio OS 10X consolidated all-wave smoke.

Asserts the 280-target program is fully scaffolded:
  Wave 1 — 56 sub-targets shipped with runtime/tests (see smoke_studio_os_10x_w1.py)
  Wave 2 — 14 subdivisions in seed + 56 wave-2 surface contracts
  Wave 3 — 14 subdivisions + 56 wave-3 surface contracts
  Wave 4 — 14 subdivisions + 56 wave-4 surface contracts
  Wave 5 — 14 subdivisions + 56 wave-5 surface contracts

Plus cross-cutting closure: register schema valid, CI workflow gate present.
"""
from __future__ import annotations

import json
import logging
import os
import sys
from pathlib import Path

logging.disable(logging.CRITICAL)

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

PASS = 0
FAIL: list[str] = []


def _ok(label: str) -> None:
    global PASS
    PASS += 1
    print(f"  OK   {label}")


def _bad(label: str, detail: str = "") -> None:
    FAIL.append(f"{label}: {detail}" if detail else label)
    print(f"  FAIL {label}: {detail}")


def assert_wave_1_completion() -> None:
    print("\n[Wave 1] full completion — invoking smoke_studio_os_10x_w1")
    import subprocess
    r = subprocess.run(
        [sys.executable, str(REPO / "scripts" / "smoke_studio_os_10x_w1.py")],
        capture_output=True, text=True, cwd=REPO,
    )
    if r.returncode == 0 and "STUDIO_OS_10X_W1_OK" in (r.stdout or ""):
        _ok("Wave 1 child smoke STUDIO_OS_10X_W1_OK")
    else:
        _bad("Wave 1 child smoke", (r.stderr or r.stdout or "no_output")[-200:])


def assert_w2_w5_subdivisions() -> None:
    print("\n[Waves 2-5] 48 subdivisions seeded in COUNTRY_LOCALIZATION")
    from apps.siteconfig._seed_country_localization import COUNTRY_LOCALIZATION as CL
    waves = {
        "W2": ["MX-CHH", "MX-TAB", "MX-VER", "MX-MOR", "MX-QUE", "MX-COA", "MX-DGO", "MX-AGU", "MX-NAY", "MX-COL", "MX-CAM", "MX-YUC"],
        "W3": ["MX-BCS", "MX-ZAC", "MX-TLA", "BR-MA", "BR-PI", "BR-AL", "BR-SE", "BR-PB", "BR-RN", "BR-AP", "BR-RR", "BR-RO"],
        "W4": ["BR-AC", "BR-TO", "BR-MT", "BR-MS", "ZA-LP", "ZA-NW", "NG-BY", "NG-RV", "NG-KW", "NG-OS", "NG-EK", "NG-PL"],
        "W5": ["KR-32", "KR-33", "KR-34", "KR-35", "KR-36", "KR-37", "KR-38", "KR-39", "KR-40", "JP-36", "JP-41", "JP-42"],
    }
    total = 0
    for wave, keys in waves.items():
        missing = [k for k in keys if k not in CL]
        if missing:
            _bad(f"{wave} subdivisions", f"missing {missing}")
        else:
            _ok(f"{wave}: 12 subdivisions present")
            total += len(keys)
    print(f"  total seeded across W2-W5: {total}/48")
    print(f"  COUNTRY_LOCALIZATION keys: {len(CL)}")


def assert_w2_w5_surface_registries() -> None:
    print("\n[Waves 2-5] 4 pillar registries × 56 surfaces each = 224 contracts")
    from apps.integrations_marketplace import studio_os_10x_w2_w5_operator_ui as op
    from apps.integrations_marketplace import studio_os_10x_w2_w5_marketplace as mp
    from apps.api import studio_os_10x_w2_w5_oneroster as orx
    from apps.governance.turbo import studio_os_10x_w2_w5_governance as govx

    for name, mod in (("operator_ui", op), ("marketplace", mp), ("oneroster", orx), ("governance", govx)):
        rows = mod.list_surfaces()
        if len(rows) != 56:
            _bad(f"{name} surface count", f"got {len(rows)}, expected 56")
            continue
        by_wave: dict[int, int] = {}
        for r in rows:
            by_wave[r["wave"]] = by_wave.get(r["wave"], 0) + 1
        if by_wave != {2: 14, 3: 14, 4: 14, 5: 14}:
            _bad(f"{name} wave distribution", str(by_wave))
            continue
        # Verify each wave has at least one surface that returns a sane envelope
        for w in (2, 3, 4, 5):
            slug = [r["slug"] for r in rows if r["wave"] == w][0]
            env = mod.call_surface(slug)
            if env.get("surface") == slug and env.get("status") == "scaffold_registered" and env.get("wave") == w:
                pass
            else:
                _bad(f"{name} W{w} envelope", str(env))
                continue
        _ok(f"{name}: 56 surfaces (14 per wave) + envelopes verified")


def assert_register_full_closure() -> None:
    print("\n[Register] all items DONE (or EXTERNAL_BLOCKED with documented reason)")
    path = REPO / "docs" / "generated" / "studio_os_10x_completion_register.json"
    if not path.is_file():
        _bad("register file", "missing")
        return
    register = json.loads(path.read_text(encoding="utf-8"))
    items = register.get("items") or []
    counts: dict[str, int] = {}
    for item in items:
        counts[item.get("status", "?")] = counts.get(item.get("status", "?"), 0) + 1
    if counts.get("NOT_DONE", 0) == 0 and counts.get("IN_PROGRESS", 0) == 0:
        _ok(f"register fully closed: counts={counts}")
    else:
        _bad("register closure", f"counts={counts}")


def assert_ci_workflow_gate() -> None:
    print("\n[CI] workflow gate present in architectural-boundaries.yml")
    path = REPO / ".github" / "workflows" / "architectural-boundaries.yml"
    if not path.is_file():
        _bad("ci yaml", "missing")
        return
    text = path.read_text(encoding="utf-8")
    if "studio-os-10x-completion:" in text and "smoke_studio_os_10x_w1.py" in text:
        _ok("ci job studio-os-10x-completion wired")
    else:
        _bad("ci job", "studio-os-10x-completion gate not found")


def main() -> int:
    print("STUDIO_OS_10X ALL-WAVES smoke — 280-target program closure")
    assert_wave_1_completion()
    assert_w2_w5_subdivisions()
    assert_w2_w5_surface_registries()
    assert_register_full_closure()
    assert_ci_workflow_gate()
    total = PASS + len(FAIL)
    print(f"\nSUMMARY: {PASS}/{total} pass, {len(FAIL)} fail")
    if FAIL:
        for line in FAIL[:20]:
            print(f"  - {line}")
        return 1
    print("STUDIO_OS_10X_ALL_WAVES_OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
