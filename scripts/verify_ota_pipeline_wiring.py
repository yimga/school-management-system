#!/usr/bin/env python
"""Assert the cascading-OTA pipeline is still CONNECTED end to end.

Every piece of this pipeline can be present, import cleanly, pass its unit tests and
still deliver nothing, because the failure mode is a missing WIRE rather than broken
code. That is the same class ``scan_unregistered_middleware`` was built for — an
``EdgeAutosyncMiddleware`` that existed, compiled, had no unused imports, and was
registered in no ``MIDDLEWARE`` list, so the fallback written for a production failure
was dead during that failure.

The OTA pipeline has five such wires, and cutting any one of them is silent:

  1. **The operator must BUILD a manifest.** Without the ``generate_system_manifest``
     step in ``build.sh``, every box asks for a manifest, gets 503 ``no_manifest``, and
     never upgrades — while the deploy stays green and the boxes stay quiet.

  2. **The box image must build one too** (``deploy/selfhost/Dockerfile``), or the box
     has no idea what it currently is, so the first delta it computes starts from
     nothing.

  3. **The box must APPLY.** Without ``edge_apply_upgrade`` in the entrypoint, a box
     detects drift, reports it on the handshake, and waits forever for a hand that
     never arrives.

  4. **The routes must be MOUNTED** on the existing sync API. The whole design rests on
     reusing one approved network lane; a route that is defined but not included is an
     upgrade channel that never runs.

  5. **The routes must be PINNED as cloud paths.** ``CLOUD_SYNC_PATHS`` is what keeps a
     box from trying to serve them locally; an unpinned upgrade route resolves against
     the wrong host.

None of these is visible to a test that imports a module, and none is visible to the
reference-integrity family, because nothing is unresolvable — the code is simply never
reached. So this checks the wires themselves.

Deliberately a pure-text scan: stdlib only, no Django, no YAML parse, so it runs in the
deps-free boundary job next to the static scanners. NO baseline and NO allow-marker — a
disconnected pipeline is never intentional. An operator who wants no OTA sets
``RMC_OTA_ENABLED=0`` at runtime, which is a setting, not a missing wire.

Pass/fail gate (no finding-count baseline), like ``verify_ci_gate_wiring``.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


# Each wire: where it must appear, the token proving it, and what breaks without it.
REQUIRED_WIRES: tuple[dict[str, str], ...] = (
    {
        "wire": "operator-manifest-build",
        "path": "build.sh",
        "token": "generate_system_manifest",
        "breaks": "the cloud serves 503 no_manifest to every box; nothing in the fleet ever upgrades",
    },
    {
        "wire": "box-manifest-build",
        "path": "deploy/selfhost/Dockerfile",
        "token": "generate_system_manifest",
        "breaks": "the box cannot say what it currently is, so its first delta starts from nothing",
    },
    {
        "wire": "box-apply-step",
        "path": "deploy/selfhost/entrypoint.web.sh",
        "token": "edge_apply_upgrade",
        "breaks": "the box reports drift forever and never applies anything",
    },
    {
        "wire": "upgrade-routes-mounted",
        "path": "apps/api/urls.py",
        "token": "sync/upgrade/manifest/",
        "breaks": "the manifest endpoint is unreachable; the box has nothing to ask",
    },
    {
        "wire": "upgrade-chunk-mounted",
        "path": "apps/api/urls.py",
        "token": "sync/upgrade/chunk/",
        "breaks": "the box can see a delta but can never fetch the bytes",
    },
    {
        "wire": "upgrade-paths-pinned-cloud",
        "path": "apps/sync_engine/cloud_endpoints.py",
        "token": "sync/upgrade/manifest/",
        "breaks": "the box resolves the upgrade route against itself instead of the cloud",
    },
)

# The manifest build must not be allowed to fail quietly. `|| echo` on this step is what
# turned a broken manifest into a green deploy with a dead OTA system.
_SILENT_FAILURE_MARKERS = ("|| echo", "|| true", "|| :")


def _read(rel: str) -> str | None:
    path = ROOT / rel
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None


def find_broken_wires() -> list[dict[str, str]]:
    findings: list[dict[str, str]] = []
    for wire in REQUIRED_WIRES:
        source = _read(wire["path"])
        if source is None:
            findings.append({**wire, "kind": "file_missing"})
            continue
        if wire["token"] not in source:
            findings.append({**wire, "kind": "wire_cut"})
    return findings


def find_silent_manifest_build() -> list[dict[str, str]]:
    """The operator manifest build must be fatal, not a warning.

    Checked separately from the wires because the wire is present in this failure mode —
    the step is there, it just cannot fail. That is strictly worse than absence: absence
    is at least visible in the file.
    """
    source = _read("build.sh")
    if source is None:
        return []
    findings = []
    for line in source.splitlines():
        if "generate_system_manifest" not in line:
            continue
        if any(marker in line for marker in _SILENT_FAILURE_MARKERS):
            findings.append(
                {
                    "wire": "operator-manifest-build-is-fatal",
                    "path": "build.sh",
                    "token": line.strip()[:120],
                    "kind": "silent_failure",
                    "breaks": (
                        "a failed manifest build produces a GREEN deploy whose OTA system "
                        "is dead; every box gets 503 no_manifest and nothing reports it"
                    ),
                }
            )
    return findings


def _payload(findings: list[dict[str, str]]) -> dict[str, object]:
    return {
        "gate": "ota-pipeline-wiring",
        "wires_checked": len(REQUIRED_WIRES),
        "finding_count": len(findings),
        "findings": findings,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    findings = find_broken_wires() + find_silent_manifest_build()

    if args.json:
        print(json.dumps(_payload(findings), indent=2, sort_keys=True))
        return 1 if findings else 0

    print(
        f"OTA pipeline wiring: {len(REQUIRED_WIRES)} wire(s) checked, "
        f"{len(findings)} broken"
    )
    for f in findings:
        if f["kind"] == "file_missing":
            print(f"  MISSING FILE: {f['path']} — {f['breaks']}")
        elif f["kind"] == "silent_failure":
            print(f"  SILENT FAILURE: {f['path']} :: {f['token']}")
            print(f"      {f['breaks']}")
        else:
            print(f"  WIRE CUT: {f['wire']} — {f['token']!r} absent from {f['path']}")
            print(f"      {f['breaks']}")
    if findings:
        print(
            "\nThe OTA pipeline is disconnected. Every module still imports and every "
            "unit test still passes; nothing reaches a school. Re-wire it — or, to run "
            "deliberately without OTA, set RMC_OTA_ENABLED=0 (a setting, not a cut wire)."
        )
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
