#!/usr/bin/env bash
#
# Put a school's database back, from the box's own encrypted backup.
#
#   bash deploy/selfhost/box-restore.sh --list
#   bash deploy/selfhost/box-restore.sh --yes-destroy-current-data
#   bash deploy/selfhost/box-restore.sh --file rmc-box-db-20260830T020000Z.dump.enc --yes-destroy-current-data
#
# WHY A SCRIPT AND NOT A RUNBOOK. This is the one procedure on the box that gets run
# by somebody having the worst day of their term, usually in a corridor, usually on a
# phone. A twelve-step list of docker commands is where the ordering mistakes come
# from -- and here the ordering is the whole thing: restoring while gunicorn and
# celery are still writing gives you a database that is half yesterday and half this
# morning, with no way to tell which rows are which. So the stopping, the restoring
# and the starting are one command, and the starting happens on EVERY exit path
# including a Ctrl-C, because a box left stopped is a school with no system at all.
#
# The restore itself runs inside the backup container, which owns the passphrase and
# the read-back. It refuses a dump that does not read back -- there is no sense in
# dropping a working database for a file we already know is broken.
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
COMPOSE_FILE="$HERE/docker-compose.yml"
COMPOSE=(docker compose -f "$COMPOSE_FILE")
APP_SERVICES=(web worker beat)
WHICH="latest"
CONFIRMED=0
LIST_ONLY=0
STOPPED=0

say()  { printf '\n\033[1m== %s\033[0m\n' "$*"; }
ok()   { printf '   \033[32mok\033[0m   %s\n' "$*"; }
warn() { printf '   \033[33mwarn\033[0m %s\n' "$*"; }
die()  { printf '\n\033[31mSTOPPED\033[0m %s\n\n' "$*" >&2; exit 1; }

# The app comes back no matter how this script ends. A failed restore is recoverable;
# a box nobody restarted is a school locked out until somebody notices.
restart_app() {
  if [ "$STOPPED" = "1" ]; then
    printf '\n'
    say "Starting the app again"
    "${COMPOSE[@]}" start "${APP_SERVICES[@]}" >/dev/null 2>&1 \
      && ok "web, worker and beat are running again" \
      || warn "could not start them from here -- run: docker compose -f $COMPOSE_FILE start ${APP_SERVICES[*]}"
  fi
}
trap restart_app EXIT

while [ "$#" -gt 0 ]; do
  case "$1" in
    --list) LIST_ONLY=1; shift ;;
    --file) WHICH="${2:-}"; shift 2 ;;
    --yes-destroy-current-data) CONFIRMED=1; shift ;;
    -h|--help)
      sed -n '2,20p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'
      exit 0
      ;;
    *) die "unknown argument '$1'. Run with --help." ;;
  esac
done

command -v docker >/dev/null 2>&1 || die "docker is not on PATH."
[ -f "$COMPOSE_FILE" ] || die "no compose file at $COMPOSE_FILE"
"${COMPOSE[@]}" ps --status running --services 2>/dev/null | grep -qx backup \
  || die "the 'backup' service is not running, so nothing here can read the backups.

  Start it:  docker compose -f $COMPOSE_FILE up -d backup"

if [ "$LIST_ONLY" = "1" ]; then
  say "Backups on this box (newest first)"
  "${COMPOSE[@]}" exec -T backup bash /usr/local/bin/box-backup.sh list \
    | awk -F '\t' '{ printf "   %10.1f MiB  %s\n", $1 / 1048576, $2 }'
  printf '\n'
  say "What the box records about them"
  "${COMPOSE[@]}" exec -T backup bash /usr/local/bin/box-backup.sh status | sed 's/^/   /'
  exit 0
fi

if [ "$CONFIRMED" != "1" ]; then
  die "this REPLACES the school's live database with the contents of a backup.
  Everything entered since that backup was taken is gone, and there is no undo.

  See what is available first:
      bash $HERE/box-restore.sh --list

  Then, when you are sure:
      bash $HERE/box-restore.sh --yes-destroy-current-data"
fi

say "The dump"
"${COMPOSE[@]}" exec -T backup bash /usr/local/bin/box-backup.sh list | head -3 \
  | awk -F '\t' '{ printf "   %10.1f MiB  %s\n", $1 / 1048576, $2 }'
ok "restoring: $WHICH"

# Stop the writers BEFORE the restore, not after. `stop` and not `down`: the
# containers keep their identity and their volumes, so starting them again is a
# second of work rather than a rebuild.
say "Stopping the app (the database stays up -- the restore needs it)"
"${COMPOSE[@]}" stop "${APP_SERVICES[@]}" >/dev/null
STOPPED=1
ok "web, worker and beat are stopped; nothing is writing to the database now"

say "Restoring"
# `--single-transaction` inside the container means a failure rolls the whole thing
# back rather than leaving half a school in place, so a refusal here is safe.
if "${COMPOSE[@]}" exec -T backup bash /usr/local/bin/box-backup.sh \
     restore "$WHICH" --yes-destroy-current-data; then
  ok "the database has been restored"
else
  # The trap still starts the app, on the data that was there before. Say so plainly:
  # somebody is going to read this line and decide what to do next.
  die "the restore did NOT complete. It ran in one transaction, so the database is
  as it was before this started, and the app is being started again on it.
  Read the reason above before trying a different dump."
fi

say "Checking the box afterwards"
# Migrations run on web's boot, so a dump older than the running code is brought
# forward by simply starting the app. That is why the check comes after the start.
restart_app
STOPPED=0
"${COMPOSE[@]}" exec -T web python manage.py check_edge_readiness 2>&1 \
  | sed 's/\x1b\[[0-9;]*m//g' | grep -E "^\[FAIL\]|Edge readiness:" | sed 's/^/   /' \
  || warn "readiness did not report -- the web container may still be applying migrations"

cat <<'BANNER'

== Restored.

Two things to do now, and neither can be done from here:

  1. Have somebody who uses the system every day open it and confirm the last
     thing they remember doing is there. A restore that ran cleanly onto the
     wrong dump looks identical to one that ran cleanly onto the right one.
  2. Work out what was entered between the backup and now, and re-enter it.
     Nothing on this box knows what that was.

The next scheduled backup will run on its usual cadence and will read itself back
as always. If you want one immediately:

  docker compose -f deploy/selfhost/docker-compose.yml exec backup \
    bash /usr/local/bin/box-backup.sh once
BANNER
