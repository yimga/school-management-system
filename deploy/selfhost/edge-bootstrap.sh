#!/usr/bin/env bash
#
# One command to bring this box's TLS to a correct, verified, backed-up state.
#
#   export RMC_EDGE_TLS_CA_PASSPHRASE='...'
#   bash deploy/selfhost/edge-bootstrap.sh
#
# Safe to run again, any number of times. On a box that is already correct it
# changes nothing and says so.
#
# WHY A SCRIPT AND NOT JUST THE MANAGEMENT COMMAND. Three of the steps cannot happen
# inside the container, and each of them was a place the twelve-step manual runbook
# went wrong:
#
#   * the Caddyfile is bind-mounted FROM THE HOST, so a process inside the web
#     container cannot write the file the terminator actually reads. Rendering it is
#     a host-side redirect, and doing that redirect in the wrong order is the trap
#     that serves Caddy's own CA to devices that trust yours;
#   * the CA backup has to leave the box to be a backup at all, which is a
#     `docker compose cp` on the host;
#   * the terminator has to be RESTARTED to pick up a reissued certificate -- it
#     reads its certificate at config load, not per handshake -- and a container
#     cannot restart a sibling without the docker socket, which is not worth handing
#     it for this.
#
# Everything that CAN be enforced in code is: see apps/schools/management/commands/
# edge_bootstrap.py, which refuses rather than proceeds on every precondition.
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO="$(cd "$HERE/../.." && pwd)"
COMPOSE_FILE="$HERE/docker-compose.yml"
COMPOSE=(docker compose -f "$COMPOSE_FILE")
CADDYFILE="$HERE/Caddyfile.edge"
BUNDLE_IN_BOX="/tmp/box-ca-bundle.p12"
# Deliberately the repo's PARENT, not the repo. box-ca-bundle.p12 carries the CA
# PRIVATE KEY, and $REPO is a git working tree on every box -- so the old default put
# a private key one `git add -A` away from a public remote, with nothing in
# .gitignore to stop it. On a stock box this resolves to /srv, beside /srv/rmc.
OUT_DIR="${RMC_EDGE_OUT_DIR:-$(dirname "$REPO")}"

say()  { printf '\n\033[1m== %s\033[0m\n' "$*"; }
ok()   { printf '   \033[32mok\033[0m   %s\n' "$*"; }
warn() { printf '   \033[33mwarn\033[0m %s\n' "$*"; }
die()  { printf '\n\033[31mSTOPPED\033[0m %s\n\n' "$*" >&2; exit 1; }

# --- 0. preconditions -------------------------------------------------------
say "Preconditions"
command -v docker >/dev/null 2>&1 || die "docker is not on PATH."
[ -f "$COMPOSE_FILE" ] || die "no compose file at $COMPOSE_FILE"
[ -f "$HERE/.env" ] || die "no $HERE/.env -- copy .env.edge.example and fill it in first."

if [ -z "${RMC_EDGE_TLS_CA_PASSPHRASE:-}" ]; then
  die "Set RMC_EDGE_TLS_CA_PASSPHRASE in your shell first:

    export RMC_EDGE_TLS_CA_PASSPHRASE='something-long'

  It encrypts the CA backup. It is taken from the environment and never from a
  flag, because a command line is visible in ps, in shell history and in docker's
  own event log. Store it somewhere separate from the bundle itself -- together,
  the encryption bought you nothing."
fi
ok "docker, compose file, .env and passphrase all present"

# --- 1. is the box well enough to change? -----------------------------------
say "Box health"
"${COMPOSE[@]}" ps --status running --services 2>/dev/null | grep -qx web \
  || die "the 'web' service is not running. Start it (\`docker compose -f $COMPOSE_FILE up -d\`)
  and let migrations finish. Adding TLS to an unwell box gives you two problems to
  debug at once, and from the corridor they look identical."
ok "web is running"

# --- 2. certificate, trust anchor, verified backup --------------------------
# The container-side command owns every irreversible decision: it refuses to mint a
# second CA on a box that recorded a different one, refuses to back up into the
# certificate directory, and reads the backup back before calling it a backup.
say "Certificate, trust anchor and backup"
"${COMPOSE[@]}" exec -T -e RMC_EDGE_TLS_CA_PASSPHRASE web \
  python manage.py edge_bootstrap --backup-to "$BUNDLE_IN_BOX" --terminator '' \
  || die "edge_bootstrap refused. Nothing has been changed. Read the reason above --
  it is a precondition, not a transient failure, and re-running will not clear it."

