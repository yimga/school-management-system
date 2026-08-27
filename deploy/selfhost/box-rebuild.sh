#!/usr/bin/env bash
# Rebuild this box onto the code in its own checkout -- and prove it took.
#
# THE TRAP THIS EXISTS TO CLOSE. The containers run a BAKED image. `git pull` in
# /srv/rmc changes the checkout and nothing else: the running code is whatever was
# compiled into `runmycampus-selfhost:latest`, and `docker compose up -d` WITHOUT
# `--build` happily restarts the old image. Every check then passes -- against the
# old code. `edge-bootstrap.sh` used to make this worse by telling the operator, in
# its own error message, to run `up -d` with no `--build`.
#
# Measured on the Gilead box on 2026-08-27: the checkout was at d2ec46fce and the
# running image had been built from 5869d6422 -- SIX commits and 877 lines behind,
# including the CA-passphrase guard written specifically for that box. Nothing on
# the box said so. Nothing could: the only place the answer lives is
# /app/.build-stamp.json inside the image, and no one thinks to look there.
#
# So the last thing this script does is compare the NEW stamp against the checkout
# and REFUSE to report success if they disagree. A rebuild that silently no-ops is
# the failure mode; a rebuild that says it worked when it did not is worse.
#
# Usage:
#   ./box-rebuild.sh --check     report drift, change NOTHING, exit 1 if behind
#   ./box-rebuild.sh             pull, rebuild, recreate, verify
#   ./box-rebuild.sh --no-pull   rebuild from the checkout exactly as it stands
#
set -uo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$HERE/../.." && pwd)"
COMPOSE_FILE="$HERE/docker-compose.yml"
COMPOSE=(docker compose -f "$COMPOSE_FILE")
STAMP_IN_IMAGE="/app/.build-stamp.json"

CHECK_ONLY=0
DO_PULL=1
for arg in "$@"; do
  case "$arg" in
    --check)    CHECK_ONLY=1 ;;
    --no-pull)  DO_PULL=0 ;;
    -h|--help)  sed -n '2,28p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'; exit 0 ;;
    *) echo "unknown argument: $arg (try --help)" >&2; exit 2 ;;
  esac
done

# --- output ------------------------------------------------------------------
# A rebuild on a box in a school office is watched by somebody who wants to know
# whether it is safe to walk away. Numbered steps and a bar, not a wall of docker.
TOTAL_STEPS=7
STEP=0

if [ -t 1 ]; then B=$'\033[1m'; G=$'\033[32m'; Y=$'\033[33m'; R=$'\033[31m'; N=$'\033[0m'
else B=""; G=""; Y=""; R=""; N=""; fi

bar() {
  local done_n="$1" width=32 filled i out=""
  filled=$(( done_n * width / TOTAL_STEPS ))
  for ((i = 0; i < width; i++)); do
    if [ "$i" -lt "$filled" ]; then out="$out#"; else out="$out."; fi
  done
  printf '  [%s] %d/%d\n' "$out" "$done_n" "$TOTAL_STEPS"
}
step() { STEP=$((STEP + 1)); printf '\n%s[%d/%d] %s%s\n' "$B" "$STEP" "$TOTAL_STEPS" "$*" "$N"; }
ok()   { printf '  %sOK%s   %s\n' "$G" "$N" "$*"; }
warn() { printf '  %sWARN%s %s\n' "$Y" "$N" "$*"; }
die()  { printf '\n  %sFAIL%s %s\n\n' "$R" "$N" "$*" >&2; exit 1; }

short() { printf '%.9s' "$1"; }

# Reads the commit the RUNNING web container was built from. Empty when the
# container is down or the image predates the stamp.
running_commit() {
  docker exec "$(container_id)" cat "$STAMP_IN_IMAGE" 2>/dev/null \
    | tr -d ' ",' | sed -n 's/^commit_sha:\(.*\)$/\1/p' | head -1
}
container_id() { "${COMPOSE[@]}" ps -q web 2>/dev/null | head -1; }
checkout_commit() { git -C "$REPO_ROOT" rev-parse HEAD 2>/dev/null; }

printf '%sRunMyCampus box rebuild%s   %s\n' "$B" "$N" "$REPO_ROOT"

