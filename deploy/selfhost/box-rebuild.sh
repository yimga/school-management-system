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
# THE SECOND TRAP, MEASURED ON THE SAME BOX ON 2026-08-28. Step 7 proves the image
# matches the CHECKOUT. Somebody typing this command is asking for the latest CODE,
# which is a different question, and step 3 is the only place that can answer it.
# That day the fetch failed for want of a stored credential; the script correctly
# built what was already on disk, and then printed "Done. This box is running its
# own checkout." Every word true. It was read as "updated", and the next command
# typed was a management-command flag that only exists in the commit which never
# arrived. So the summary now carries step 3's verdict to the end, and --check asks
# the remote itself -- read-only -- instead of reporting only on the image.
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
    # Derived from the header, not from a line range. '2,28p' meant "the header"
    # only for as long as the header was 28 lines; one paragraph more and --help
    # starts printing shell code. The marker cannot drift.
    -h|--help)  awk 'NR == 1 {next} /^set -uo pipefail/ {exit} {print}' "${BASH_SOURCE[0]}" \
                  | sed 's/^# \{0,1\}//'; exit 0 ;;
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

# One reader for every value a box configures in its own .env. The last assignment
# wins, quotes come off, and a CRLF line ending cannot smuggle a carriage return
# into the value -- a trailing CR made "off" compare unequal to "off" and started a
# terminator on a box that had no certificate to present.
env_value() {
  awk -F= -v key="$1" '
    $0 ~ "^[[:space:]]*" key "[[:space:]]*=" { v = $2 }
    END { gsub(/[^[:alnum:]_-]/, "", v); print v }
  ' "$HERE/.env" 2>/dev/null
}

# A FETCH BUDGET, NOT A FETCH DEADLINE. Sixty seconds was a guess, and a box on a
# school link does not fetch this repo in sixty seconds -- at which point `timeout`
# kills it and the script calls a slow link an unreachable remote. Environment beats
# .env beats the default, and anything that is not a plain number falls back rather
# than being handed to `timeout` to choke on.
FETCH_BUDGET="${RMC_GIT_FETCH_TIMEOUT:-$(env_value RMC_GIT_FETCH_TIMEOUT)}"
case "$FETCH_BUDGET" in
  ""|*[!0-9]*) FETCH_BUDGET=300 ;;
esac

# The TLS terminator runs behind a compose PROFILE, and a plain `up -d` does not
# start a profiled service. On a box that was fully down -- `compose down`, a disk
# swap, a rebuild after a stop -- that brings the stack back with NO HTTPS: :10000
# answers, :443 does not, and nothing in the output says why. So read the box's own
# configured mode and carry the profile when it has one. `off` is the default and
# must stay profile-less: starting Caddy on a box with no certificate binds :443 to
# a terminator that has nothing to present.
edge_tls_mode() { env_value RMC_EDGE_TLS_MODE; }
TLS_MODE="$(edge_tls_mode)"
PROFILE_ARGS=()
if [ -n "$TLS_MODE" ] && [ "$TLS_MODE" != "off" ]; then
  PROFILE_ARGS=(--profile tls)
