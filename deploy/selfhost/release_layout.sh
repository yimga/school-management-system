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
# away the rollback target. deploy/selfhost/docker-compose.yml mounts one.

set -o errexit
set -o nounset
set -o pipefail

# Seed the layout if it is not there yet, and echo the directory the web server should
# run from. Idempotent: an existing `current` is left alone, because re-seeding on every
# boot would copy the whole tree each start AND destroy the rollback target.
rmc_release_layout_prepare() {
  local root="${1:?release root required}"
  local live="${2:?live tree required}"
  local current="${root}/current"

  if [[ -L "${current}" && -d "${current}" ]]; then
    echo "${current}"
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

  mkdir -p "${root}/releases"
  if [[ ! -d "${root}/releases/${seed}" ]]; then
    echo "[selfhost] seeding release layout at ${root}/releases/${seed} (one-time copy)" >&2
    cp -a "${live}/." "${root}/releases/${seed}/" 2>/dev/null || {
      mkdir -p "${root}/releases/${seed}"
      cp -a "${live}/." "${root}/releases/${seed}/"
    }
  fi

  # Atomic even on first creation: build the link beside the target, then rename over.
  ln -sfn "${root}/releases/${seed}" "${current}.tmp"
  mv -Tf "${current}.tmp" "${current}"
  echo "${current}"
}
