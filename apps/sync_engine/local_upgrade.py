"""``LocalRuntimeUpgradeManager`` — apply an upgrade on a box without ever bricking it.

THE SHAPE OF THE PROBLEM. A school appliance has no operator standing next to it. Whatever
this module does at 09:41 on a Tuesday is what the school lives with until somebody drives
out there, so the design question is not "how do we apply an update" — that part is
trivial — it is "what is the worst state a half-finished update can leave, and how do we
make that state unreachable".

THE SEQUENCE, AND WHY EACH STEP IS BEFORE THE NEXT.

  1. **drain**    — hold the sync rail and let in-flight cycles finish. A bundle applying
                    while templates change underneath it is the one race worth paying for.
  2. **stage**    — every byte lands in an isolated directory. The running tree is not
                    touched, so an abort here costs nothing at all.
  3. **verify**   — re-hash every staged file against the manifest. THIS is the step that
                    makes the rest safe: a truncated download, a corrupted chunk and a
                    tampered file are all indistinguishable from a good one afterwards,
                    and all three are caught here, before promotion.
  4. **precheck** — the migration plan is examined and, where the database supports
                    transactional DDL, actually executed inside a transaction that is then
                    rolled back. A migration that cannot apply is found now rather than
                    half-applied later.
  5. **activate** — only now does the running tree change, and only through per-file
                    ``os.replace`` (atomic on both POSIX and Windows) with the previous
                    bytes copied into the release's ``rollback/`` set first.
  6. **health**   — the box must answer its own ``/health/`` within
                    ``RMC_OTA_HEALTH_TIMEOUT_SECONDS`` (default 60). It does not, the
                    rollback set goes back and the box returns to the manifest it was
                    serving.

WHAT THIS DOES NOT PRETEND TO DO. Python that is already imported stays imported: swapping
a ``.py`` file under a running interpreter changes nothing until the process restarts. So
the ``assets`` lane (templates, static, locale — everything Django re-reads per request or
per collectstatic) genuinely takes effect immediately, and the ``full`` lane is honest
about needing a worker reload, which it requests and then verifies through the health
gate. Where the deployment is not laid out for a symlink swap — the ordinary
``COPY . .`` image is not — ``full`` stages, verifies, prechecks, records, and reports
``activation="deferred"``. It does not claim a swap it did not perform.

DEFAULT OFF. ``RMC_OTA_AUTO_APPLY`` is ``off`` unless an operator sets it. An appliance
that rewrites its own code unattended is a decision a school makes, not one a default
makes for them.
"""
from __future__ import annotations

import logging
import os
import shutil
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

from django.conf import settings

from apps.sync_engine import upgrade_delta, upgrade_lock, upgrade_runtime
from apps.sync_engine.system_manifest import (
    ASSET_CATEGORIES,
    STATIC_ASSET,
    SystemManifestGenerator,
    load_manifest,
    manifest_path,
    verify_tree,
)

logger = logging.getLogger(__name__)

MODE_ASSETS = "assets"
MODE_FULL = "full"
MODE_OFF = "off"

_CHUNK_BYTES = 1024 * 1024  # magic-number-allow: 1 MiB transfer chunk
_DEFAULT_HEALTH_TIMEOUT = 60  # magic-number-allow: health gate budget (seconds)
_DEFAULT_HEALTH_POLL = 2.0  # magic-number-allow: health poll interval (seconds)
_DEFAULT_DRAIN_TIMEOUT = 60  # magic-number-allow: drain budget (seconds)
_DEFAULT_STAGING_DIRNAME = ".rmc_ota_staging"
_ROLLBACK_DIRNAME = "rollback"
_MAX_ATTEMPTS_PER_FILE = 3  # magic-number-allow: chunk attempts before a file is failed
# One line of an exception is enough to say WHICH migration refused; the full traceback is
# already in the logs and in EdgeDeploymentHistory.error.
_REFUSAL_DETAIL_MAX_CHARS = 120  # magic-number-allow: excerpt of a refusal in a log line


def _current_migration_heads() -> dict:
    """Per-app migration heads as the DATABASE has them right now.

    ``schema_guard.local_migration_heads`` reads the applied graph, which is the right
    source here — the manifest's file-derived heads answer a different question ("what
    does this tree contain") and would name a migration that has not run.
    """
    try:
        from apps.api.sync_services import entity_app_labels
        from apps.sync_engine.schema_guard import local_migration_heads

        return dict(local_migration_heads(set(entity_app_labels().values())))
    except Exception:  # noqa: BLE001 - no floor is recorded rather than a wrong one
        logger.debug("ota: could not read migration heads", exc_info=True)
        return {}


class UpgradeAborted(RuntimeError):
    """A gate refused. The running tree is unchanged or has been restored."""


def _setting(name, default):
    return getattr(settings, name, default)


def _resolve_credential() -> str:
    """The box's bearer credential, resolved the way the rest of sync_engine does.

    Two sources, and only one of them is an env var: a box that was PAIRED keeps its
    credential in the database, where no amount of environment reading would find it.
    ``edge_binding.edge_credential()`` covers both, and is what every other caller in
    this app already uses.

    Falls back to the raw env var if the app registry is not up -- this module is
    importable from an entrypoint, and a credential lookup must not be the thing that
    turns a partially-booted box into a traceback.
    """
    try:
        from apps.sync_engine.edge_binding import edge_credential

        return edge_credential()
    except Exception:  # noqa: BLE001 - see docstring; the fallback is the same value
        return (os.getenv("RMC_EDGE_CREDENTIAL") or "").strip()


