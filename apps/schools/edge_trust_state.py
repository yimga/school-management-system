"""What this box remembers about its own certificate authority.

THE PROBLEM THIS SOLVES. The box CA private key is the only artefact on an edge box
that cannot be rebuilt from configuration. Everything else -- the leaf, the
Caddyfile, ALLOWED_HOSTS, the origins -- is derived and rebuilds in a minute. Lose
``ca.key`` and every device that trusted this box has to be physically revisited.

The dangerous shape is not losing it. It is losing it **silently**. A wiped
``edgetlsdata`` volume, a rebuilt appliance, a ``docker compose down -v``, a restore
onto fresh storage -- and then somebody helpfully runs ``--issue-selfsigned``, which
cheerfully mints a brand new CA and reports success. Nothing anywhere says "that CA
you spent an afternoon installing on thirty devices is now worthless". The box looks
healthy from every angle it can see itself from.

So the box writes down which CA it has, in a place that does NOT share a failure
domain with the certificates: a different named volume. On the next issue it compares.
A CA that appears where a different one was recorded is not a fresh install, it is a
loss -- and the tooling refuses to proceed rather than making it permanent.

Deliberately file-based and stdlib-only, NOT a Django model:

* it has to work at container start, before and independently of the database, which
  is exactly when ``--ensure`` runs;
* a box that cannot reach its database must still be prevented from minting a second
  CA, and a model would make the guard fail open at the worst moment;
* and it must live in a volume the certificate directory does not, which a table in
  the same Postgres volume would not guarantee.

Nothing in here is secret. A fingerprint, a subject and some timestamps are all
public properties of a certificate that is handed to every client that connects.
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from typing import Any

#: Default lives under MEDIA_ROOT, which selfhost mounts as `mediadata` -- a
#: DIFFERENT named volume from `edgetlsdata`. That separation is the entire point:
#: state that shares a volume with the certificates disappears in the same accident.
DEFAULT_STATE_DIR = "/app/media/.rmc-edge"
ENV_STATE_DIR = "RMC_EDGE_STATE_DIR"
ANCHOR_FILENAME = "trust-anchor.json"
SCHEMA = 1

#: Outcomes of comparing the CA on disk against the one this box remembers.
ANCHOR_FIRST = "first"        # nothing recorded; this is the box's first CA
ANCHOR_SAME = "same"          # matches what we recorded -- the ordinary case
ANCHOR_CHANGED = "changed"    # a DIFFERENT CA is on disk; devices are stranded
ANCHOR_MISSING = "missing"    # we recorded a CA and there is none on disk
ANCHOR_UNKNOWN = "unknown"    # no CA on disk and none recorded


def state_dir(environ: dict[str, str] | None = None) -> str:
    env = os.environ if environ is None else environ
    return str(env.get(ENV_STATE_DIR, "") or "").strip() or DEFAULT_STATE_DIR


def anchor_path(environ: dict[str, str] | None = None) -> str:
    return os.path.join(state_dir(environ), ANCHOR_FILENAME)


def _now(now: Any = None) -> str:
    return (now or datetime.now(timezone.utc)).isoformat()


def load_state(environ: dict[str, str] | None = None) -> dict[str, Any]:
    """Read the recorded state. Never raises -- an unreadable file is "nothing yet".

    A corrupt or missing file must not stop a box booting, but it also must not be
    mistaken for "this box has never had a CA": that reading is what would let a
    second CA be minted. Callers get ``readable`` so they can tell the difference,
    and :func:`anchor_findings` reports an unreadable file rather than passing it.
    """
    path = anchor_path(environ)
    if not os.path.exists(path):
        return {"schema": SCHEMA, "active": None, "history": [], "readable": True}
    try:
        with open(path, encoding="utf-8") as handle:
            data = json.load(handle)
    except (OSError, ValueError) as exc:
        return {
            "schema": SCHEMA,
            "active": None,
            "history": [],
            "readable": False,
            "error": str(exc),
        }
    if not isinstance(data, dict):
        return {"schema": SCHEMA, "active": None, "history": [], "readable": False,
                "error": "not a JSON object"}
    data.setdefault("active", None)
    data.setdefault("history", [])
    data.setdefault("schema", SCHEMA)
    data["readable"] = True
    return data


def save_state(state: dict[str, Any], environ: dict[str, str] | None = None) -> tuple[bool, str]:
    """Write the state atomically. Returns ``(ok, error)`` and never raises.

    Atomic because a box loses power mid-write often enough to matter: a truncated
    anchor file reads as "no CA recorded", which is precisely the state that would
    permit a second CA.
    """
    directory = state_dir(environ)
    path = anchor_path(environ)
    payload = {k: v for k, v in state.items() if k != "readable"}
    try:
        os.makedirs(directory, exist_ok=True)
        tmp = path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2, sort_keys=True)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp, path)
    except OSError as exc:
        return False, f"cannot write {path}: {exc}"
    return True, ""


def compare(ca_facts: Any, environ: dict[str, str] | None = None) -> dict[str, Any]:
    """Compare the CA on disk against the one this box remembers."""
    state = load_state(environ)
    active = state.get("active") or None
    recorded = (active or {}).get("fingerprint") or ""
    present = getattr(ca_facts, "fingerprint", "") or ""
    exists = bool(getattr(ca_facts, "exists", False)) and bool(present)

    if not exists and not recorded:
        status = ANCHOR_UNKNOWN
    elif not exists:
        status = ANCHOR_MISSING
    elif not recorded:
        status = ANCHOR_FIRST
    elif present == recorded:
        status = ANCHOR_SAME
    else:
        status = ANCHOR_CHANGED
    return {
        "status": status,
        "recorded": active,
        "present_fingerprint": present,
        "readable": bool(state.get("readable", True)),
        "path": anchor_path(environ),
        "state": state,
    }


def record(
    ca_facts: Any,
    environ: dict[str, str] | None = None,
    now: Any = None,
) -> dict[str, Any]:
    """Record the CA currently on disk as this box's trust anchor.

    Records the PREVIOUS anchor into history rather than overwriting it. A box that
    has replaced its CA has stranded devices, and the fingerprint of the CA those
    devices still trust is exactly what somebody will need in order to work out what
    happened.
    """
    present = getattr(ca_facts, "fingerprint", "") or ""
    if not present:
        return {"ok": False, "error": "no CA fingerprint to record"}

    verdict = compare(ca_facts, environ)
    state = verdict["state"]
    active = state.get("active") or None
    stamp = _now(now)

    if active and active.get("fingerprint") == present:
        active["last_seen"] = stamp
    else:
        if active:
            active["retired_at"] = stamp
            state.setdefault("history", []).append(active)
        active = {
            "fingerprint": present,
            "subject": getattr(ca_facts, "subject", "") or "",
            "not_before": getattr(ca_facts, "not_before", "") or "",
            "not_after": getattr(ca_facts, "not_after", "") or "",
            "first_seen": stamp,
            "last_seen": stamp,
            "exported_at": None,
            "export_verified_at": None,
            "export_destination": "",
        }
    state["active"] = active
    ok, error = save_state(state, environ)
    return {"ok": ok, "error": error, "anchor": active, "status": verdict["status"]}


def record_export(
    fingerprint: str,
    destination: str,
    verified: bool,
    environ: dict[str, str] | None = None,
    now: Any = None,
) -> dict[str, Any]:
    """Note that the active CA has been backed up, and whether the backup was read back.

    ``verified`` means the bundle was re-imported into a scratch directory and the CA
    inside it matched. An unverified backup is a belief, not a backup -- the failure
    mode is a wrong passphrase or a truncated copy, and both are discovered years
    later at the exact moment the backup is needed.
    """
    state = load_state(environ)
    active = state.get("active") or None
    if not active or active.get("fingerprint") != fingerprint:
        return {"ok": False, "error": "the active trust anchor is not the one exported"}
    stamp = _now(now)
    active["exported_at"] = stamp
    active["export_destination"] = str(destination or "")
    active["export_verified_at"] = stamp if verified else None
    state["active"] = active
    ok, error = save_state(state, environ)
    return {"ok": ok, "error": error, "anchor": active}


def new_ca_allowed(ca_facts: Any, environ: dict[str, str] | None = None) -> tuple[bool, str]:
    """May a brand-new CA be minted right now? ``(allowed, reason if not)``.

    This is the guard on the one action in the whole runbook that cannot be undone.
    """
    verdict = compare(ca_facts, environ)
    if not verdict["readable"]:
        return False, (
            f"this box's trust-anchor record at {verdict['path']} cannot be read, so "
            "it is not possible to tell whether this box has already had a CA. "
            "Minting one now would strand every device that trusted the old one. "
            "Restore the record, or pass --force-new-ca if you are certain this box "
            "has never issued a certificate."
        )
    if verdict["status"] == ANCHOR_MISSING:
        recorded = verdict["recorded"] or {}
        return False, (
            "this box has issued a CA before -- fingerprint "
            f"{recorded.get('fingerprint', '?')}, first seen "
            f"{recorded.get('first_seen', '?')} -- and there is no CA on disk now. "
            "The certificate volume has been lost or replaced. Minting a new CA here "
            "strands every device that installed the old one, and there is no remedy "
            "but visiting each device. RESTORE FIRST: `edge_tls --import-ca "
            "<bundle>`, then issue. Use --force-new-ca only if the backup is gone and "
            "you accept re-installing on every device."
        )
    return True, ""


def anchor_findings(
    ca_facts: Any,
    environ: dict[str, str] | None = None,
) -> list[tuple[str, str]]:
    """Standing report on the one artefact that cannot be regenerated."""
    verdict = compare(ca_facts, environ)
    status = verdict["status"]
    findings: list[tuple[str, str]] = []

    if not verdict["readable"]:
        findings.append((
            "fail",
            f"This box's trust-anchor record ({verdict['path']}) is unreadable. Until "
            "it is repaired the box cannot tell a first install from a lost CA, and "
            "the guard that stops a second CA being minted cannot do its job.",
        ))
        return findings

    if status == ANCHOR_UNKNOWN:
        return findings  # no CA and none expected; other checks cover a missing cert

    if status == ANCHOR_MISSING:
        recorded = verdict["recorded"] or {}
        findings.append((
            "fail",
            "This box has issued a CA before (fingerprint "
            f"{recorded.get('fingerprint', '?')}) and there is no CA on disk now. The "
            "certificate volume has been lost or replaced. RESTORE the backup before "
            "issuing anything: minting a new CA here strands every device that "
            "installed the old one.",
        ))
        return findings

    if status == ANCHOR_CHANGED:
        recorded = verdict["recorded"] or {}
        findings.append((
            "fail",
            "The CA on this box is NOT the one it recorded. Devices trust "
            f"{recorded.get('fingerprint', '?')}; the box now holds "
            f"{verdict['present_fingerprint']}. Every device that installed the old CA "
            "will reject this box until it installs the new one. If this was not "
            "deliberate, restore the original bundle with --import-ca --force and "
            "reissue; the devices then need nothing.",
        ))
        return findings

    active = verdict["recorded"] or {}
    if status == ANCHOR_FIRST:
        findings.append((
            "warn",
            "A CA is on disk but this box has not recorded it yet. Run `edge_tls "
            "--issue-selfsigned` or `edge_bootstrap` to record it, so the box can "
            "tell a future replacement from a first install.",
        ))
        return findings

    if not active.get("exported_at"):
        findings.append((
            "fail",
            "The box CA has never been backed up. It is the ONLY artefact here that "
            "cannot be rebuilt from configuration -- lose it and every device that "
            "trusted this box has to be physically revisited. Back it up before you "
            "install it anywhere: `edge_bootstrap` does it, or `edge_tls --export-ca "
            "/tmp/box-ca-bundle.p12` with RMC_EDGE_TLS_CA_PASSPHRASE set.",
        ))
    elif not active.get("export_verified_at"):
        findings.append((
            "warn",
            f"The box CA was exported ({active.get('exported_at')}) but the bundle was "
            "never read back, so nothing has confirmed the passphrase is right or the "
            "copy is complete. An unverified backup is a belief. `edge_bootstrap` "
            "re-imports it into a scratch directory and checks the CA inside matches.",
        ))
    else:
        findings.append((
            "ok",
            "The box CA is recorded and its backup has been read back and verified "
            f"({active.get('export_verified_at')}). Keep the bundle and its passphrase "
            "off the box, and stored apart from each other.",
        ))
    return findings