fi
# ${arr[@]+...} because `set -u` and an empty array are not friends on older bash.
compose() { "${COMPOSE[@]}" ${PROFILE_ARGS[@]+"${PROFILE_ARGS[@]}"} "$@"; }

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
  # "Is this box current?" has two answers and step 2 only knows one of them. The
  # image can match the checkout perfectly while the CHECKOUT sits commits behind
  # origin -- and a rebuild, the thing CURRENT invites you to skip, would not move
  # it either. So ask the remote too.
  #
  # --check promises to change NOTHING, so this must not `fetch`: a fetch writes
  # remote-tracking refs into .git. `ls-remote` reads and writes nothing. It is
  # bounded and never prompts, because a box in a school office is usually offline
  # and an unreachable remote is not an error here -- it is one fewer thing known.
  BEHIND_UPSTREAM=0
  BRANCH="$(git -C "$REPO_ROOT" rev-parse --abbrev-ref HEAD 2>/dev/null || echo main)"
  REMOTE_TIP="$(GIT_TERMINAL_PROMPT=0 timeout 20 git -C "$REPO_ROOT" \
    ls-remote origin "refs/heads/$BRANCH" 2>/dev/null | awk 'NR == 1 {print $1}')"
  if [ -z "$REMOTE_TIP" ]; then
    warn "could not reach the git remote -- cannot tell whether the checkout is current"
  elif [ "$REMOTE_TIP" = "$HEAD_COMMIT" ]; then
    ok "the checkout is level with origin/$BRANCH"
  else
    warn "the checkout is behind origin/$BRANCH, which is at $(short "$REMOTE_TIP")"
    BEHIND_UPSTREAM=1
  fi

  printf '\n'
  if [ "$DRIFTED" = "1" ]; then
    printf '%sDRIFTED%s -- this box is not running its own checkout. Rebuild with:\n' "$Y" "$N"
    printf '    %s\n\n' "$HERE/box-rebuild.sh"
    exit 1
  fi
  if [ "$BEHIND_UPSTREAM" = "1" ]; then
    # A rebuild alone cannot fix this, so do not print the word that means "run a
    # rebuild". The checkout has to move first.
    printf '%sBEHIND%s -- the image matches the checkout, but the checkout is behind\n' "$Y" "$N"
    printf 'origin/%s. Move the checkout first, then rebuild:\n' "$BRANCH"
    printf '    git -C %s pull && %s/box-rebuild.sh\n\n' "$REPO_ROOT" "$HERE"
    exit 1
  fi
  if [ -n "$REMOTE_TIP" ]; then
    printf '%sCURRENT%s -- the image matches the checkout, and the checkout is level\n' "$G" "$N"
    printf 'with origin/%s. Nothing to do.\n\n' "$BRANCH"
  else
    printf '%sCURRENT%s -- the image matches the checkout. Whether the checkout itself\n' "$G" "$N"
    printf 'is the latest was NOT checked; the remote was unreachable.\n\n'
  fi
  exit 0
fi

# --- 3. move the checkout ----------------------------------------------------
step "Update the checkout"
# WHAT THIS STEP CAN ESTABLISH THAT NO LATER STEP CAN. Step 7 proves the running
# image matches the checkout. That is not the question somebody asks by typing this
# command -- they are asking for the latest code -- and the two answers only
# coincide when the checkout itself reached the remote. This is the only step that
# can know, so it records the verdict and the summary reads it back.
#
# UPSTREAM is set ONLY on a path that actually compared against the remote. Empty
# means "not established", which is different from "behind" and must never be
# rendered as "up to date".
UPSTREAM=""
CHECKOUT_NOTE=""
BRANCH="$(git -C "$REPO_ROOT" rev-parse --abbrev-ref HEAD 2>/dev/null || echo main)"
if [ "$DO_PULL" = "0" ]; then
  ok "--no-pull: building from the checkout exactly as it stands"
  CHECKOUT_NOTE="--no-pull was given, so the remote was never consulted"
elif ! git -C "$REPO_ROOT" diff --quiet 2>/dev/null; then
  # Never discard work this script did not create. A dirty tree here is usually a
  # rendered artefact (Caddyfile.edge) but it can be somebody's edit, and guessing
  # wrong destroys it.
  warn "the checkout has uncommitted changes -- NOT pulling over them"
  git -C "$REPO_ROOT" status --short 2>/dev/null | sed 's/^/       /' | head -10
  warn "resolve those first, or re-run with --no-pull to build them as they are"
  CHECKOUT_NOTE="the checkout has uncommitted changes, so it was not pulled"
