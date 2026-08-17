#!/usr/bin/env bash
# Near-instant edge sync the moment the box regains connectivity (OPTIONAL).
#
# The in-process scheduler already auto-syncs within one interval
# (RMC_EDGE_SYNC_INTERVAL_SECONDS, default 180s) of the network returning, and the
# entrypoint fires one reconcile on every boot — so this host hook is only for
# operators who want a sync fired the INSTANT an interface comes up (rather than
# within a couple of minutes).
#
# Install as a NetworkManager dispatcher hook on the HOST (not in the container):
#   sudo cp deploy/selfhost/edge-sync-on-connect.sh /etc/NetworkManager/dispatcher.d/90-rmc-edge-sync
#   sudo chown root:root /etc/NetworkManager/dispatcher.d/90-rmc-edge-sync
#   sudo chmod 755      /etc/NetworkManager/dispatcher.d/90-rmc-edge-sync
# NetworkManager invokes dispatcher scripts as: <script> <interface> <action>.
#
# Point it at your compose install by exporting these (or editing the defaults):
#   RMC_COMPOSE_DIR   directory holding docker-compose.yml   (default /opt/runmycampus)
#   RMC_WEB_SERVICE   compose service name for the web app   (default web)
set -euo pipefail

ACTION="${2:-}"
RMC_COMPOSE_DIR="${RMC_COMPOSE_DIR:-/opt/runmycampus}"
RMC_WEB_SERVICE="${RMC_WEB_SERVICE:-web}"

case "$ACTION" in
  up | vpn-up | dhcp4-change | dhcp6-change | connectivity-change)
    # Fire-and-forget; edge_autosync is flag-gated + offline-safe, so a spurious
    # trigger while still offline is a harmless no-op.
    if command -v docker >/dev/null 2>&1 && [ -d "$RMC_COMPOSE_DIR" ]; then
      (
        cd "$RMC_COMPOSE_DIR" \
          && docker compose exec -T "$RMC_WEB_SERVICE" \
               python manage.py edge_autosync >/dev/null 2>&1 || true
      ) &
    fi
    ;;
  *)
    : # ignore down / pre-up / hostname / other actions
    ;;
esac
