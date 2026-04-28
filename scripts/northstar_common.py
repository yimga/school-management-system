"""
Shared helpers for North Star audit / kill-test / self-heal CLIs.

Keep this module importable without Django (SOT parsing + path checks only).
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
SOT_PATH = ROOT / "docs" / "RUNMYCAMPUS_SINGLE_EXECUTION_SOURCE_OF_TRUTH.md"

# North Star product slices referenced in execution prompts (15–24).
NORTHSTAR_SLICES: tuple[int, ...] = tuple(range(15, 25))

_STATUS_TAIL = re.compile(r"\):\*\*\s*\*\*([^*]+)\*\*")

# e.g. (North Star slice 15 — title, 2026-04-27):** **DONE**


def repo_root() -> Path:
    return ROOT


def parse_sot_north_star_slice_status(
    sot_text: str, *, slice_numbers: tuple[int, ...] = NORTHSTAR_SLICES
) -> dict[int, str | None]:
    """
    For each slice id, return the SOT keyword (e.g. DONE, PARTIAL) or None if not found.
    """
    out: dict[int, str | None] = {n: None for n in slice_numbers}
    for line in sot_text.splitlines():
        if "North Star slice " not in line:
            continue
        m = re.search(r"North Star slice (\d+)", line)
        if not m:
            continue
        n = int(m.group(1))
        if n not in out:
            continue
        st = _STATUS_TAIL.search(line)
        if not st:
            continue
        out[n] = (st.group(1) or "").strip().split()[0].upper()
    return out


def load_sot_text(path: Path = SOT_PATH) -> str:
    if not path.is_file():
        return ""
    return path.read_text(encoding="utf-8", errors="replace")


def count_slices_done(status: dict[int, str | None]) -> int:
    return sum(1 for n, s in status.items() if s == "DONE")


def run_script(
    rel: str,
    args: list[str] | None = None,
    *,
    timeout: int = 600,
) -> subprocess.CompletedProcess[str]:
    exe = sys.executable
    cmd = [exe, str(ROOT / rel)]
    if args:
        cmd.extend(args)
    return subprocess.run(
        cmd,
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
    )


def run_manage(*args: str, env: dict[str, str] | None = None, timeout: int = 900):
    exe = sys.executable
    cmd = [exe, str(ROOT / "manage.py"), *args]
    merged = dict(env) if env else None
    return subprocess.run(
        cmd,
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
        env=merged,
    )


def score_from_exit_ok(exit_code: int) -> int:
    return 5 if exit_code == 0 else 1


def path_exists(rel: str) -> bool:
    return (ROOT / rel).is_file()


def ensure_generated_dir() -> Path:
    d = ROOT / "docs" / "generated"
    d.mkdir(parents=True, exist_ok=True)
    return d


def json_dump(obj: Any, path: Path) -> None:
    import json

    path.write_text(
        json.dumps(obj, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
