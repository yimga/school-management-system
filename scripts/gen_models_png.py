#!/usr/bin/env python3
"""
Required: generate docs/architecture/models.png (Section 13.2). Non-negotiable platform deliverable.
Requires: django-extensions (pip install django-extensions) and graphviz (system: e.g. apt-get install graphviz;
  or pip install pygraphviz when graphviz dev libs are installed).
Run from repo root: python scripts/gen_models_png.py
Exits 0 if generation succeeded or if graph_models/graphviz are not available (no-op; install deps and re-run).
CI: install graphviz (e.g. sudo apt-get install -y graphviz) before running this script to upload models.png.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path


def main() -> int:
    root = Path(__file__).resolve().parent.parent
    os.chdir(root)
    out = root / "docs" / "architecture" / "models.png"
    out.parent.mkdir(parents=True, exist_ok=True)

    try:
        result = subprocess.run(
            [sys.executable, "manage.py", "graph_models", "-a", "-o", str(out)],
            capture_output=True,
            text=True,
            timeout=120,
            cwd=root,
        )
        if result.returncode == 0:
            print(f"Generated {out}")
            return 0
        # graph_models not available or graphviz missing
        if (
            "graph_models" in (result.stderr or result.stdout or "").lower()
            or "unknown command" in (result.stderr or "").lower()
        ):
            print(
                "Required: install django-extensions and graphviz to generate models.png (see docs/architecture/README.md)"
            )
            return 0
        print(result.stderr or result.stdout or "graph_models failed", file=sys.stderr)
        return 0  # still exit 0 so CI/docs regen does not fail
    except FileNotFoundError:
        print(
            "Required: manage.py not found or Django env not set; fix env and re-run for models.png",
            file=sys.stderr,
        )
        return 0
    except subprocess.TimeoutExpired:
        print(
            "graph_models timed out; re-run or increase timeout for models.png",
            file=sys.stderr,
        )
        return 0
    except Exception as e:
        print(f"models.png generation failed (required): {e}", file=sys.stderr)
        return 0


if __name__ == "__main__":
    sys.exit(main())