def auto_apply_mode() -> str:
    """``off`` | ``assets`` | ``full`` — how much this box may apply unattended."""
    raw = str(_setting("RMC_OTA_AUTO_APPLY", MODE_OFF) or MODE_OFF).strip().lower()
    return raw if raw in (MODE_OFF, MODE_ASSETS, MODE_FULL) else MODE_OFF


def release_root() -> Path | None:
    """Root of a symlink-based release layout, when the deployment uses one.

    ``None`` means the ordinary single-tree deployment, where a code swap cannot be made
    atomic and is therefore reported as deferred rather than faked.
    """
    raw = str(_setting("RMC_OTA_RELEASE_ROOT", "") or "").strip()
    return Path(raw) if raw else None


def release_headroom_ratio() -> float:
    """How much free space a release copy must find before it is allowed to start.

    A release is a whole tree, so applying one costs roughly the size of the app again.
    On the cheap hardware many schools actually run, filling the disk does not merely fail
    the upgrade -- it stops Postgres being able to write, and the box loses its data sync
    along with everything else. A refused upgrade is recoverable; a full disk on an
    appliance nobody is standing next to is not.
    """
    try:
        pct = int(_setting("RMC_OTA_RELEASE_HEADROOM_PCT", 140))
    except (TypeError, ValueError):
        pct = 140
    return max(1.0, pct / 100.0)


def tree_bytes(path) -> int:
    """Bytes on disk under ``path``. Unreadable entries are skipped, never fatal."""
    total = 0
    for root, _dirs, names in os.walk(str(path)):
        for name in names:
            try:
                total += os.lstat(os.path.join(root, name)).st_size
            except OSError:
                continue
    return total


def releases_to_keep() -> int:
    """How many release trees to leave on disk, newest first. Two is the floor.

    Two, because the second one IS the rollback target: pruning to one would mean the box
    can no longer go back, which is the entire reason for the layout. Anything above two
    is disk spent on history nobody reads.
    """
    try:
        return max(2, int(_setting("RMC_OTA_RELEASES_KEPT", 2)))
    except (TypeError, ValueError):
        return 2


def staging_root() -> Path:
    raw = str(_setting("RMC_OTA_STAGING_ROOT", "") or "").strip()
    if raw:
        return Path(raw)
    return Path(str(_setting("BASE_DIR", "."))) / _DEFAULT_STAGING_DIRNAME


def live_root() -> Path:
    return Path(str(_setting("RMC_OTA_MANIFEST_ROOT", "") or _setting("BASE_DIR", ".")))


def health_timeout_seconds() -> int:
    try:
        return max(5, int(_setting("RMC_OTA_HEALTH_TIMEOUT_SECONDS", _DEFAULT_HEALTH_TIMEOUT)))
    except (TypeError, ValueError):
        return _DEFAULT_HEALTH_TIMEOUT


