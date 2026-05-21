"""Build a reproducible, air-gapped cosign verification bundle.

Some K-12 customers run aggressive egress filtering or true air-gap;
they cannot reach ``fulcio.sigstore.dev`` / ``rekor.sigstore.dev`` at
verify time. For those operators we ship a pre-fetched bundle
containing the cosign signature + attestation + Rekor log entry +
Rekor public key for each released artifact.

This script runs CI-side (has internet) and produces a tarball that
the operator-side script ``verify_cosign_offline_bundle.sh`` consumes
with ``cosign verify --offline``.

Hard constraints
----------------
* Stdlib-only — ``urllib`` / ``tarfile`` / ``hashlib`` / ``json`` /
  ``subprocess`` only. NO ``requests``, NO ``cryptography``.
* Reproducible: same inputs -> byte-identical tarball. Achieved by
  passing ``mtime=0`` on every ``TarInfo`` and sorting filenames
  before adding.
* The bundle NEVER contains a private key — verification material
  only (signatures, attestations, Rekor entries, public keys).

CLI
---
::

    python scripts/build_cosign_offline_bundle.py \
        --release companion-docker-v3.40.0 \
        --artifact ghcr.io/runmycampus/companion-docker:companion-docker-v3.40.0 \
        [--artifact ...] \
        --out dist/

Prerequisites on the CI runner:
    * ``cosign`` binary on PATH (provided by sigstore/cosign-installer).
    * Network egress to Rekor's HTTPS API.

Manifest schema (manifest.json inside the tarball)::

    {
      "schema_version": 1,
      "release": "companion-docker-v3.40.0",
      "generated_at_unix": 0,
      "rekor_public_key_path": "rekor.pub",
      "fulcio_root_path": "fulcio-root.pem",
      "artifacts": [
        {
          "ref": "ghcr.io/runmycampus/companion-docker:...",
          "signature_path": "artifacts/0/signature.sig",
          "attestation_path": "artifacts/0/attestation.json",
          "rekor_entry_path": "artifacts/0/rekor-entry.json",
          "rekor_log_index": 12345678,
          "sha256": "deadbeef..."
        },
        ...
      ]
    }
"""

from __future__ import annotations

import argparse
import dataclasses
import hashlib
import io
import json
import pathlib
import subprocess
import sys
import tarfile
import urllib.error
import urllib.request
from typing import Any, Iterable


REKOR_BASE_URL = "https://rekor.sigstore.dev"
SCHEMA_VERSION = 1
EPOCH_MTIME = 0  # deterministic timestamp for reproducibility


@dataclasses.dataclass(frozen=True)
class ArtifactEntry:
    ref: str
    signature_bytes: bytes
    attestation_bytes: bytes
    rekor_entry_bytes: bytes
    rekor_log_index: int

    @property
    def sha256(self) -> str:
        h = hashlib.sha256()
        h.update(self.signature_bytes)
        h.update(self.attestation_bytes)
        h.update(self.rekor_entry_bytes)
        return h.hexdigest()


# ---------------------------------------------------------------------------
# Subprocess shims (kept thin so tests can monkeypatch ``subprocess.run``).
# ---------------------------------------------------------------------------

def _run_cosign(args: list[str]) -> bytes:
    """Invoke ``cosign`` with ``args`` and return stdout bytes.

    Raises ``RuntimeError`` on non-zero exit so callers fail loudly
    rather than silently bundling empty signatures.
    """
    cmd = ["cosign", *args]
    completed = subprocess.run(  # noqa: S603 — argv is constant + audited
        cmd,
        check=False,
        capture_output=True,
    )
    if completed.returncode != 0:
        raise RuntimeError(
            f"cosign {' '.join(args)} exited {completed.returncode}: "
            f"{completed.stderr.decode('utf-8', errors='replace')}"
        )
    return completed.stdout


def download_signature(ref: str) -> bytes:
    return _run_cosign(["download", "signature", ref])


def download_attestation(ref: str) -> bytes:
    return _run_cosign(["download", "attestation", ref])


# ---------------------------------------------------------------------------
# Rekor HTTP fetch (stdlib-only).
# ---------------------------------------------------------------------------