else
  # NEVER NAME A CAUSE THIS DID NOT MEASURE. The old branch sent the fetch's stderr
  # to /dev/null and then asserted "offline, or no stored credential". On the Gilead
  # box on 2026-08-28 BOTH were false -- `git ls-remote` answered that same URL from
  # that same checkout with no prompt, returning the sha origin really was at. The
  # script was holding git's own message and threw it away, so an operator got a
  # guess, and the guess pointed at the network.
  #
  # A stopped fetch is a THIRD thing and the one a box is likeliest to hit. rc 124
  # is `timeout` killing a fetch that was working, which is a slow link, not an
  # outage, and it has a different remedy -- so it gets its own message.
  #
  # Offline remains the normal state for a box in a school. None of these block a
  # rebuild of code already on disk; they only decide what is said about it.
  BEFORE_PULL="$HEAD_COMMIT"
  FETCH_ERR="$(GIT_TERMINAL_PROMPT=0 timeout "$FETCH_BUDGET" \
    git -C "$REPO_ROOT" fetch origin 2>&1 >/dev/null)"
  FETCH_RC=$?
  if [ "$FETCH_RC" = "124" ]; then
    warn "the fetch was still running after ${FETCH_BUDGET}s and was stopped"
    warn "that is a slow link, not an outage. Give it longer:"
    warn "    RMC_GIT_FETCH_TIMEOUT=1200 $HERE/box-rebuild.sh"
    ok "building from the checkout as it stands"
    CHECKOUT_NOTE="the fetch was stopped after ${FETCH_BUDGET}s without finishing"
  elif [ "$FETCH_RC" != "0" ]; then
    warn "the fetch failed (exit $FETCH_RC). In git's own words:"
    printf '%s\n' "${FETCH_ERR:-(git said nothing)}" | sed 's/^/       /' | head -6
    ok "building from the checkout as it stands"
    CHECKOUT_NOTE="the fetch failed with exit $FETCH_RC -- git's message is above"
  elif git -C "$REPO_ROOT" merge --ff-only "origin/$BRANCH" >/dev/null 2>&1; then
  HEAD_COMMIT="$(checkout_commit)"
    # A successful ff-merge means BOTH "moved" and "was already there", and those
    # are worth telling apart: only one of them is news. Either way the checkout
    # has now been compared against the remote, which is what UPSTREAM records.
    if [ "$HEAD_COMMIT" = "$BEFORE_PULL" ]; then
      UPSTREAM="level"
      ok "the checkout is already level with origin/$BRANCH"
    else
      UPSTREAM="advanced"
      ok "fast-forwarded to $(short "$HEAD_COMMIT")"
    fi
  else
    warn "cannot fast-forward $BRANCH -- the checkout has diverged from origin"
    ok "building from the checkout as it stands"
    CHECKOUT_NOTE="the checkout has diverged from origin/$BRANCH and could not be fast-forwarded"
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
if [ -n "$TLS_MODE" ] && [ "$TLS_MODE" != "off" ]; then
  ok "TLS mode is '$TLS_MODE' -- bringing the terminator up with the stack"
fi
if ! compose up -d 2>&1 | sed 's/^/       /'; then
  die "containers failed to come up. \`docker compose -f $COMPOSE_FILE logs web\` will say why."
fi
ok "containers recreated"

# A box in a TLS mode whose terminator is not running has no HTTPS at all. The
# rebuild itself may have gone perfectly; saying so and stopping there is how an
# operator walks away from a box that half works.
if [ -n "$TLS_MODE" ] && [ "$TLS_MODE" != "off" ]; then
  TLS_CID="$(compose ps -q edge-tls 2>/dev/null | head -1)"
  if [ -z "$TLS_CID" ]; then
    die "TLS mode is '$TLS_MODE' but the terminator did not start, so nothing is
  serving HTTPS on this box. \`docker compose -f $COMPOSE_FILE --profile tls logs edge-tls\`
  will say why. The code rebuild itself succeeded."
  fi
  ok "terminator running"
fi
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

# THE SUMMARY MUST NOT FORGET STEP 3. This is where somebody decides whether to
# walk away. "Done" means one thing here -- the image matches the checkout -- and it
# is read as another. A warning printed four steps and several minutes of build log
# ago is not a caveat anybody still has on screen.
printf '\n%sDone.%s This box is running its own checkout, %s.\n' "$G" "$N" "$(short "$AFTER_COMMIT")"
if [ -n "$UPSTREAM" ]; then
  printf '%sUp to date%s with origin/%s.\n\n' "$G" "$N" "$BRANCH"
else
  printf '\n%sThe checkout was NOT updated%s -- %s.\n' "$Y" "$N" "${CHECKOUT_NOTE:-the remote was not consulted}"
  printf 'So this box is running the code that was already on disk. Whether that is\n'
  printf 'the latest has NOT been established. To find out:\n'
  printf '    git -C %s fetch origin && git -C %s status -sb\n\n' "$REPO_ROOT" "$REPO_ROOT"
fi
printf 'Next, if TLS or trust changed:\n'
printf '    %s/edge-bootstrap.sh\n' "$HERE"
printf 'To confirm at any time without changing anything:\n'
printf '    %s/box-rebuild.sh --check\n\n' "$HERE"
