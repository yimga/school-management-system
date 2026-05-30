#!/usr/bin/env python3
"""Regression gate: luxury chrome is the platform default.

- OS-grade density (`data-rmc-os-grade`) must be opt-in only (localStorage on).
- Admin shell density must default to comfortable, not compact.
- Platform density bootstrap (`rmc-shell-polish.js`) must default to comfortable.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _read(rel: str) -> str:
    return (ROOT / rel).read_text(encoding="utf-8")


def verify_admin_quickaction(source: str) -> list[str]:
    errors: list[str] = []
    if re.search(
        r"classList\.contains\([\"']admin-manager-shell[\"']\)[\s\S]{0,400}"
        r"setAttribute\([\"']data-rmc-os-grade[\"'],\s*[\"']1[\"']\)",
        source,
    ):
        errors.append(
            "admin-quickaction.js auto-enables OS-grade for manager/admin shells "
            "(luxury baseline requires explicit opt-in)"
        )
    if re.search(
        r"data-rmc-admin-density[\"']\)\s*\|\|\s*[\"']compact[\"']",
        source,
    ):
        errors.append(
            "admin-quickaction.js defaults admin density to compact "
            "(luxury baseline requires comfortable)"
        )
    if 'localStorage.getItem("rmc-os-grade") === "on"' not in source:
        errors.append(
            "admin-quickaction.js must gate OS-grade on localStorage rmc-os-grade=on"
        )
    if 'html.setAttribute("data-rmc-admin-density", "comfortable")' not in source:
        errors.append(
            "admin-quickaction.js must set comfortable admin density when not compact"
        )
    return errors


def verify_shell_polish(source: str) -> list[str]:
    errors: list[str] = []
    if 'VALID[raw] ? raw : "comfortable"' not in source:
        errors.append("rmc-shell-polish.js must default platform density to comfortable")
    return errors


def verify_admin_base_site(source: str) -> list[str]:
    errors: list[str] = []
    if "data-rmc-admin-density', 'comfortable'" not in source.replace('"', "'"):
        if "data-rmc-admin-density', 'comfortable'" not in source:
            errors.append(
                "admin/base_site.html head bootstrap must SSR comfortable admin density"
            )
    if "removeAttribute('data-rmc-os-grade')" not in source:
        errors.append(
            "admin/base_site.html head bootstrap must clear OS-grade unless opted in"
        )
    return errors


def main() -> int:
    errors: list[str] = []
    errors.extend(verify_admin_quickaction(_read("static/js/_pages/admin-quickaction.js")))
    errors.extend(verify_shell_polish(_read("static/js/rmc-shell-polish.js")))
    errors.extend(verify_admin_base_site(_read("templates/admin/base_site.html")))

    if errors:
        print("LUXURY_BASELINE_DEFAULT_FAIL")
        for err in errors:
            print(f"  - {err}")
        return 1

    import subprocess

    leak = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "verify_template_comment_zero_leak.py")],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    if leak.returncode != 0:
        print(leak.stdout or leak.stderr or "verify_template_comment_zero_leak failed")
        return 1

    print("LUXURY_BASELINE_DEFAULT_PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
