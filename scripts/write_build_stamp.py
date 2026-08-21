#!/usr/bin/env python
"""Write ``.build-stamp.json`` so a built image can say what code it is running.

Render sets ``RENDER_GIT_COMMIT`` for free, so the hosted deploy has always been
able to answer ``/-/version/``. A self-hosted Docker appliance has no such
platform, nothing in ``deploy/`` ever set ``GIT_COMMIT``, and the runtime image
is not guaranteed to carry the ``git`` binary -- so the box reported
``commit_sha: unknown`` and nobody could tell what code it was running. That also
made ``resolve_deploy_commit_sha()`` permanently inert, which is the value the
post-deploy cache-buster uses to let a browser notice a stale shell.

Run at image build time (see ``deploy/selfhost/Dockerfile``)::

    python scripts/write_build_stamp.py

Sources, in order:

1. ``GIT_COMMIT`` / ``BUILD_TIME`` / ``ENVIRONMENT`` build args, when the
   operator or CI passes them.
2. ``.git`` in the build context, read as plain files (no ``git`` binary).
3. Nothing -- the stamp simply omits that key and the runtime falls back.

A malformed env var here falls back to ``.git``, which is the OPPOSITE of what
the runtime resolver does -- deliberately. At build time ``.git`` is ground truth
sitting right there and the arg is only a hint, so using it is strictly better
than stamping nothing. At runtime there is no ground truth to check against: the
env var is the deployer's declaration of what they shipped, and silently
answering with something else would turn a visible config error into a confident
wrong answer.

**This script never fails a build.** A stamp is a convenience: an image that
cannot name its commit is worse than one that can, but it is not broken, and
turning a missing ``.git`` into a failed build would be a far worse trade. Every
failure path prints a reason and exits 0.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
STAMP_PATH = REPO_ROOT / ".build-stamp.json"

_SHA_RE = re.compile(r"[0-9a-fA-F]{7,64}")


def _load_deploy_meta():
    """Import ``apps/siteconfig/deploy_meta.py`` by path.

    By path, not by package, so this runs during a Docker build with no Django
    settings configured and no app registry -- and so the git-reading logic has
    exactly one implementation shared with the runtime resolver.
    """
    path = REPO_ROOT / "apps" / "siteconfig" / "deploy_meta.py"
    spec = importlib.util.spec_from_file_location("_rmc_deploy_meta", path)
    if spec is None or spec.loader is None:
        return None
    module = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(module)
    except Exception as exc:  # noqa: BLE001 - a stamp is never worth a failed build
        print(f"[build-stamp] could not load deploy_meta ({exc!r}); git fallback off")
        return None
    return module


def resolve_commit(meta=None) -> str:
    # The same key list the runtime resolver uses, in the same order, so a stamp
    # can never disagree with the env var that would override it anyway. Render
    # sets RENDER_GIT_COMMIT during the build; the self-host Dockerfile passes
    # GIT_COMMIT as a build arg.
    keys = getattr(meta, "COMMIT_ENV_KEYS", None) or ("GIT_COMMIT",)
    for key in keys:
        declared = (os.environ.get(key) or "").strip()
        if not declared:
            continue
        if _SHA_RE.fullmatch(declared):
            return declared
        print(f"[build-stamp] {key} is not a sha ({len(declared)} chars); ignoring")
    if meta is None:
        return ""
    try:
        return meta.read_git_head_sha()
    except Exception as exc:  # noqa: BLE001 - see module docstring
        print(f"[build-stamp] reading .git failed ({exc!r})")
        return ""


def resolve_build_time() -> str:
    declared = (os.environ.get("BUILD_TIME") or "").strip()
    if declared:
        return declared
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def build_stamp() -> dict[str, str]:
    stamp = {"build_time": resolve_build_time()}
    commit = resolve_commit(_load_deploy_meta())
    if commit:
        stamp["commit_sha"] = commit
    environment = (os.environ.get("ENVIRONMENT") or "").strip()
    if environment:
        stamp["environment"] = environment
    return stamp


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--path",
        default=str(STAMP_PATH),
        help="Where to write the stamp (default: <repo root>/.build-stamp.json).",
    )
    parser.add_argument(
        "--print",
        action="store_true",
        dest="print_only",
        help="Print the stamp without writing it.",
    )
    args = parser.parse_args(argv)

    stamp = build_stamp()
    payload = json.dumps(stamp, indent=2, sort_keys=True) + "\n"

    if args.print_only:
        print(payload, end="")
        return 0

    try:
        Path(args.path).write_text(payload, encoding="utf-8")
    except OSError as exc:
        print(f"[build-stamp] could not write {args.path} ({exc}); continuing")
        return 0

    print(
        "[build-stamp] wrote {path}: commit_sha={sha} build_time={when}".format(
            path=args.path,
            sha=stamp.get("commit_sha", "(none)"),
            when=stamp["build_time"],
        )
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