# --- 1. can we act at all? ---------------------------------------------------
step "Preflight"
command -v docker >/dev/null 2>&1 || die "docker is not installed or not on PATH."
docker info >/dev/null 2>&1 || die "docker is installed but not responding. Is the daemon running?"
[ -f "$COMPOSE_FILE" ] || die "no compose file at $COMPOSE_FILE"
[ -f "$HERE/.env" ] || die "no .env at $HERE/.env -- this box has never been bootstrapped."
ok "docker, compose file and .env all present"

# A build is the most expensive thing this box will do. Boxes run on cheap
# hardware, and a build that dies half way leaves a dangling layer set and a
# confused operator. Say the numbers BEFORE spending twenty minutes on them.
AVAIL_KB="$(df -Pk "$REPO_ROOT" 2>/dev/null | awk 'NR==2 {print $4}')"
if [ -n "${AVAIL_KB:-}" ]; then
  AVAIL_GB=$(( AVAIL_KB / 1024 / 1024 ))
  if [ "$AVAIL_GB" -lt 3 ]; then
    warn "only ${AVAIL_GB}GB free on this filesystem -- a build needs a few GB of layer space"
    warn "reclaim some first:  docker image prune -f"
  else
    ok "${AVAIL_GB}GB free for build layers"
  fi
fi
bar 1

# --- 2. what is actually running right now? ----------------------------------
step "What this box is running"
CID="$(container_id)"
BEFORE_COMMIT=""
if [ -n "$CID" ]; then
  BEFORE_COMMIT="$(running_commit)"
fi
HEAD_COMMIT="$(checkout_commit)"
[ -n "$HEAD_COMMIT" ] || die "$REPO_ROOT is not a git checkout -- cannot tell what code it should run."

if [ -z "$CID" ]; then
  warn "web is not running, so nothing is serving this box's code right now"
elif [ -z "$BEFORE_COMMIT" ]; then
  warn "the running image carries no build stamp (built before stamping existed)"
  warn "there is no way to tell what code it is running -- rebuilding is the only way to know"
else
  ok "running:  $(short "$BEFORE_COMMIT")"
fi
ok "checkout: $(short "$HEAD_COMMIT")"

if [ -n "$BEFORE_COMMIT" ] && [ "$BEFORE_COMMIT" = "$HEAD_COMMIT" ]; then
  ok "the box is running its own checkout"
  DRIFTED=0
else
  DRIFTED=1
  BEHIND="$(git -C "$REPO_ROOT" rev-list --count "${BEFORE_COMMIT:-HEAD}..HEAD" 2>/dev/null || echo "")"
  if [ -n "$BEHIND" ] && [ "$BEHIND" != "0" ]; then
    warn "the running image is ${BEHIND} commit(s) behind this checkout"
  else
    warn "the running image was built from different code than this checkout"
  fi
fi
bar 2

if [ "$CHECK_ONLY" = "1" ]; then
  printf '\n'
  if [ "$DRIFTED" = "1" ]; then
    printf '%sDRIFTED%s -- this box is not running its own checkout. Rebuild with:\n' "$Y" "$N"
    printf '    %s\n\n' "$HERE/box-rebuild.sh"
    exit 1
  fi
  printf '%sCURRENT%s -- the running image matches the checkout. Nothing to do.\n\n' "$G" "$N"
  exit 0
fi

# --- 3. move the checkout ----------------------------------------------------
step "Update the checkout"
if [ "$DO_PULL" = "0" ]; then
  ok "--no-pull: building from the checkout exactly as it stands"
elif ! git -C "$REPO_ROOT" diff --quiet 2>/dev/null; then
  # Never discard work this script did not create. A dirty tree here is usually a
  # rendered artefact (Caddyfile.edge) but it can be somebody's edit, and guessing
  # wrong destroys it.
  warn "the checkout has uncommitted changes -- NOT pulling over them"
  git -C "$REPO_ROOT" status --short 2>/dev/null | sed 's/^/       /' | head -10
  warn "resolve those first, or re-run with --no-pull to build them as they are"
elif ! GIT_TERMINAL_PROMPT=0 timeout 60 git -C "$REPO_ROOT" fetch origin >/dev/null 2>&1; then
  # Offline is the normal state for a box in a school. It is not an error, and it
  # must never block a rebuild of code that is already on disk.
  warn "could not reach the git remote (offline, or no stored credential)"
  ok "building from the checkout as it stands"