# --- 3. terminator config, rendered AFTER the certificate exists ------------
say "Terminator config"
TMP_CADDY="$(mktemp)"
trap 'rm -f "$TMP_CADDY"' EXIT
if ! "${COMPOSE[@]}" exec -T web python manage.py edge_bootstrap --print-caddyfile > "$TMP_CADDY"; then
  die "could not render the terminator config. The certificate step above must have
  succeeded first; the command refuses to render before a certificate exists,
  because doing so emits \`tls internal\` and serves Caddy's own CA."
fi
grep -qE '^[[:space:]]*tls[[:space:]]+/' "$TMP_CADDY" \
  || die "the rendered config does not point at this box's key pair. Refusing to
  install it. Contents:
$(sed 's/^/    /' "$TMP_CADDY")"
grep -qE '^[[:space:]]*tls[[:space:]]+internal' "$TMP_CADDY" \
  && die "the rendered config says \`tls internal\`, which serves Caddy's OWN CA --
  the ca.crt you distribute would match nothing this box presents. Refusing."

CADDY_CHANGED=0
if [ ! -f "$CADDYFILE" ] || ! cmp -s "$TMP_CADDY" "$CADDYFILE"; then
  cp "$TMP_CADDY" "$CADDYFILE"
  CADDY_CHANGED=1
  ok "written to $CADDYFILE"
else
  ok "already correct, unchanged"
fi
printf '        site line: %s\n' "$(grep -m1 -vE '^\s*#|^\s*$' "$CADDYFILE" | sed 's/ *{$//')"

# --- 4. start, and RESTART if anything changed ------------------------------
# `up -d` alone does not reload a bind-mounted file, and it does not reload a
# certificate the running Caddy read at its last config load. A box whose address
# changed heals its files and then serves the old certificate until this happens --
# looking healthy in every log it writes.
say "Terminator"
"${COMPOSE[@]}" --profile tls up -d edge-tls >/dev/null
"${COMPOSE[@]}" --profile tls restart edge-tls >/dev/null
ok "started and restarted, so it is holding the current certificate"
[ "$CADDY_CHANGED" = "1" ] && ok "config had changed, which is why the restart matters"

# --- 5. get the CA and the backup off the box -------------------------------
say "Off-box copies"
"${COMPOSE[@]}" cp "web:$BUNDLE_IN_BOX" "$OUT_DIR/box-ca-bundle.p12" >/dev/null
ok "$OUT_DIR/box-ca-bundle.p12   (encrypted CA backup -- move this OFF this machine)"
"${COMPOSE[@]}" exec -T web rm -f "$BUNDLE_IN_BOX" >/dev/null 2>&1 || true
ok "removed the bundle from inside the container"
"${COMPOSE[@]}" cp "web:/app/var/edge-tls/ca.crt" "$OUT_DIR/box-ca.crt" >/dev/null
ok "$OUT_DIR/box-ca.crt          (public CA certificate -- this is what devices install)"

# --- 6. verify against what is ACTUALLY being served ------------------------
say "Verification"
"${COMPOSE[@]}" exec -T web python manage.py edge_tls --check-terminator edge-tls:443 \
  || die "the terminator is not serving the certificate on disk. It did not pick up
  the restart. Check \`docker compose -f $COMPOSE_FILE logs edge-tls\`."
"${COMPOSE[@]}" exec -T web python manage.py check_edge_readiness --strict \
  || die "readiness is not clean. The box is NOT ready for devices yet; fix the
  findings above and run this script again."

# --- 7. the enrolment URL, so nobody carries a file to thirty devices -------
# Devices install the CA by browsing to the box, not by being handed box-ca.crt on
# a USB stick.
#
# ASKED FOR, not derived here. Building this URL in shell needs the published port
# and the which-of-our-names-do-we-hand-out rule, and both already exist inside the
# app -- where they are tested. A shell copy is a second answer that drifts, and it
# drifts into a URL nobody can open. `tr -d` strips the CR that Compose adds on
# some hosts, which would otherwise land in the middle of the printed line.
TRUST_URL="$("${COMPOSE[@]}" exec -T web python manage.py edge_tls --trust-url \
  2>/dev/null | tr -d '\r' | head -1)"
if [ -z "$TRUST_URL" ]; then
  # The box holds no address a device could reach. Say so rather than printing a
  # URL with a hole in it -- somebody would try it.
  TRUST_URL="(this box has no reachable address -- see ALLOWED_HOSTS)"
fi

cat <<BANNER

$(printf '\033[32m== Box is ready.\033[0m')

Send every device here, on the school wifi:

  $(printf '\033[1m%s\033[0m' "$TRUST_URL")

That page shows this box's fingerprint, a QR code so a phone does not have to type
an address, and the certificate itself. PLAIN http on purpose -- a device reaches
it precisely because it does not trust the box yet, and sending it to https would
show the very warning it came to fix.

Have whoever installs it compare the fingerprint on that page against the one
\`manage.py edge_tls\` prints on this console. Over http that comparison is the only
thing standing between a school and somebody else's certificate authority.

Two things still need a person:

  1. Move  $OUT_DIR/box-ca-bundle.p12  off this machine, and store the passphrase
     somewhere else again. Together in one place, the encryption bought you nothing.
     It carries the CA PRIVATE KEY and is never the file you hand to a device.
  2. Re-enrol offline PIN on each device at the https origin. Nothing carries over
     from the old one, and it could never have sealed there anyway.

Managed Chromebooks and supervised iPads are still an admin-console push rather
than a per-device visit; if nobody here holds that console, read the runbook.

Re-run this script any time. On a correct box it changes nothing.
BANNER
