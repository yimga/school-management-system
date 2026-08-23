#!/usr/bin/env bash
# Blue-green release layout for an edge box, so a FULL OTA upgrade can actually swap.
#
# WHY THIS EXISTS. The ordinary image is one tree: `COPY . .` into /app, and gunicorn
# serves from there. A full-lane upgrade (python + migrations) cannot be made atomic in
# that shape -- you would be overwriting .py files under a live interpreter -- so
# `local_upgrade` correctly REFUSES and reports "deferred: apply with an image rebuild".
# That is honest, and it also means the full lane never actually runs on a real box.
#
# The fix is the capistrano shape the rollout manager already knows how to drive:
#
#     $RMC_OTA_RELEASE_ROOT/releases/<manifest-prefix>/   one whole tree per release
#     $RMC_OTA_RELEASE_ROOT/current -> releases/<...>     one symlink, flipped atomically
#
# The manager builds the next release beside the current one, verifies it, and repoints
# `current` with a single rename. Nothing being served changes until that call, and going
# back is the same call with the old target.
#
# OPT-IN, and deliberately so. With RMC_OTA_RELEASE_ROOT unset the box boots exactly as it
# did before this file existed. An appliance that fails to boot is far worse than one that
# defers an upgrade, so this must never be something a deployment gets by accident.
#
# REQUIRES A VOLUME. The releases live outside the image; on a container without a mount
# at RMC_OTA_RELEASE_ROOT every restart discards them and re-seeds, which works but throws
# away the rollback target. deploy/selfhost/docker-compose.yml carries the volume and
# the mount, both commented out beside RMC_OTA_RELEASE_ROOT -- uncomment the three
# together or not at all.

set -o errexit
set -o nounset
set -o pipefail

# Headroom over the measured tree size before we are willing to seed a release. The copy
# is roughly one whole tree; anything tighter and a school on a small disk buys a full
# filesystem, which stops Postgres writing and takes the whole appliance down -- far worse
# than never having had the release layout at all.
: "${RMC_OTA_RELEASE_HEADROOM_PCT:=140}"

# Seed the layout if it is not there yet, and echo the directory the web server should
# run from. Idempotent: an existing `current` is left alone, because re-seeding on every
# boot would copy the whole tree each start AND destroy the rollback target.
#
# THIS FUNCTION NEVER FAILS THE BOOT. Every path out of it echoes a directory that exists
# and returns 0. If the disk is too small, the volume is not mounted, the filesystem has
# no symlinks, or the copy breaks halfway, the box boots on the live tree and full-lane
# upgrades go on deferring exactly as they did before this file existed. A school whose
# box does not start is in far more trouble than a school whose box needs an image
# rebuild to take a code upgrade -- and the schools most likely to hit any of these are
# the ones on the cheapest hardware, who can least afford an outage.
rmc_release_layout_prepare() {
  local root="${1:?release root required}"
  local live="${2:?live tree required}"
  local current="${root}/current"

  if [[ -L "${current}" && -d "${current}" ]]; then
    echo "${current}"
    return 0
  fi

  if ! mkdir -p "${root}/releases" 2>/dev/null; then
    echo "[selfhost] WARNING: cannot create ${root}/releases -- is the volume mounted?" >&2
    echo "[selfhost]          Serving the live tree; full-lane upgrades will defer." >&2
    echo "${live}"
    return 0
  fi

  # First boot on a release layout. Seed one release from the image so `current` always
  # points at a COMPLETE tree -- the manager copies the current release forward when it
  # builds the next one, so a partial seed would poison every future upgrade.
  local seed
  seed="$(cat "${live}/.build-stamp.json" 2>/dev/null | sed -n 's/.*"commit_sha"[[:space:]]*:[[:space:]]*"\([0-9a-f]\{7,12\}\).*/\1/p' | head -1)"
  if [[ -z "${seed}" ]]; then
    seed="image"
  fi

  if [[ ! -d "${root}/releases/${seed}" ]]; then
    # Measure BEFORE copying. POSIX -k mode on both, so this reads the same on the
    # busybox coreutils a small ARM image ships as it does on GNU.
    local need_kb avail_kb want_kb
    need_kb="$(du -sk "${live}" 2>/dev/null | awk '{print $1}')"
    avail_kb="$(df -Pk "${root}" 2>/dev/null | awk 'NR==2 {print $4}')"
    if [[ -n "${need_kb}" && -n "${avail_kb}" ]]; then
      want_kb=$(( need_kb * RMC_OTA_RELEASE_HEADROOM_PCT / 100 ))
      if (( avail_kb < want_kb )); then
        echo "[selfhost] WARNING: the release layout needs ~$(( want_kb / 1024 ))MB free at" >&2
        echo "[selfhost]          ${root}, and only $(( avail_kb / 1024 ))MB is available. NOT seeding." >&2
        echo "[selfhost]          Serving the live tree; full-lane upgrades will defer to an" >&2
        echo "[selfhost]          image rebuild. Give the volume more room, or leave" >&2
        echo "[selfhost]          RMC_OTA_RELEASE_ROOT unset on this box." >&2
        echo "${live}"
        return 0
      fi
    fi

    echo "[selfhost] seeding the release layout at ${root}/releases/${seed}: a one-time" >&2
    echo "[selfhost] copy of ~$(( ${need_kb:-0} / 1024 ))MB. On a slow disk this adds a minute to first boot." >&2
    # Copy into a .partial name, so an interrupted copy can never be mistaken for a
    # complete release -- not by this function, and not by the upgrade manager when it
    # copies the current release forward to build the next one.
    rm -rf "${root}/releases/${seed}.partial"
    if ! mkdir -p "${root}/releases/${seed}.partial" 2>/dev/null \
       || ! cp -a "${live}/." "${root}/releases/${seed}.partial/" 2>/dev/null; then
      echo "[selfhost] WARNING: seeding failed -- out of space, or a permissions problem." >&2
      echo "[selfhost]          Serving the live tree; nothing was left half-linked." >&2
      rm -rf "${root}/releases/${seed}.partial"
      echo "${live}"
      return 0
    fi
    mv -Tf "${root}/releases/${seed}.partial" "${root}/releases/${seed}"
  fi

  # Atomic even on first creation: build the link beside the target, then rename over.
  if ! ln -sfn "${root}/releases/${seed}" "${current}.tmp" 2>/dev/null \
     || ! mv -Tf "${current}.tmp" "${current}" 2>/dev/null; then
    echo "[selfhost] WARNING: could not create the ${current} symlink. Does this filesystem" >&2
    echo "[selfhost]          support them? Serving the live tree." >&2
    rm -f "${current}.tmp"
    echo "${live}"
    return 0
  fi
  echo "${current}"
}
