"""Apply a pending OTA upgrade on this box, or report why it will not.

    python manage.py edge_apply_upgrade --status          # what is pending, change nothing
    python manage.py edge_apply_upgrade --mode assets     # templates/static/locale only
    python manage.py edge_apply_upgrade --mode full       # + python and migrations
    python manage.py edge_apply_upgrade --from /mnt/usb   # LAN data-mule, no network

Deliberately NOT automatic. ``RMC_OTA_AUTO_APPLY`` exists for operators who want the box
to apply upgrades on its own, and it defaults to ``off``: an appliance that rewrites its
own code while a school is teaching should be a decision somebody made, not a default.
"""
from __future__ import annotations

from django.core.management.base import BaseCommand, CommandError

from apps.sync_engine import upgrade_lock
from apps.sync_engine.local_upgrade import (
    MODE_ASSETS,
    MODE_FULL,
    LocalRuntimeUpgradeManager,
    auto_apply_mode,
    release_root,
)
from apps.sync_engine.system_manifest import load_manifest, local_manifest_hash


class Command(BaseCommand):
    help = "Stage, verify and apply the operator's pending upgrade on this edge box."

    def add_arguments(self, parser):
        parser.add_argument("--mode", choices=[MODE_ASSETS, MODE_FULL], default="", help="Default: RMC_OTA_AUTO_APPLY, else assets.")
        parser.add_argument("--status", action="store_true", help="Report state and exit without changing anything.")
        parser.add_argument("--from", dest="source_root", default="", help="Read the bundle from a local directory instead of the network.")
        parser.add_argument("--base", default="", help="Operator base URL (default: RMC_EDGE_OPERATOR_BASE).")
        parser.add_argument("--token", default="", help="Edge credential (default: RMC_EDGE_SYNC_TOKEN).")

    def handle(self, *args, **options):
        if options["status"]:
            return self._status()

        mode = options["mode"] or (auto_apply_mode() if auto_apply_mode() != "off" else MODE_ASSETS)
        manager = LocalRuntimeUpgradeManager(
            operator_base=options["base"],
            token=options["token"],
            mode=mode,
            source_root=options["source_root"] or None,
        )
        result = manager.run()
        for line in result["log"]:
            self.stdout.write(f"  {line}")

        if not result["ok"]:
            # A refusal is the product working. Exit non-zero so a wrapper script or a
            # supervisor notices, but say plainly that the box is still serving.
            raise CommandError(
                f"upgrade did not complete: {result['error']}\n"
                f"The box is still running its previous manifest and is serving normally."
            )
        self.stdout.write(
            self.style.SUCCESS(
                f"upgrade ok — activation={result['activation']} "
                f"manifest={result['manifest_hash'][:12] or 'unchanged'}"
            )
        )

    def _status(self):
        local = load_manifest()
        hold = upgrade_lock.local_state()
        failure = upgrade_lock.local_failure()
        root = release_root()

        self.stdout.write("Edge OTA status")
        self.stdout.write(f"  local manifest      {local_manifest_hash()[:12] or '(none — run generate_system_manifest)'}")
        self.stdout.write(f"  local version       {local.get('version_label') or '(unknown)'}")
        self.stdout.write(f"  sync state          {hold.get('state')}")
        if hold.get("target_hash"):
            self.stdout.write(f"  pending target      {str(hold['target_hash'])[:12]} (held {hold.get('held_seconds', 0)}s)")
            if hold.get("reason"):
                self.stdout.write(f"  reason              {hold['reason']}")
        self.stdout.write(f"  auto-apply          {auto_apply_mode()}")
        self.stdout.write(
            f"  code swap           {'symlink layout at ' + str(root) if root else 'DEFERRED (single-tree deployment; assets lane still applies)'}"
        )
        if failure:
            self.stdout.write(self.style.WARNING(f"  last failure        {failure.get('error', '')[:160]}"))

        try:
            from apps.sync_engine.models_deployment import EdgeDeploymentHistory

            active = EdgeDeploymentHistory.active()
            revert = EdgeDeploymentHistory.revert_target()
            self.stdout.write(f"  active row          {active.manifest_hash[:12] if active else '(none recorded)'}")
            self.stdout.write(f"  revert target       {revert.manifest_hash[:12] if revert else '(none recorded)'}")
        except Exception as exc:  # noqa: BLE001 - status must not fail on a missing table
            self.stdout.write(self.style.WARNING(f"  deployment history  unavailable ({exc})"))