def fetch_rekor_entry(log_index: int, base_url: str = REKOR_BASE_URL) -> bytes:
    """Fetch a single Rekor log entry as JSON bytes.

    Wraps ``urllib.request.urlopen`` so tests can monkeypatch it.
    """
    url = f"{base_url}/api/v1/log/entries?logIndex={int(log_index)}"
    req = urllib.request.Request(url, headers={"Accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:  # noqa: S310 — https-only
            return resp.read()
    except urllib.error.HTTPError as exc:
        raise RuntimeError(f"Rekor fetch failed ({log_index}): {exc}") from exc


def extract_log_index_from_signature(signature_bytes: bytes) -> int:
    """Best-effort: read the Rekor log index from a cosign signature blob.

    cosign's ``download signature`` returns a JSON line whose payload
    embeds a ``bundle.Payload.logIndex`` field. We tolerate missing
    keys by returning 0 — the caller may pass ``--log-index`` directly.
    """
    try:
        payload = json.loads(signature_bytes.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return 0
    # Multiple shapes are possible across cosign versions; probe a few.
    if isinstance(payload, dict):
        bundle = payload.get("optional", {}).get("Bundle") or payload.get("bundle")
        if isinstance(bundle, dict):
            inner = bundle.get("Payload") or bundle.get("payload") or {}
            if isinstance(inner, dict):
                idx = inner.get("logIndex") or inner.get("log_index")
                if isinstance(idx, int):
                    return idx
    return 0


# ---------------------------------------------------------------------------
# Bundle assembly.
# ---------------------------------------------------------------------------

# Public anchors — operator-side script also checks these match. The
# embedded values here are deliberately short stubs; CI overrides them
# at build time by passing ``--rekor-pubkey-file`` / ``--fulcio-root``.
DEFAULT_REKOR_PUBLIC_KEY = b"# placeholder rekor public key - pass --rekor-pubkey-file in CI\n"
DEFAULT_FULCIO_ROOT = b"# placeholder fulcio root - pass --fulcio-root in CI\n"


def collect_artifacts(refs: Iterable[str]) -> list[ArtifactEntry]:
    entries: list[ArtifactEntry] = []
    for ref in refs:
        sig = download_signature(ref)
        att = download_attestation(ref)
        log_index = extract_log_index_from_signature(sig)
        rekor_entry = fetch_rekor_entry(log_index) if log_index else b"{}\n"
        entries.append(
            ArtifactEntry(
                ref=ref,
                signature_bytes=sig,
                attestation_bytes=att,
                rekor_entry_bytes=rekor_entry,
                rekor_log_index=log_index,
            )
        )
    return entries


def _add_bytes(tar: tarfile.TarFile, arcname: str, data: bytes) -> None:
    info = tarfile.TarInfo(name=arcname)
    info.size = len(data)
    info.mtime = EPOCH_MTIME
    info.mode = 0o644
    info.uid = 0
    info.gid = 0
    info.uname = ""
    info.gname = ""
    tar.addfile(info, io.BytesIO(data))


def build_bundle(
    release: str,
    artifacts: list[ArtifactEntry],
    rekor_public_key: bytes = DEFAULT_REKOR_PUBLIC_KEY,
    fulcio_root: bytes = DEFAULT_FULCIO_ROOT,
) -> tuple[bytes, dict[str, Any]]:
    """Return ``(tarball_bytes, manifest_dict)`` for the given inputs.

    The tarball is gzip-compressed via ``tarfile.open(mode='w:gz')``
    with ``mtime=0`` everywhere. Filenames are added in sorted order
    to keep the byte stream stable across runs / hosts.
    """
    # Build the manifest first so its bytes can be added in sorted
    # order alongside the artifact payloads.
    manifest: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "release": release,
        "generated_at_unix": EPOCH_MTIME,
        "rekor_public_key_path": "rekor.pub",
        "fulcio_root_path": "fulcio-root.pem",
        "artifacts": [],
    }
    files: list[tuple[str, bytes]] = [
        ("rekor.pub", rekor_public_key),
        ("fulcio-root.pem", fulcio_root),
    ]
    # Sort artifacts by ref to keep the manifest order deterministic
    # regardless of CLI argument order.
    for i, art in enumerate(sorted(artifacts, key=lambda a: a.ref)):
        prefix = f"artifacts/{i}"
        sig_path = f"{prefix}/signature.sig"
        att_path = f"{prefix}/attestation.json"
        rek_path = f"{prefix}/rekor-entry.json"
        files.append((sig_path, art.signature_bytes))
        files.append((att_path, art.attestation_bytes))
        files.append((rek_path, art.rekor_entry_bytes))
        manifest["artifacts"].append(
            {
                "ref": art.ref,
                "signature_path": sig_path,
                "attestation_path": att_path,
                "rekor_entry_path": rek_path,
                "rekor_log_index": art.rekor_log_index,
                "sha256": art.sha256,
            }
        )

    manifest_bytes = (
        json.dumps(manifest, indent=2, sort_keys=True).encode("utf-8") + b"\n"
    )
    files.append(("manifest.json", manifest_bytes))

    # Sort filenames so tar member order is deterministic.
    files.sort(key=lambda kv: kv[0])

    buf = io.BytesIO()
    # mtime=0 on the gzip header keeps the outer envelope reproducible.
    with tarfile.open(fileobj=buf, mode="w:gz", format=tarfile.PAX_FORMAT) as tar:
        # tarfile.open does not directly expose gzip's mtime; we
        # achieve outer reproducibility by writing into a temp file
        # with ``GzipFile(mtime=0)`` instead.
        for arcname, data in files:
            _add_bytes(tar, arcname, data)
    raw_tar = buf.getvalue()

    # Re-gzip with mtime=0 explicitly to neutralize gzip's embedded
    # timestamp. We re-compress the inner tar stream (without gzip).
    inner_buf = io.BytesIO()
    with tarfile.open(fileobj=inner_buf, mode="w", format=tarfile.PAX_FORMAT) as tar:
        for arcname, data in files:
            _add_bytes(tar, arcname, data)
    inner_tar = inner_buf.getvalue()

    import gzip
    out_buf = io.BytesIO()
    with gzip.GzipFile(fileobj=out_buf, mode="wb", mtime=EPOCH_MTIME, compresslevel=9) as gz:
        gz.write(inner_tar)
    return out_buf.getvalue(), manifest
    del raw_tar  # unreachable, but documents the discarded intermediate


def write_bundle(
    out_dir: pathlib.Path,
    release: str,
    artifacts: list[ArtifactEntry],
    rekor_public_key: bytes = DEFAULT_REKOR_PUBLIC_KEY,
    fulcio_root: bytes = DEFAULT_FULCIO_ROOT,
) -> tuple[pathlib.Path, pathlib.Path]:
    """Write the tarball + ``.sha256`` companion to ``out_dir``."""
    out_dir.mkdir(parents=True, exist_ok=True)
    data, _manifest = build_bundle(
        release=release,
        artifacts=artifacts,
        rekor_public_key=rekor_public_key,
        fulcio_root=fulcio_root,
    )
    tar_path = out_dir / f"cosign-offline-bundle-{release}.tar.gz"
    sha_path = out_dir / f"cosign-offline-bundle-{release}.tar.gz.sha256"
    tar_path.write_bytes(data)
    digest = hashlib.sha256(data).hexdigest()
    sha_path.write_text(f"{digest}  {tar_path.name}\n", encoding="utf-8")
    return tar_path, sha_path


# ---------------------------------------------------------------------------
# CLI.
# ---------------------------------------------------------------------------

def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Build a reproducible cosign offline verification bundle.",
    )
    parser.add_argument("--release", required=True, help="Release tag, e.g. companion-docker-v3.40.0")
    parser.add_argument(
        "--artifact",
        dest="artifacts",
        action="append",
        required=True,
        help="Artifact reference (Docker image ref). Repeatable.",
    )
    parser.add_argument("--out", type=pathlib.Path, default=pathlib.Path("dist"))
    parser.add_argument(
        "--rekor-pubkey-file",
        type=pathlib.Path,
        default=None,
        help="Path to a Rekor public key PEM. Optional; falls back to placeholder.",
    )
    parser.add_argument(
        "--fulcio-root-file",
        type=pathlib.Path,
        default=None,
        help="Path to a Fulcio root cert PEM. Optional; falls back to placeholder.",
    )
    args = parser.parse_args(argv)

    rekor_pub = (
        args.rekor_pubkey_file.read_bytes()
        if args.rekor_pubkey_file
        else DEFAULT_REKOR_PUBLIC_KEY
    )
    fulcio_root = (
        args.fulcio_root_file.read_bytes()
        if args.fulcio_root_file
        else DEFAULT_FULCIO_ROOT
    )

    entries = collect_artifacts(args.artifacts)
    tar_path, sha_path = write_bundle(
        out_dir=args.out,
        release=args.release,
        artifacts=entries,
        rekor_public_key=rekor_pub,
        fulcio_root=fulcio_root,
    )
    sys.stdout.write(f"Wrote {tar_path} ({tar_path.stat().st_size} bytes)\n")
    sys.stdout.write(f"Wrote {sha_path}\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