else
  BRANCH="$(git -C "$REPO_ROOT" rev-parse --abbrev-ref HEAD 2>/dev/null || echo main)"
  if git -C "$REPO_ROOT" merge --ff-only "origin/$BRANCH" >/dev/null 2>&1; then
    HEAD_COMMIT="$(checkout_commit)"
    ok "fast-forwarded to $(short "$HEAD_COMMIT")"
  else
    warn "cannot fast-forward $BRANCH -- the checkout has diverged from origin"
    ok "building from the checkout as it stands"
  fi
fi
bar 3

# --- 4. the step that actually changes the code ------------------------------
step "Build the image"
printf '  this is the long one -- several minutes on box hardware\n'
if ! GIT_COMMIT="$HEAD_COMMIT" BUILD_TIME="$(date -u +%Y-%m-%dT%H:%M:%SZ)" \
     "${COMPOSE[@]}" build web 2>&1 | sed 's/^/       /'; then
  die "the image build failed. The box is UNCHANGED and still serving the old image,
  which is the safe outcome. Read the output above; the usual causes are a full
  disk and a package index that needs the network."
fi
ok "image built and stamped $(short "$HEAD_COMMIT")"
bar 4

# --- 5. swap the containers onto it ------------------------------------------
step "Recreate the containers"
# The entrypoint runs migrations and check_edge_readiness on the way up, so there
# is deliberately no separate migrate step here -- two places that migrate is one
# place too many.
if ! "${COMPOSE[@]}" up -d 2>&1 | sed 's/^/       /'; then
  die "containers failed to come up. \`docker compose -f $COMPOSE_FILE logs web\` will say why."
fi
ok "containers recreated"
bar 5

# --- 6. wait for it to actually serve ----------------------------------------
step "Wait for web to answer"
DEADLINE=$(( $(date +%s) + 300 ))
HEALTHY=0
while [ "$(date +%s)" -lt "$DEADLINE" ]; do
  CID="$(container_id)"
  if [ -n "$CID" ]; then
    STATE="$(docker inspect "$CID" --format '{{if .State.Health}}{{.State.Health.Status}}{{else}}{{.State.Status}}{{end}}' 2>/dev/null)"
    case "$STATE" in
      healthy|running) HEALTHY=1; break ;;
      exited|dead) die "the web container exited during startup.
  \`docker compose -f $COMPOSE_FILE logs web\` will say why. Migrations run on the way
  up, so a failure here is usually a migration, not the build." ;;
    esac
  fi
  sleep 3
done
[ "$HEALTHY" = "1" ] || die "web did not become healthy within 5 minutes.
  Check \`docker compose -f $COMPOSE_FILE logs web\`. The old image is gone, so this
  needs resolving rather than leaving."
ok "web is up"
bar 6

# --- 7. prove it -------------------------------------------------------------
step "Prove the box is running the new code"
# The whole reason this script exists. Everything above can succeed while the
# running code stays exactly where it was.
AFTER_COMMIT="$(running_commit)"
if [ -z "$AFTER_COMMIT" ]; then
  die "the new container reports no build stamp at $STAMP_IN_IMAGE.
  Something is serving an image this script did not build. Do NOT treat this box as
  updated."
fi
if [ "$AFTER_COMMIT" != "$HEAD_COMMIT" ]; then
  die "the box is running $(short "$AFTER_COMMIT") but the checkout is $(short "$HEAD_COMMIT").
  The rebuild did not take. Do NOT treat this box as updated."
fi
ok "running $(short "$AFTER_COMMIT") -- matches the checkout"
if [ -n "$BEFORE_COMMIT" ] && [ "$BEFORE_COMMIT" != "$AFTER_COMMIT" ]; then
  ok "moved from $(short "$BEFORE_COMMIT") to $(short "$AFTER_COMMIT")"
fi
bar 7

printf '\n%sDone.%s This box is running its own checkout.\n\n' "$G" "$N"
printf 'Next, if TLS or trust changed:\n'
printf '    %s/edge-bootstrap.sh\n' "$HERE"
printf 'To confirm at any time without changing anything:\n'
printf '    %s/box-rebuild.sh --check\n\n' "$HERE"