class LocalRuntimeUpgradeManager:
    """Drive one upgrade attempt end to end. Never leaves the box on an unverified tree."""

    def __init__(
        self,
        *,
        operator_base: str = "",
        token: str = "",
        mode: str = MODE_ASSETS,
        target_manifest: dict | None = None,
        source_root: Path | None = None,
        health_url: str = "",
        now=None,
    ):
        self.operator_base = (operator_base or str(_setting("RMC_EDGE_OPERATOR_BASE", "") or "")).rstrip("/")
        # This read a Django setting named RMC_EDGE_SYNC_TOKEN, which is defined
        # NOWHERE -- not settings.py, not the settings registry, not
        # .env.edge.example. It occurred exactly twice in the tree: on this line, and
        # in the --token help text that documented it. So it always resolved to "",
        # every unattended upgrade sent `Authorization: Bearer ` with nothing after
        # it, and the cloud answered 401. MEASURED on a live box: edge_apply_upgrade
        # 401'd against the manifest endpoint that answers 409 not_released for the
        # credential everything else uses -- so OTA had never once authenticated, and
        # the failure looked like a credential problem rather than a missing setting.
        #
        # A wrong name fails exactly like a revoked token, which is why this survived:
        # both are a 401, and the box holds a credential that demonstrably works.
        self.token = token or _resolve_credential()
        self.mode = mode if mode in (MODE_ASSETS, MODE_FULL) else MODE_ASSETS
        self.target_manifest = target_manifest or {}
        # ``source_root`` lets a test (or a LAN data-mule with a USB stick) supply the
        # bytes from a local directory instead of the network. The gates are identical
        # either way — which is the point: the verification is not a property of HTTP.
        self.source_root = Path(source_root) if source_root else None
        self.health_url = health_url or str(_setting("RMC_OTA_HEALTH_URL", "http://127.0.0.1:10000/health/"))
        self._now = now or time.monotonic
        self.log: list[str] = []
        self.history_row = None
        self._writes_frozen = False
        self._migration_floor: dict = {}
        self._previous_release: Path | None = None

    # ── logging ──────────────────────────────────────────────────────────────
    def _say(self, message: str) -> None:
        self.log.append(message)
        logger.info("[ota] %s", message)

    # ── 0. plan ──────────────────────────────────────────────────────────────
    def fetch_target_manifest(self) -> dict:
        """The operator's manifest. From ``source_root`` when given, else over HTTPS."""
        if self.target_manifest:
            return self.target_manifest
        if self.source_root is not None:
            self.target_manifest = load_manifest(self.source_root / manifest_path().name)
            return self.target_manifest
        from apps.sync_engine.cloud_endpoints import cloud_endpoint

        url = cloud_endpoint(self.operator_base, "api:sync-upgrade-manifest")
        local_hash = str((load_manifest() or {}).get("manifest_hash") or "")
        if local_hash:
            url += "?" + urllib.parse.urlencode({"since": local_hash})
        request = urllib.request.Request(url, headers={"Authorization": f"Bearer {self.token}"})
        with urllib.request.urlopen(request, timeout=60) as response:  # noqa: S310 — operator URL
            import json

            payload = json.loads(response.read().decode("utf-8", "replace"))
        if not payload.get("ok"):
            raise UpgradeAborted(f"operator refused the manifest request: {payload.get('error')}")
        # Reassemble a manifest document from the response so every downstream step works
        # on one shape regardless of where the bytes came from.
        self.target_manifest = {
            "manifest_hash": payload.get("manifest_hash") or "",
            "version_label": payload.get("version_label") or "",
            "channel": payload.get("channel") or "stable",
            "engine_commit": payload.get("engine_commit") or "",
            "migration_heads": payload.get("migration_heads") or {},
            "files": payload.get("files") or {},
        }
        return self.target_manifest

    def plan(self) -> dict:
        """The delta this box must fetch, narrowed by mode."""
        target = self.fetch_target_manifest()
        if not target.get("files"):
            raise UpgradeAborted("operator manifest is empty — nothing to apply")
        categories = ASSET_CATEGORIES if self.mode == MODE_ASSETS else None
        delta = upgrade_delta.compute_delta(load_manifest(), target, categories=categories)
        self._say(
            f"plan: target {str(target.get('manifest_hash'))[:12]} · "
            f"{upgrade_delta.describe(delta) or 'nothing to fetch'} · mode={self.mode}"
        )
        return delta

    # ── 1. drain ─────────────────────────────────────────────────────────────
    def drain(self, *, timeout_seconds: int = _DEFAULT_DRAIN_TIMEOUT) -> dict:
        """Hold the rail and wait for in-flight cycles to finish.

        Bounded and non-fatal: a cycle that outlives the budget does NOT abort the
        upgrade, because the steps that follow do not touch the running tree until the
        verify gate has passed anyway. What the wait buys is that the common case has no
        overlap at all, and the uncommon case is recorded rather than hidden.
        """
        target = str(self.target_manifest.get("manifest_hash") or "")
        upgrade_lock.arm_local(target_hash=target, reason="local upgrade in progress")

        # Stop NEW work arriving before waiting for the work already in flight — the
        # other order races forever on a busy box.
        self._writes_frozen = upgrade_runtime.freeze_writes()
        self._say(
            "drain: user writes frozen (maintenance 503; /health/ and superusers exempt)"
            if self._writes_frozen
            else "drain: write freeze NOT installed — no usable cache; proceeding without it"
        )
        self._say("drain: " + upgrade_runtime.pause_workers())

        deadline = self._now() + max(1, timeout_seconds)
        in_flight = 0
        while self._now() < deadline:
            try:
                from apps.sync_engine.models import EdgeSyncRun

                # tenant-isolation-allow: box upgrade drain: counts in-flight runs box-wide because the upgrade must wait for ALL of them; a count, never a read of tenant rows (reviewed 2026-09-01)
                in_flight = EdgeSyncRun.objects.filter(finished_at__isnull=True).count()
            except Exception:  # noqa: BLE001 — a drain check must never abort an upgrade
                in_flight = 0
            if in_flight == 0:
                break
            time.sleep(1)
        self._say(
            "drain: rail held" + ("" if in_flight == 0 else f"; {in_flight} cycle(s) still running")
        )
        return {"held": True, "in_flight": in_flight}

    # ── 2. stage ─────────────────────────────────────────────────────────────
    def _release_dir(self) -> Path:
        digest = str(self.target_manifest.get("manifest_hash") or "unknown")[:12]
        return staging_root() / digest

    def _fetch_file(self, record: dict, destination: Path) -> int:
        """Pull one file into ``destination``. Resumes from whatever is already there."""
        destination.parent.mkdir(parents=True, exist_ok=True)
        if self.source_root is not None:
            shutil.copyfile(self.source_root / record["path"], destination)
            return destination.stat().st_size

        from apps.sync_engine.cloud_endpoints import cloud_endpoint

        endpoint = cloud_endpoint(self.operator_base, "api:sync-upgrade-chunk")
        offset = destination.stat().st_size if destination.exists() else 0
        attempts = 0
        while True:
            url = endpoint + "?" + urllib.parse.urlencode(
                {"path": record["path"], "offset": offset, "length": _CHUNK_BYTES}
            )
            request = urllib.request.Request(url, headers={"Authorization": f"Bearer {self.token}"})
            try:
                with urllib.request.urlopen(request, timeout=60) as response:  # noqa: S310
                    payload = response.read()
                    complete = str(response.headers.get("X-RMC-Upgrade-Complete") or "") == "1"
            except (urllib.error.URLError, OSError) as exc:
                attempts += 1
                if attempts >= _MAX_ATTEMPTS_PER_FILE:
                    raise UpgradeAborted(f"{record['path']}: transfer failed ({exc})") from exc
                continue
            if payload:
                with open(destination, "ab") as handle:
                    handle.write(payload)
                offset += len(payload)
            if complete or not payload:
                return offset

    def stage(self, delta: dict) -> Path:
        """Land every changed file in an isolated directory. Running tree untouched."""
        release = self._release_dir()
        release.mkdir(parents=True, exist_ok=True)
        records = list(delta.get("added") or []) + list(delta.get("changed") or [])
        total = 0
        for record in records:
            total += self._fetch_file(record, release / record["path"])
        self._say(f"stage: {len(records)} file(s), {total} bytes -> {release}")
        return release

    # ── 3. verify ────────────────────────────────────────────────────────────
    def verify(self, delta: dict, release: Path) -> dict:
        """Re-hash the staged tree. A single disagreement stops the deployment.

        The failure this exists for is not exotic. A chunked transfer over a link that
        drops mid-file produces a shorter file and a 200 on every request that made it;
        nothing in the transport can tell the difference afterwards, and a truncated
        template or JS bundle that reaches a running box is a broken school day.
        """
        paths = [record["path"] for record in (list(delta.get("added") or []) + list(delta.get("changed") or []))]
        report = verify_tree(self.target_manifest, release, paths=paths)
        if not report["ok"]:
            detail = []
            if report["mismatched"]:
                detail.append(f"{len(report['mismatched'])} corrupt ({', '.join(report['mismatched'][:3])})")
            if report["missing"]:
                detail.append(f"{len(report['missing'])} missing ({', '.join(report['missing'][:3])})")
            raise UpgradeAborted("verify FAILED — " + "; ".join(detail))
        self._say(f"verify: {report['checked']}/{len(paths)} sha256 match")
        return report

    # ── 4. migration precheck ────────────────────────────────────────────────
    def precheck_migrations(self, delta: dict) -> dict:
        """Would these migrations apply? Answered without leaving the schema changed.

        Two tiers, and the manager reports honestly which one it got:

        * ``transactional`` — the plan is EXECUTED inside ``transaction.atomic()`` and then
          rolled back. Only on a backend with transactional DDL and only outside
          django-tenants, whose ``migrate_schemas`` spans many schemas and cannot be
          wrapped in one transaction.
        * ``plan-only`` — the unapplied plan is listed and scanned for destructive
          operations using the coordinator the platform already trusts
          (``platform_runtime.schema_rollout``). Weaker, and said so rather than implied.
        """
        migrations = list(delta.get("migrations") or [])
        if not migrations:
            self._say("precheck: no migrations in this delta")
            return {"level": "none", "ok": True, "migrations": []}

        dangerous = []
        try:
            from apps.platform_runtime.schema_rollout import find_dangerous_operations

            dangerous = find_dangerous_operations()
        except Exception:  # noqa: BLE001 — a scanner failure must not read as "safe"
            logger.debug("ota: danger scan unavailable", exc_info=True)
            dangerous = []

        if dangerous and not bool(_setting("RMC_OTA_ALLOW_DANGEROUS_MIGRATIONS", False)):
            names = ", ".join(f"{app}.{name}:{op}" for app, name, op in dangerous[:5])
            raise UpgradeAborted(
                f"precheck REFUSED — destructive migration operation(s) present: {names}. "
                "Set RMC_OTA_ALLOW_DANGEROUS_MIGRATIONS=1 to apply deliberately."
            )

        from django.db import connection

        tenants = bool(_setting("USE_DJANGO_TENANTS", False))
        transactional = getattr(connection.features, "can_rollback_ddl", False) and not tenants
        if not transactional:
            self._say(
                f"precheck: plan-only ({len(migrations)} migration(s)); "
                + ("django-tenants spans schemas" if tenants else "backend cannot roll back DDL")
            )
            return {"level": "plan-only", "ok": True, "migrations": migrations}

        from django.core.management import call_command
        from django.db import transaction

        class _Rollback(Exception):
            """Sentinel: unwinds the probe transaction. Never escapes this method."""

        try:
            with transaction.atomic():
                call_command("migrate", verbosity=0, interactive=False)
                raise _Rollback()
        except _Rollback:
            self._say(f"precheck: transactional dry-run PASSED for {len(migrations)} migration(s), rolled back")
            return {"level": "transactional", "ok": True, "migrations": migrations}
        except Exception as exc:  # noqa: BLE001 — a failing probe is the answer, not a crash
            raise UpgradeAborted(f"precheck FAILED — migrations do not apply: {exc}") from exc

    # ── 5. activate ──────────────────────────────────────────────────────────
    def activate(self, delta: dict, release: Path) -> str:
        """Promote the verified tree. Returns ``swapped`` | ``deferred``.

        Per-file ``os.replace`` rather than a whole-tree switch, because the ordinary
        deployment is a single directory and there is no second one to point at. Each
        replace is itself atomic, and every file overwritten is copied into the release's
        ``rollback/`` set FIRST — so the undo is complete even if the process dies
        halfway, which is the property that actually matters here.
        """
        root = release_root()
        if root is not None and self.mode == MODE_FULL:
            return self._activate_release_symlink(delta, release, root)
        if self.mode == MODE_FULL and root is None:
            self._say(
                "activate: DEFERRED — this deployment is a single tree with no release "
                "symlink (RMC_OTA_RELEASE_ROOT unset), so a code swap cannot be made "
                "atomic. Staged and verified; apply with an image rebuild."
            )
            return "deferred"

        live = live_root()
        rollback_dir = release / _ROLLBACK_DIRNAME
        records = list(delta.get("added") or []) + list(delta.get("changed") or [])
        swapped = 0
        for record in records:
            relative = record["path"]
            staged = release / relative
            target = live / relative
            if target.exists():
                backup = rollback_dir / relative
                backup.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(target, backup)
            target.parent.mkdir(parents=True, exist_ok=True)
            os.replace(staged, target)
            swapped += 1
        self._say(f"activate: {swapped} file(s) swapped into {live} (rollback set in {rollback_dir})")

        self._collect_static(delta)
        self._flush_caches()
        self._say("activate: " + upgrade_runtime.reload_workers())
        return "swapped"

    def _require_disk_headroom(self, source: Path, root: Path) -> None:
        """Refuse to start a release copy the disk cannot hold."""
        try:
            need = tree_bytes(source)
            free = shutil.disk_usage(str(root)).free
        except OSError as exc:
            # Cannot measure -- do not invent a verdict. The copy itself fails honestly if
            # there is no room, and that path cleans up after itself.
            self._say(f"space: could not measure free space ({exc}); continuing")
            return
        want = int(need * release_headroom_ratio())
        if free < want:
            raise UpgradeAborted(
                f"not enough disk to build the new release: ~{want // (1024 * 1024)}MB "
                f"wanted at {root}, {free // (1024 * 1024)}MB free. The box stays on its "
                f"current code and keeps syncing. Free space on the release volume, lower "
                f"RMC_OTA_RELEASES_KEPT, or unset RMC_OTA_RELEASE_ROOT on this box to go "
                f"back to image-rebuild upgrades."
            )
        self._say(f"space: {free // (1024 * 1024)}MB free, ~{want // (1024 * 1024)}MB wanted -- ok")

    def _prune_old_releases(self, releases: Path, keep) -> None:
        """Delete release trees older than the ones still needed.

        Without this the layout is a slow disk leak: every upgrade adds a whole tree and
        nothing removes one, so a box with a small volume fills up after enough upgrades
        and then fails the very check above -- having spent the space on releases nobody
        will ever roll back to. Newest-first by mtime; the current release and the
        rollback target are never candidates.
        """
        keep_paths = set()
        for candidate in keep:
            if candidate is None:
                continue
            try:
                keep_paths.add(candidate.resolve())
            except OSError:
                continue
        try:
            directories = [d for d in releases.iterdir() if d.is_dir()]
            directories.sort(key=lambda d: d.stat().st_mtime, reverse=True)
        except OSError:
            return
        seen = 0
        for directory in directories:
            try:
                if directory.resolve() in keep_paths:
                    continue
            except OSError:
                continue
            seen += 1
            if seen < releases_to_keep():
                continue
            self._say(f"prune: removing old release {directory.name}")
            shutil.rmtree(directory, ignore_errors=True)

    def _activate_release_symlink(self, delta: dict, release: Path, root: Path) -> str:
        """Whole-tree blue-green: build the new release beside the old, then flip one link.

        This is the activation the ordinary image cannot have. ``<root>/releases/<hash>``
        is materialised by copying the CURRENT release and overlaying the verified staged
        files, so the new directory is a complete tree rather than a diff; then
        ``<root>/current`` is repointed with an atomic rename. Nothing the web server is
        serving changes until that one call, and going back is the same call with the old
        target — which is why this path does not need the per-file rollback set.
        """
        releases = root / "releases"
        releases.mkdir(parents=True, exist_ok=True)
        digest = str(self.target_manifest.get("manifest_hash") or "unknown")[:12]
        new_release = releases / digest
        current = root / "current"

        previous = current.resolve() if current.exists() else None
        if new_release.exists():
            shutil.rmtree(new_release, ignore_errors=True)

        # No current release yet: seed from the live tree so the new release is whole.
        source = previous if (previous is not None and previous.is_dir()) else live_root()

        # MEASURE BEFORE COPYING. A release is a whole tree -- roughly the size of the app
        # again -- and on a small disk an upgrade that runs out of space does not merely
        # fail: Postgres stops being able to write and the box loses its data sync too.
        # Refusing here leaves it on its current code, still syncing, with a message that
        # says what to do about it.
        self._require_disk_headroom(source, root)

        try:
            shutil.copytree(source, new_release, symlinks=True, dirs_exist_ok=True)
        except OSError as exc:
            # Never leave a half-copied tree behind. It holds down the very space that ran
            # out, and the next attempt would copy IT forward as though it were whole.
            shutil.rmtree(new_release, ignore_errors=True)
            raise UpgradeAborted(
                f"could not build the new release ({exc}); the running tree is untouched"
            ) from exc

        records = list(delta.get("added") or []) + list(delta.get("changed") or [])
        for record in records:
            destination = new_release / record["path"]
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(release / record["path"], destination)
        for removed in list(delta.get("removed") or []):
            candidate = new_release / removed
            if candidate.is_file():
                candidate.unlink()

        # Verify the ASSEMBLED release, not just the delta — a copytree that silently
        # dropped a file would otherwise reach traffic on the strength of a check that
        # only ever looked at the files we happened to fetch.
        report = verify_tree(self.target_manifest, new_release)
        if not report["ok"]:
            shutil.rmtree(new_release, ignore_errors=True)
            raise UpgradeAborted(
                f"assembled release failed verification: {len(report['mismatched'])} corrupt, "
                f"{len(report['missing'])} missing"
            )

        # Atomic flip. A symlink cannot be replaced in place on either platform, so the
        # new link is created beside it and renamed over — os.replace is atomic for both.
        staging_link = root / f".current.{digest}"
        if staging_link.exists() or staging_link.is_symlink():
            staging_link.unlink()
        try:
            staging_link.symlink_to(new_release, target_is_directory=True)
            os.replace(staging_link, current)
        except OSError as exc:
            # Windows without developer mode, or a filesystem with no symlink support.
            if staging_link.exists() or staging_link.is_symlink():
                staging_link.unlink()
            raise UpgradeAborted(f"symlink swap failed ({exc}); running tree untouched") from exc

        self._previous_release = previous
        self._say(f"activate: {current} -> releases/{digest} (atomic symlink flip)")
        self._prune_old_releases(releases, keep=[new_release, previous])
        self._collect_static(delta)
        self._flush_caches()
        self._say("activate: " + upgrade_runtime.reload_workers())
        return "swapped"

    def _collect_static(self, delta: dict | None = None) -> None:
        """Re-hash the static manifest so the new assets are addressable.

        Load-bearing rather than cosmetic: production serves through
        ``ForgivingCompressedManifestStaticFilesStorage``, which resolves ``{% static %}``
        through ``staticfiles.json``. New bytes that were never collected are simply not
        reachable by any URL the templates can produce.
        """
        if not bool(_setting("RMC_OTA_COLLECTSTATIC", True)):
            self._say("activate: collectstatic disabled by RMC_OTA_COLLECTSTATIC")
            return
        if delta is not None:
            touched = {
                str(r.get("category") or "")
                for r in (list(delta.get("added") or []) + list(delta.get("changed") or []))
            }
            if STATIC_ASSET not in touched:
                # A templates-only release does not need it, and collectstatic on a large
                # asset set is minutes of work — spending them for nothing widens the
                # window in which the box is mid-upgrade.
                self._say("activate: no static assets changed; collectstatic skipped")
                return
        try:
            from django.core.management import call_command

            call_command("collectstatic", interactive=False, verbosity=0)
            self._say("activate: collectstatic complete")
        except Exception as exc:  # noqa: BLE001 — reported, not fatal; health gate decides
            self._say(f"activate: collectstatic FAILED ({exc}) — health gate will decide")

    def _flush_caches(self) -> None:
        """Drop the caches that would otherwise keep serving the previous release."""
        try:
            from apps.sync_engine import schema_guard

            schema_guard.reset()
        except Exception:  # noqa: BLE001
            logger.debug("ota: schema_guard reset failed", exc_info=True)
        try:
            from django.template import engines

            for engine in engines.all():
                loaders = getattr(getattr(engine, "engine", None), "template_loaders", []) or []
                for loader in loaders:
                    if hasattr(loader, "reset"):
                        loader.reset()
        except Exception:  # noqa: BLE001
            logger.debug("ota: template loader reset failed", exc_info=True)
        self._say("activate: caches flushed")

    # ── 6. health gate ───────────────────────────────────────────────────────
    def health_gate(self) -> tuple[bool, float, str]:
        """Poll ``/health/`` until it answers 200 or the budget runs out."""
        budget = health_timeout_seconds()
        started = self._now()
        detail = "no response"
        while self._now() - started < budget:
            try:
                with urllib.request.urlopen(self.health_url, timeout=5) as response:  # noqa: S310
                    if response.status == 200:
                        elapsed = self._now() - started
                        self._say(f"health: 200 in {elapsed:.1f}s of {budget}s")
                        return True, elapsed, "200"
                    detail = f"HTTP {response.status}"
            except (urllib.error.URLError, OSError) as exc:
                detail = str(exc)[:120]
            time.sleep(_DEFAULT_HEALTH_POLL)
        elapsed = self._now() - started
        self._say(f"health: FAILED after {elapsed:.1f}s ({detail})")
        return False, elapsed, detail

    # ── 7. rollback ──────────────────────────────────────────────────────────
    def rollback(self, release: Path) -> int:
        """Put the box back: the schema first, then the files. Returns files restored.

        SCHEMA FIRST, and the order is not arbitrary. Restoring the code while the
        database still carries the new columns leaves old code reading a schema it was
        never written against — the same split-brain a failed upgrade is supposed to
        avoid, arrived at from the other direction. Reversing first means that at no
        point is there a schema the running code cannot handle.
        """
        self._reverse_migrations()

        # A release-symlink deployment goes back by pointing the link at the tree it came
        # from. There is no per-file set to restore because no file was ever overwritten.
        if self._previous_release is not None:
            current = (release_root() or Path(".")) / "current"
            staging_link = current.parent / ".current.rollback"
            try:
                if staging_link.exists() or staging_link.is_symlink():
                    staging_link.unlink()
                staging_link.symlink_to(self._previous_release, target_is_directory=True)
                os.replace(staging_link, current)
                self._say(f"rollback: {current} -> {self._previous_release} (atomic symlink flip)")
                self._say("rollback: " + upgrade_runtime.reload_workers())
                return 0
            except OSError as exc:
                self._say(f"rollback: symlink restore FAILED ({exc}); falling through to file restore")

        rollback_dir = release / _ROLLBACK_DIRNAME
        if not rollback_dir.is_dir():
            self._say("rollback: no file set to restore (activation had not begun)")
            return 0
        live = live_root()
        restored = 0
        for path in rollback_dir.rglob("*"):
            if not path.is_file():
                continue
            relative = path.relative_to(rollback_dir)
            target = live / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(path, target)
            restored += 1
        self._collect_static()
        self._flush_caches()
        self._say("rollback: " + upgrade_runtime.reload_workers())
        self._say(f"rollback: {restored} file(s) restored to the previous manifest")
        return restored

    def _reverse_migrations(self) -> None:
        """Unwind the schema to the floor recorded before this attempt ran.

        BOUNDED AND HONEST. Only apps this attempt actually advanced are touched, and
        only back to the exact index they were on. A migration Django cannot reverse
        (``IrreversibleError`` — a data migration with no ``reverse_code``) is REPORTED and
        left applied rather than forced: there is no safe automatic way to undo a data
        migration on a school's live database, and a rollback that destroys records to
        restore a schema has done more damage than the failure it was cleaning up.

        Opt-out for an operator who would rather fix forward:
        ``RMC_OTA_REVERSE_MIGRATIONS_ON_ROLLBACK=0``.
        """
        if not self._migration_floor:
            return
        if not bool(_setting("RMC_OTA_REVERSE_MIGRATIONS_ON_ROLLBACK", True)):
            self._say("rollback: migration reversal disabled by setting; schema left as applied")
            return

        current = _current_migration_heads()
        advanced = {
            app: floor
            for app, floor in self._migration_floor.items()
            if str(current.get(app, "")) > str(floor)
        }
        # An app that had NO migrations applied before and has some now cannot be expressed
        # as "migrate <app> <index>"; Django spells that "migrate <app> zero".
        for app, head in current.items():
            if app not in self._migration_floor and head:
                advanced[app] = "zero"

        if not advanced:
            self._say("rollback: schema unchanged by this attempt; nothing to reverse")
            return

        from django.core.management import call_command

        reversed_apps, refused = [], []
        for app, floor in sorted(advanced.items()):
            try:
                call_command("migrate", app, floor, interactive=False, verbosity=0)
                reversed_apps.append(f"{app}->{floor}")
            except Exception as exc:  # noqa: BLE001 - a refusal is information, not a crash
                refused.append(f"{app} ({type(exc).__name__}: {str(exc)[:_REFUSAL_DETAIL_MAX_CHARS]})")
        if reversed_apps:
            self._say("rollback: schema reversed " + ", ".join(reversed_apps))
        if refused:
            self._say(
                "rollback: could NOT reverse " + "; ".join(refused)
                + " — these migrations remain applied; fix forward"
            )

    # ── orchestration ────────────────────────────────────────────────────────
    def run(self) -> dict:
        """One attempt, recorded in ``EdgeDeploymentHistory`` whatever the outcome."""
        from apps.sync_engine.models_deployment import EdgeDeploymentHistory

        result = {
            "ok": False,
            "mode": self.mode,
            "activation": "none",
            "manifest_hash": "",
            "log": self.log,
            "error": "",
        }
        release = None
        try:
            delta = self.plan()
        except UpgradeAborted as exc:
            result["error"] = str(exc)
            self._say(f"ABORTED before staging: {exc}")
            return result

        target_hash = str(self.target_manifest.get("manifest_hash") or "")
        result["manifest_hash"] = target_hash
        previous = str((load_manifest() or {}).get("manifest_hash") or "")

        if not delta.get("file_count") and not delta.get("removed"):
            upgrade_lock.acknowledge_local(target_hash)
            upgrade_lock.disarm_local()
            result["ok"] = True
            result["activation"] = "none"
            self._say("already in parity with the operator manifest")
            return result

        self._migration_floor = _current_migration_heads()
        self.history_row = EdgeDeploymentHistory.begin(
            migration_floor=self._migration_floor,
            manifest_hash=target_hash,
            previous_manifest_hash=previous,
            version_label=self.target_manifest.get("version_label") or "",
            channel=self.target_manifest.get("channel") or "stable",
            engine_commit=self.target_manifest.get("engine_commit") or "",
            release_id=f"rel_{target_hash[:12]}",
            release_path=str(self._release_dir()),
            files_total=int(delta.get("file_count") or 0),
            bytes_total=int(delta.get("total_bytes") or 0),
            mode=self.mode,
            complete=bool(delta.get("complete")),
            message="staged",
        )

        try:
            self.drain()
            release = self.stage(delta)
            report = self.verify(delta, release)
            self.history_row.mark_verified(files_verified=report["checked"], message="verified")
            self.precheck_migrations(delta)
            activation = self.activate(delta, release)
            result["activation"] = activation

            if activation == "deferred":
                # Nothing changed, so there is nothing to health-check and nothing to
                # roll back. Recorded as FAILED rather than ACTIVE precisely because the
                # box is NOT running the target manifest and must not be reported as if
                # it were.
                self.history_row.mark_failed(
                    "activation deferred: no release symlink layout",
                    message="staged and verified; requires an image rebuild",
                )
                # Acknowledged, not forgotten: the box has done everything it is able to
                # do about this target, so continuing to hold its DATA rail would take the
                # school offline for records as well as for code — a strictly worse
                # outcome than running one release behind. The upgrade stays visible on
                # every cycle via result["upgrade_available"].
                upgrade_lock.acknowledge_local(target_hash)
                upgrade_lock.disarm_local()
                self._restore_runtime()
                result["ok"] = True
                self._say("finished: staged + verified, activation deferred")
                return result

            self._apply_migrations(delta)
            healthy, elapsed, detail = self.health_gate()
            if not healthy:
                self.rollback(release)
                self.history_row.mark_rolled_back(
                    f"health gate failed: {detail}",
                    message="rolled back to the previous manifest",
                    health_seconds=elapsed,
                    health_detail=detail,
                )
                upgrade_lock.record_local_failure(target_hash=target_hash, error=f"health: {detail}")
                upgrade_lock.disarm_local()
                self._restore_runtime()
                result["error"] = f"health gate failed: {detail}"
                return result

            self._stamp_local_manifest()
            upgrade_lock.acknowledge_local(target_hash)
            self.history_row.mark_active(
                activation=activation,
                health_seconds=elapsed,
                health_detail=detail,
                message="upgrade applied",
            )
            upgrade_lock.clear_local_failure()
            upgrade_lock.disarm_local()
            self._restore_runtime()
            self._say(self._notify_cloud_revived())
            result["ok"] = True
            self._say("finished: upgrade live")
            return result

        except UpgradeAborted as exc:
            result["error"] = str(exc)
            if release is not None:
                self.rollback(release)
            if self.history_row is not None:
                self.history_row.mark_failed(str(exc), message="aborted at a safety gate")
            upgrade_lock.record_local_failure(target_hash=target_hash, error=str(exc))
            upgrade_lock.disarm_local()
            self._restore_runtime()
            self._say(f"ABORTED: {exc}")
            return result
        except Exception as exc:  # noqa: BLE001 — an unexpected failure must still restore
            result["error"] = f"unexpected failure: {exc}"
            if release is not None:
                self.rollback(release)
            if self.history_row is not None:
                self.history_row.mark_failed(str(exc), message="unexpected failure")
            upgrade_lock.record_local_failure(target_hash=target_hash, error=str(exc))
            upgrade_lock.disarm_local()
            self._restore_runtime()
            logger.exception("ota: unexpected failure applying %s", target_hash[:12])
            return result

    def _restore_runtime(self) -> None:
        """Undo everything :meth:`drain` did. Called on EVERY exit, success or not.

        A box left frozen after a failed upgrade is a school locked out of its own system,
        which is a strictly worse outcome than the drift the upgrade was closing. The
        freeze also carries a TTL for the case where this process never reaches here.
        """
        if self._writes_frozen:
            self._say(
                "restore: user writes thawed" if upgrade_runtime.thaw_writes()
                else "restore: could not lift the write freeze — it expires on its own TTL"
            )
        self._say("restore: " + upgrade_runtime.resume_workers())

    def _notify_cloud_revived(self) -> str:
        """Tell the cloud immediately that this box is on the new manifest.

        Without this the hold clears on the box's next ordinary cycle, which is correct
        but up to a cadence interval away — and for that whole window the cloud reports a
        school as held for an upgrade it has already finished. One cheap GET closes it:
        the manifest endpoint releases the hold the moment the hashes agree, so this is
        the revival callback rather than a second status protocol.
        """
        if self.source_root is not None or not self.operator_base or not self.token:
            return "revival callback skipped (no operator link on this run)"
        from apps.sync_engine.cloud_endpoints import cloud_endpoint

        digest = str(load_manifest().get("manifest_hash") or "")
        url = cloud_endpoint(self.operator_base, "api:sync-upgrade-manifest")
        if digest:
            url += "?" + urllib.parse.urlencode({"since": digest})
        request = urllib.request.Request(url, headers={"Authorization": f"Bearer {self.token}"})
        try:
            with urllib.request.urlopen(request, timeout=30) as response:  # noqa: S310
                return f"revival callback -> cloud answered {response.status}"
        except (urllib.error.URLError, OSError) as exc:
            # The box is upgraded and healthy either way; the cloud finds out on the next
            # cycle. A failed callback must never turn a successful upgrade into a failure.
            return f"revival callback could not reach the cloud ({exc}); cloud clears on next cycle"

    def _apply_migrations(self, delta: dict) -> None:
        """Run the migrations the delta brought, the way this deployment runs them."""
        if not delta.get("migrations"):
            return
        from django.core.management import call_command

        applied = []
        try:
            if bool(_setting("USE_DJANGO_TENANTS", False)):
                call_command("migrate_schemas", shared=True, interactive=False, verbosity=0)
                call_command("migrate_schemas", tenant=True, interactive=False, verbosity=0)
            else:
                call_command("migrate", interactive=False, verbosity=0)
            applied = [f"{m['app_label']}.{m['migration_index']}" for m in delta["migrations"]]
            self._say(f"migrate: {len(applied)} migration(s) applied")
        except Exception as exc:  # noqa: BLE001
            raise UpgradeAborted(f"migrate FAILED after precheck passed: {exc}") from exc
        if self.history_row is not None:
            self.history_row.migrations_applied = applied
            self.history_row.save(update_fields=["migrations_applied"])

    def _stamp_local_manifest(self) -> None:
        """Re-record what this box is NOW, by re-crawling its own tree.

        Not "copy the operator's manifest in". A full-lane upgrade that landed every file
        will hash to the target anyway; an asset-only lane will not, and must not, because
        the box genuinely is not on the target — its python is still the old python. The
        crawl is the only statement that is true in both cases, and it is what keeps the
        NEXT delta honest: a manifest claiming a state the tree is not in would make every
        future subtraction start from fiction.
        """
        try:
            generator = SystemManifestGenerator(
                root=live_root(),
                version_label=str(self.target_manifest.get("version_label") or ""),
                channel=str(self.target_manifest.get("channel") or "stable"),
            )
            written = generator.write(manifest_path())
            digest = str(load_manifest(written).get("manifest_hash") or "")
            self._say(
                f"stamp: local manifest re-crawled -> {digest[:12]}"
                + ("" if digest == str(self.target_manifest.get("manifest_hash") or "") else " (still short of the target — expected on the assets lane)")
            )
        except OSError as exc:
            self._say(f"stamp: could not write the local manifest ({exc})")


__all__ = [
    "MODE_ASSETS",
    "MODE_FULL",
    "MODE_OFF",
    "UpgradeAborted",
    "LocalRuntimeUpgradeManager",
    "auto_apply_mode",
    "release_root",
    "staging_root",
    "live_root",
    "health_timeout_seconds",
]
