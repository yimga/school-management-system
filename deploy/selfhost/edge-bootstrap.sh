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

# Where a generated passphrase is kept. Overridable, because the right answer on a
# box with a mounted secrets volume is not the default one -- and the default has to
# be somewhere, so it may as well be somewhere findable.
PASSPHRASE_FILE="${RMC_EDGE_CA_PASSPHRASE_FILE:-$OUT_DIR/box-ca-passphrase.txt}"

new_passphrase() {
  # `head -c` closes the pipe, and a closed pipe under `set -o pipefail` fails the
  # script. Turned off inside this subshell only: pipefail is doing real work in
  # every other pipeline here, and disabling it globally to fix one line is how a
  # later failure gets swallowed.
  ( set +o pipefail; LC_ALL=C tr -dc 'A-Za-z0-9' < /dev/urandom 2>/dev/null | head -c 44 )
}

say()  { printf '\n\033[1m== %s\033[0m\n' "$*"; }
ok()   { printf '   \033[32mok\033[0m   %s\n' "$*"; }
warn() { printf '   \033[33mwarn\033[0m %s\n' "$*"; }
die()  { printf '\n\033[31mSTOPPED\033[0m %s\n\n' "$*" >&2; exit 1; }

# --- 0. preconditions -------------------------------------------------------
say "Preconditions"
command -v docker >/dev/null 2>&1 || die "docker is not on PATH."
[ -f "$COMPOSE_FILE" ] || die "no compose file at $COMPOSE_FILE"
[ -f "$HERE/.env" ] || die "no $HERE/.env -- copy .env.edge.example and fill it in first."

# The passphrase encrypts the CA backup. Still taken from the environment and never
# from a flag -- a command line is visible in ps, in shell history and in docker's own
# event log. What changed is that not having one is no longer a reason to stop: an
# operator who is made to invent a secret here either picks a weak one or loses it,
# and both of those end with an unrecoverable box.
if [ -z "${RMC_EDGE_TLS_CA_PASSPHRASE:-}" ]; then
  if [ -s "$PASSPHRASE_FILE" ]; then
    # Reused, not regenerated. A second passphrase would re-encrypt the bundle and
    # silently strand whatever copy is already off the box.
    RMC_EDGE_TLS_CA_PASSPHRASE="$(tr -d '\r\n' < "$PASSPHRASE_FILE")"
    ok "passphrase read from $PASSPHRASE_FILE"
  else
    RMC_EDGE_TLS_CA_PASSPHRASE="$(new_passphrase)"
    [ "${#RMC_EDGE_TLS_CA_PASSPHRASE}" -ge 32 ] || die "could not generate a passphrase
  (/dev/urandom unreadable?). Set RMC_EDGE_TLS_CA_PASSPHRASE yourself and run again."
    ( umask 077; printf '%s\n' "$RMC_EDGE_TLS_CA_PASSPHRASE" > "$PASSPHRASE_FILE" )
    ok "generated a passphrase and wrote it to $PASSPHRASE_FILE (owner-only)"
    warn "it is currently in the same place as the backup it protects. Moving one of
       the two elsewhere is the last item in this run's closing notes."
  fi
  export RMC_EDGE_TLS_CA_PASSPHRASE
fi
ok "docker, compose file and .env all present"

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
trap 'rm -f "$TMP_CADDY"; [ -n "${MDM_TMP:-}" ] && rm -rf "$MDM_TMP"; true' EXIT
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

# --- 5b. what a device-management console needs, asked for or not -----------
# Written on every run rather than on request. The command that produces these is one
# nobody remembers exists, and a school that manages its devices should never walk the
# building at all: one console push installs the CA on every enrolled device, and on
# Apple hardware a PUSHED profile is trusted on arrival where a hand-installed one
# still needs the Certificate Trust Settings screen.
say "Management-console payloads"
MDM_TMP="$(mktemp -d)"
# Copied via a temp directory and moved into place: `docker compose cp` of a
# directory copies INTO an existing target, so a second run would otherwise leave
# $OUT_DIR/mdm/mdm and a stale copy above it.
if "${COMPOSE[@]}" exec -T web python manage.py edge_tls --export-mdm /app/var/mdm >/dev/null \
   && "${COMPOSE[@]}" cp web:/app/var/mdm "$MDM_TMP/" >/dev/null 2>&1 \
   && [ -d "$MDM_TMP/mdm" ]; then
  rm -rf "$OUT_DIR/mdm"
  mv "$MDM_TMP/mdm" "$OUT_DIR/mdm"
  ok "$OUT_DIR/mdm/              (push these from your console instead of visiting devices)"
  for f in "$OUT_DIR"/mdm/*; do
    [ -e "$f" ] || continue   # an unmatched glob is the literal pattern, not nothing
    printf '        %s\n' "$(basename "$f")"
  done
else
  # Never fatal. These are a convenience for a fleet console, and a box whose TLS is
  # correct is not less correct because a folder could not be copied off it.
  warn "could not write the management-console payloads -- everything else is fine.
       Run it by hand with:
         docker compose -f $COMPOSE_FILE exec web python manage.py edge_tls --export-mdm /app/var/mdm"
fi

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
an address, and -- on Windows, macOS and Linux -- a single command that fetches the
certificate, checks its fingerprint and installs it only on a match. PLAIN http on
purpose: a device reaches it precisely because it does not trust the box yet, and
sending it to https would show the very warning it came to fix.

Have whoever installs it compare the fingerprint on that page against the one
\`manage.py edge_tls\` prints on this console. Over http that comparison is the only
thing standing between a school and somebody else's certificate authority, and no
command can make it for you: a page that lied about the certificate would lie about
the fingerprint printed beside it too.

IF THE SCHOOL MANAGES ITS DEVICES, NOBODY VISITS A DEVICE AT ALL. Push
$OUT_DIR/mdm/ from the console -- box-ca.mobileconfig to Jamf / Mosyle / Kandji /
Intune, box-ca.crt to Google Admin or Group Policy, android-policy.json into an
Android Enterprise policy. On managed Chromebooks and supervised iPads a per-device
install does not stick, and on Android 11+ a hand-installed authority is ignored by
apps -- so there this is not the convenient route, it is the only one.

Two things still need a person, and neither can be automated from here:

  1. Move ONE of these off this machine, so they stop sitting together:
       $OUT_DIR/box-ca-bundle.p12       the encrypted CA backup
       $PASSPHRASE_FILE
     In one place the encryption bought you nothing. The bundle carries the CA
     PRIVATE KEY and is never the file you hand to a device. It is also the only
     artefact on this box that cannot be regenerated.
  2. Re-enrol offline PIN on each device at the https origin. Nothing carries over
     from the old one, and it could never have sealed there anyway.

Re-run this script any time. On a correct box it changes nothing.
BANNER
