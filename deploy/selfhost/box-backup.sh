#!/usr/bin/env bash
#
# The school's own records, backed up on the school's own box.
#
# WHY THIS EXISTS. A sovereign box replicates a handful of entities to the cloud and
# keeps everything else -- the fee ledger, the marks, the attendance, the discipline
# record, the uploaded documents -- on exactly one disk, in a school building, on
# hardware chosen because it was affordable. Until this service existed the only copy
# of a school's year was that disk. A dead SSD was total loss.
#
# The discipline here is copied deliberately from the one artefact on this box that
# already had it: the TLS certificate authority (see edge-bootstrap.sh, and section C
# of box-audit.sh). That backup is encrypted, its passphrase is kept somewhere other
# than the bundle, it is READ BACK before it is called a backup, and the box FAILS its
# own audit if there is no verified read-back on record. That was exactly right, and it
# was being applied to a certificate while the children's records got nothing.
#
# SO THE RULES ARE THE SAME ONES:
#
#   * the dump never touches disk unencrypted -- pg_dump streams straight into
#     `openssl enc`, and a failure anywhere in that pipe deletes the partial file;
#   * the passphrase lives in a DIFFERENT volume from the dumps, so an operator can
#     carry the backups off the box without carrying the key that opens them;
#   * every dump is read back before it counts: decrypted, its table of contents
#     listed, and then read END TO END through `pg_restore -f /dev/null`, which
#     decompresses every data block without touching any database. A file that
#     decrypts but is truncated fails that, and a truncated backup that nobody read
#     back is indistinguishable from a good one until the day it matters;
#   * a WRONG passphrase is tried on purpose, and must not produce a Postgres archive.
#     That is what proves the encryption is real rather than merely configured;
#   * the read-back is RECORDED, and box-audit.sh fails the box when the record is
#     missing or older than the newest dump on disk.
#
# AND TWO RULES THIS BOX ADDS, BECAUSE IT IS NOT A DATA CENTRE:
#
#   * IT MUST NEVER TAKE THE BOX DOWN. Same house rule as entrypoint.web.sh, where a
#     boot helper must never fail the boot. Nothing here exits non-zero in the loop,
#     nothing here runs in a container anything else depends on, and every write is
#     preceded by a measured free-space check that SKIPS the run -- loudly, on the
#     record -- rather than filling the disk. A backup job that fills the disk stops
#     Postgres writing and takes the school offline, which is worse than the risk it
#     was mitigating.
#   * IT MUST BE BOUNDED IN BYTES, not just in file count. Retention keeps a
#     grandfather-father-son set (daily/weekly/monthly), and then a hard byte cap
#     prunes further if the school is bigger than the estimate. The newest verified
#     dump is never pruned by either rule: a retention policy that can delete the only
#     backup is worse than no retention policy.
#
# WHAT IT DELIBERATELY DOES NOT BACK UP: deploy/selfhost/.env. This container is given
# the database and the media tree and nothing else -- it never sees SECRET_KEY or the
# cloud credential. Keep a copy of .env wherever you keep the backup passphrase; see
# docs/EDGE_BOX_BACKUP_RUNBOOK.md.
#
# Usage (all of these run INSIDE the backup container):
#   box-backup.sh loop        # the default; what the compose service runs
#   box-backup.sh once        # take one backup now, verify it, prune, return
#   box-backup.sh verify      # re-read the newest dump back, no new dump taken
#   box-backup.sh drill       # restore into a scratch database and count rows
#   box-backup.sh proof       # read-only: is the encryption real, where is the key
#   box-backup.sh status      # print the record box-audit.sh reads
#   box-backup.sh list        # what is on disk, newest first
#   box-backup.sh restore <file|latest> [--into DB] [--yes-destroy-current-data]
#
# On the HOST, the restore is orchestrated by deploy/selfhost/box-restore.sh, which
# stops the app services first. Do not hand-run the restore subcommand against the
# live database while gunicorn is serving it.

# NOT `set -e`. A single failed step must record itself and let the loop continue --
# an appliance that stops backing up because one dump failed has quietly become an
# appliance with no backups. pipefail is on because the dump is a pipeline and its
# FIRST element is the one that matters.
set -uo pipefail

# --- configuration ----------------------------------------------------------
# Everything is a knob with a default, because the right numbers follow the hardware
# and a box that hand-edits a tracked file fights every git pull.
# libpq reads PGHOST/PGPORT/PGUSER/PGPASSWORD straight out of the environment, so
# they are never named again below. PGDATABASE is, in log lines and in the restore
# target, and `set -u` would abort on it -- so it gets the same default the compose
# file gives the server.
PGDATABASE="${PGDATABASE:-runmycampus}"
export PGDATABASE
BACKUP_DIR="${RMC_BOX_BACKUP_DIR:-/backups}"
KEY_DIR="${RMC_BOX_BACKUP_KEY_DIR:-/keys}"
MEDIA_SRC="${RMC_BOX_BACKUP_MEDIA_DIR:-/media-src}"
OFFBOX_DIR="${RMC_BOX_BACKUP_OFFBOX_DIR_IN:-/offbox}"
WORK_DIR="$BACKUP_DIR/.work"
STATE_FILE="$BACKUP_DIR/backup-state.json"
PASS_FILE="$KEY_DIR/box-backup-passphrase.txt"
DB_PREFIX="rmc-box-db-"
MEDIA_PREFIX="rmc-box-media-"

# Cadence. The window keeps the dump off the box while a school is using it; the
# OVERDUE escape hatch below is what makes that safe on a box that is switched off
# every evening -- which is most of them. Without it a school that powers the box down
# at 4pm would never once be inside the quiet window, and would never be backed up.
INTERVAL_HOURS="${RMC_BOX_BACKUP_INTERVAL_HOURS:-24}"
WINDOW_START="${RMC_BOX_BACKUP_WINDOW_START:-1}"
WINDOW_END="${RMC_BOX_BACKUP_WINDOW_END:-5}"
POLL_SECONDS="${RMC_BOX_BACKUP_POLL_SECONDS:-600}"
SETTLE_SECONDS="${RMC_BOX_BACKUP_SETTLE_SECONDS:-300}"

# Retention. Overlapping on purpose: a dump can be today's daily AND this week's
# weekly AND this month's monthly, and it is one file either way.
RET_DAILY="${RMC_BOX_BACKUP_KEEP_DAILY:-7}"
RET_WEEKLY="${RMC_BOX_BACKUP_KEEP_WEEKLY:-4}"
RET_MONTHLY="${RMC_BOX_BACKUP_KEEP_MONTHLY:-3}"

# The byte bounds. 4 GiB of dumps and 2 GiB of media is the whole footprint this
# service is allowed on a mini-PC. See docs/EDGE_BOX_BACKUP_RUNBOOK.md for the
# arithmetic behind these defaults.
CAP_BYTES="${RMC_BOX_BACKUP_MAX_BYTES:-4294967296}"
MEDIA_MAX_BYTES="${RMC_BOX_BACKUP_MEDIA_MAX_BYTES:-2147483648}"
MIN_FREE_BYTES="${RMC_BOX_BACKUP_MIN_FREE_BYTES:-1073741824}"
FIRST_ESTIMATE_BYTES="${RMC_BOX_BACKUP_FIRST_ESTIMATE_BYTES:-268435456}"

MEDIA_MODE="${RMC_BOX_BACKUP_MEDIA:-auto}"
MEDIA_INTERVAL_HOURS="${RMC_BOX_BACKUP_MEDIA_INTERVAL_HOURS:-168}"
MEDIA_KEEP="${RMC_BOX_BACKUP_MEDIA_KEEP:-1}"

DRILL_DAYS="${RMC_BOX_BACKUP_DRILL_DAYS:-30}"
DRILL_DB="${RMC_BOX_BACKUP_DRILL_DB:-rmc_restore_drill}"
DRILL_HEADROOM="${RMC_BOX_BACKUP_DRILL_HEADROOM:-10}"

# pg_dump takes ACCESS SHARE locks. It does not block readers or writers, but it DOES
# queue behind a migration's ACCESS EXCLUSIVE lock -- and once queued it blocks
# everything behind it. Bounded so a backup can never be the reason a school's boot
# migration or a teacher's page waits: if the locks are not free in a minute the dump
# gives up, records itself, and tries again next poll.
LOCK_WAIT_MS="${RMC_BOX_BACKUP_LOCK_WAIT_MS:-60000}"
EXPECT_TABLE="${RMC_BOX_BACKUP_EXPECT_TABLE:-django_migrations}"
MIN_TOC_ENTRIES="${RMC_BOX_BACKUP_MIN_TOC_ENTRIES:-200}"

ENC_ARGS=(-aes-256-cbc -md sha512 -pbkdf2 -iter 200000 -salt)
WRONG_PASS="definitely-not-the-passphrase"

# --- small helpers ----------------------------------------------------------
now_iso()   { date -u +%Y-%m-%dT%H:%M:%SZ; }
now_epoch() { date -u +%s; }
stamp()     { date -u +%Y%m%dT%H%M%SZ; }
log()       { printf '[backup] %s %s\n' "$(now_iso)" "$*"; }

# JSON string escaping, for a flat one-key-per-line document. Quotes, backslashes and
# newlines are removed rather than escaped: the only values that reach here are
# messages and filenames, and an unparseable state file would blind box-audit.sh --
# which is the exact failure this whole service is built to make impossible.
jstr() { printf '%s' "$*" | tr -d '"\\' | tr '\n\r\t' '   ' | cut -c1-400; }

free_bytes() {
  df -Pk "${1:-$BACKUP_DIR}" 2>/dev/null | awk 'NR == 2 { print $4 * 1024 }'
}

file_bytes() { stat -c %s "$1" 2>/dev/null || printf '0'; }

dir_bytes() { du -sk "$1" 2>/dev/null | awk '{ print $1 * 1024 }'; }

# Every dump on disk, NEWEST FIRST. The stamp is fixed width and the prefix constant,
# so a reverse lexical sort is a reverse chronological sort, and it does not depend on
# mtime -- which a copy, a restore or a filesystem check can rewrite.
db_files() {
  ls -1 "$BACKUP_DIR" 2>/dev/null | grep "^$DB_PREFIX" | grep '\.dump\.enc$' | sort -r
}

media_files() {
  ls -1 "$BACKUP_DIR" 2>/dev/null | grep "^$MEDIA_PREFIX" | grep '\.tar\.enc$' | sort -r
}

# --- the state record -------------------------------------------------------
# One flat JSON document, one key per line, written atomically. box-audit.sh reads it
# through `docker compose exec`, exactly as section C reads the trust anchor.
S_LAST_ATTEMPT_AT=""
S_LAST_SUCCESS_AT=""
S_LAST_SUCCESS_EPOCH="0"
S_LAST_STATUS="never"
S_LAST_ERROR=""
S_LAST_FILE=""
S_LAST_BYTES="0"
S_VERIFIED_AT=""
S_VERIFIED_FILE=""
S_VERIFIED_TOC="0"
S_VERIFIED_FULL_READ="false"
S_ENCRYPTION_REAL="unknown"
S_DRILL_AT=""
S_DRILL_EPOCH="0"
S_DRILL_STATUS="never"
S_DRILL_ROWS="0"
S_MEDIA_AT=""
S_MEDIA_EPOCH="0"
S_MEDIA_STATUS="never"
S_MEDIA_BYTES="0"
S_KEPT_FILES="0"
S_KEPT_BYTES="0"
S_FREE_BYTES="0"
S_OFFBOX_AT=""
S_OFFBOX_STATUS="none"
S_OFFBOX_INDEPENDENT="unknown"

state_read_key() {
  sed -n 's/.*"'"$1"'"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/p' "$STATE_FILE" 2>/dev/null | head -1
}

state_read_num() {
  sed -n 's/.*"'"$1"'"[[:space:]]*:[[:space:]]*\([0-9][0-9]*\).*/\1/p' "$STATE_FILE" 2>/dev/null | head -1
}

state_load() {
  [ -s "$STATE_FILE" ] || return 0
  S_LAST_ATTEMPT_AT="$(state_read_key last_attempt_at)"
  S_LAST_SUCCESS_AT="$(state_read_key last_success_at)"
  S_LAST_SUCCESS_EPOCH="$(state_read_num last_success_epoch)"
  S_LAST_STATUS="$(state_read_key last_status)"
  S_LAST_ERROR="$(state_read_key last_error)"
  S_LAST_FILE="$(state_read_key last_file)"
  S_LAST_BYTES="$(state_read_num last_bytes)"
  S_VERIFIED_AT="$(state_read_key verified_at)"
  S_VERIFIED_FILE="$(state_read_key verified_file)"
  S_VERIFIED_TOC="$(state_read_num verified_toc_entries)"
  S_VERIFIED_FULL_READ="$(state_read_key verified_full_read)"
  S_ENCRYPTION_REAL="$(state_read_key encryption_real)"
  S_DRILL_AT="$(state_read_key drill_at)"
  S_DRILL_EPOCH="$(state_read_num drill_epoch)"
  S_DRILL_STATUS="$(state_read_key drill_status)"
  S_DRILL_ROWS="$(state_read_num drill_rows)"
  S_MEDIA_AT="$(state_read_key media_at)"
  S_MEDIA_EPOCH="$(state_read_num media_epoch)"
  S_MEDIA_STATUS="$(state_read_key media_status)"
  S_MEDIA_BYTES="$(state_read_num media_bytes)"
  S_KEPT_FILES="$(state_read_num kept_files)"
  S_KEPT_BYTES="$(state_read_num kept_bytes)"
  S_FREE_BYTES="$(state_read_num free_bytes)"
  S_OFFBOX_AT="$(state_read_key offbox_at)"
  S_OFFBOX_STATUS="$(state_read_key offbox_status)"
  S_OFFBOX_INDEPENDENT="$(state_read_key offbox_independent)"
  : "${S_LAST_SUCCESS_EPOCH:=0}" "${S_LAST_BYTES:=0}" "${S_VERIFIED_TOC:=0}"
  : "${S_DRILL_EPOCH:=0}" "${S_DRILL_ROWS:=0}" "${S_MEDIA_EPOCH:=0}"
  : "${S_MEDIA_BYTES:=0}" "${S_KEPT_FILES:=0}" "${S_KEPT_BYTES:=0}" "${S_FREE_BYTES:=0}"
}

state_write() {
  local tmp="$STATE_FILE.tmp"
  {
    printf '{\n'
    printf '  "schema": 1,\n'
    printf '  "last_attempt_at": "%s",\n'   "$(jstr "$S_LAST_ATTEMPT_AT")"
    printf '  "last_success_at": "%s",\n'   "$(jstr "$S_LAST_SUCCESS_AT")"
    printf '  "last_success_epoch": %s,\n'  "${S_LAST_SUCCESS_EPOCH:-0}"
    printf '  "last_status": "%s",\n'       "$(jstr "$S_LAST_STATUS")"
    printf '  "last_error": "%s",\n'        "$(jstr "$S_LAST_ERROR")"
    printf '  "last_file": "%s",\n'         "$(jstr "$S_LAST_FILE")"
    printf '  "last_bytes": %s,\n'          "${S_LAST_BYTES:-0}"
    printf '  "verified_at": "%s",\n'       "$(jstr "$S_VERIFIED_AT")"
    printf '  "verified_file": "%s",\n'     "$(jstr "$S_VERIFIED_FILE")"
    printf '  "verified_toc_entries": %s,\n' "${S_VERIFIED_TOC:-0}"
    printf '  "verified_full_read": "%s",\n' "$(jstr "$S_VERIFIED_FULL_READ")"
    printf '  "encryption_real": "%s",\n'   "$(jstr "$S_ENCRYPTION_REAL")"
    printf '  "drill_at": "%s",\n'          "$(jstr "$S_DRILL_AT")"
    printf '  "drill_epoch": %s,\n'         "${S_DRILL_EPOCH:-0}"
    printf '  "drill_status": "%s",\n'      "$(jstr "$S_DRILL_STATUS")"
    printf '  "drill_rows": %s,\n'          "${S_DRILL_ROWS:-0}"
    printf '  "media_at": "%s",\n'          "$(jstr "$S_MEDIA_AT")"
    printf '  "media_epoch": %s,\n'         "${S_MEDIA_EPOCH:-0}"
    printf '  "media_status": "%s",\n'      "$(jstr "$S_MEDIA_STATUS")"
    printf '  "media_bytes": %s,\n'         "${S_MEDIA_BYTES:-0}"
    printf '  "kept_files": %s,\n'          "${S_KEPT_FILES:-0}"
    printf '  "kept_bytes": %s,\n'          "${S_KEPT_BYTES:-0}"
    printf '  "free_bytes": %s,\n'          "${S_FREE_BYTES:-0}"
    printf '  "offbox_at": "%s",\n'         "$(jstr "$S_OFFBOX_AT")"
    printf '  "offbox_status": "%s",\n'     "$(jstr "$S_OFFBOX_STATUS")"
    printf '  "offbox_independent": "%s"\n' "$(jstr "$S_OFFBOX_INDEPENDENT")"
    printf '}\n'
  } > "$tmp" 2>/dev/null && mv -f "$tmp" "$STATE_FILE"
}

# --- retention, as PURE TEXT ------------------------------------------------
# Reads dump BASENAMES on stdin. Writes the names to KEEP on stdout. It touches no
# filesystem and asks the clock for nothing -- every date comes out of the name -- so
# the arithmetic can be lifted into a test harness and run against a synthetic decade
# of filenames on a machine that has no box and no Docker. That is the only way this
# particular rule ever gets tested, and an untested retention rule is how a backup
# directory either fills a disk or quietly empties itself.
#
# Grandfather-father-son. Buckets OVERLAP: today's dump is today's daily, this week's
# weekly and this month's monthly, and it is one file on disk either way.
retention_keep() {
  sort -r | awk \
    -v kd="${RET_DAILY:-7}" -v kw="${RET_WEEKLY:-4}" -v km="${RET_MONTHLY:-3}" '
    # Days since 1970-01-01 from a civil date, by arithmetic only. GNU date could do
    # this, but calling it once per file per pass makes the function depend on a
    # binary and on the ambient timezone, and neither belongs in a rule about which
    # files to delete.
    function dfc(y, m, d,   yy, era, yoe, doy, doe) {
      yy  = y - (m <= 2 ? 1 : 0)
      era = int((yy >= 0 ? yy : yy - 399) / 400)
      yoe = yy - era * 400
      doy = int((153 * (m + (m > 2 ? -3 : 9)) + 2) / 5) + d - 1
      doe = yoe * 365 + int(yoe / 4) - int(yoe / 100) + doy
      return era * 146097 + doe - 719468
    }
    # POSIX character classes only: mawk is the default awk on Debian and its
    # support for {n} interval expressions has not always been on.
    /[0-9][0-9][0-9][0-9][0-9][0-9][0-9][0-9]T[0-9][0-9][0-9][0-9][0-9][0-9]Z/ {
      match($0, /[0-9][0-9][0-9][0-9][0-9][0-9][0-9][0-9]T[0-9][0-9][0-9][0-9][0-9][0-9]Z/)
      s  = substr($0, RSTART, RLENGTH)
      dk = substr(s, 1, 8)
      mk = substr(s, 1, 6)
      wk = int((dfc(substr(s,1,4) + 0, substr(s,5,2) + 0, substr(s,7,2) + 0) + 4) / 7)
      # Input is newest-first, so the first name seen in a bucket is that bucket s
      # newest and the one worth keeping.
      if (!(dk in bd)) { bd[dk] = $0; dord[++nd] = dk }
      if (!(wk in bw)) { bw[wk] = $0; word[++nw] = wk }
      if (!(mk in bm)) { bm[mk] = $0; mord[++nm] = mk }
    }
    END {
      for (i = 1; i <= nd && i <= kd; i++) keep[bd[dord[i]]] = 1
      for (i = 1; i <= nw && i <= kw; i++) keep[bw[word[i]]] = 1
      for (i = 1; i <= nm && i <= km; i++) keep[bm[mord[i]]] = 1
      for (k in keep) print k
    }' | sort -r
}

# The byte bound, applied AFTER the policy above. Reads "BYTES<TAB>NAME" newest first,
# writes the names that fit. The newest is kept unconditionally, even when it alone is
# over the cap: a rule that can delete the only backup is worse than no rule.
cap_keep() {
  awk -F '\t' -v cap="${CAP_BYTES:-0}" '
    {
      n++
      total += $1
      if (n > 1 && cap > 0 && total > cap) exit
      print $2
    }'
}

# --- preflight --------------------------------------------------------------
PREFLIGHT_ERROR=""
preflight() {
  PREFLIGHT_ERROR=""
  local missing=""
  local tool
  for tool in pg_dump pg_restore psql openssl tar df du stat; do
    command -v "$tool" >/dev/null 2>&1 || missing="$missing $tool"
  done
  if [ -n "$missing" ]; then
    # openssl is the one that matters and the one worth naming. Writing a PLAINTEXT
    # dump of a school's records because the encryptor was missing is not a
    # degraded backup, it is a data-protection incident that looks like success --
    # so this refuses instead, loudly, and box-audit.sh turns the refusal into a
    # FAIL an operator will actually see.
    PREFLIGHT_ERROR="missing tools:$missing (refusing to write an unencrypted dump)"
    return 1
  fi
  mkdir -p "$BACKUP_DIR" "$WORK_DIR" "$KEY_DIR" 2>/dev/null
  [ -d "$BACKUP_DIR" ] || { PREFLIGHT_ERROR="backup directory $BACKUP_DIR is not writable"; return 1; }
  return 0
}

# The passphrase. Generated once, kept in a volume that is deliberately NOT the one
# holding the dumps, and never regenerated -- a second passphrase re-encrypts nothing
# and silently strands every copy already carried off the box. Same reasoning, and the
# same trap, as edge-bootstrap.sh's CA passphrase.
ensure_passphrase() {
  if [ -n "${RMC_BOX_BACKUP_PASSPHRASE:-}" ]; then
    if [ ! -s "$PASS_FILE" ]; then
      ( umask 077; printf '%s\n' "$RMC_BOX_BACKUP_PASSPHRASE" > "$PASS_FILE" )
    fi
    return 0
  fi
  [ -s "$PASS_FILE" ] && return 0
  local generated
  generated="$( set +o pipefail; LC_ALL=C tr -dc 'A-Za-z0-9' < /dev/urandom 2>/dev/null | head -c 44 )"
  if [ "${#generated}" -lt 32 ]; then
    PREFLIGHT_ERROR="could not generate a passphrase (is /dev/urandom readable?)"
    return 1
  fi
  ( umask 077; printf '%s\n' "$generated" > "$PASS_FILE" )
  log "generated a backup passphrase at $PASS_FILE"
  log "TAKE A COPY OFF THIS BOX. Without it every dump here is unreadable, and it is"
  log "the one thing in this service that cannot be regenerated from the database."
  return 0
}

encrypt_to() { openssl enc "${ENC_ARGS[@]}" -pass "file:$PASS_FILE" -out "$1"; }

decrypt_from() { openssl enc -d "${ENC_ARGS[@]}" -pass "file:$PASS_FILE" -in "$1" -out "$2" 2>/dev/null; }

# --- the read-back ----------------------------------------------------------
# It is not a backup until it has been read back. Three questions, in order, and each
# one has been the difference between a real backup and a file that looked like one:
#
#   1. does it decrypt with the passphrase this box holds, and is the plaintext a
#      Postgres archive (the PGDMP magic) rather than 40MB of noise;
#   2. does its table of contents list a real database -- the migrations table and
#      more entries than an empty schema could produce;
#   3. does it read END TO END. `pg_restore -f /dev/null` generates the whole restore
#      script, which means decompressing every data block, without touching any
#      database. A dump truncated by a full disk decrypts fine and lists fine and
#      fails here, which is the whole reason this step is not optional.
#
# Then the fourth question, which is about the encryption rather than the archive: a
# WRONG passphrase must not produce a Postgres archive. Section C of box-audit.sh asks
# the CA bundle the same thing for the same reason.
VERIFY_TOC=0
VERIFY_FULL="false"
VERIFY_ENC="unknown"
VERIFY_ERROR=""
verify_dump() {
  local enc="$BACKUP_DIR/$1"
  local plain="$WORK_DIR/verify.dump"
  local wrong="$WORK_DIR/verify-wrong.bin"
  VERIFY_TOC=0; VERIFY_FULL="false"; VERIFY_ENC="unknown"; VERIFY_ERROR=""
  rm -f "$plain" "$wrong" 2>/dev/null

  if [ ! -s "$enc" ]; then
    VERIFY_ERROR="no such dump: $1"
    return 1
  fi
  if ! decrypt_from "$enc" "$plain"; then
    VERIFY_ERROR="the dump does not decrypt with the passphrase this box holds"
    rm -f "$plain"; return 1
  fi
  if [ "$(head -c 5 "$plain" 2>/dev/null)" != "PGDMP" ]; then
    VERIFY_ERROR="decrypted, but the plaintext is not a Postgres archive"
    rm -f "$plain"; return 1
  fi

  local toc
  toc="$(pg_restore -l "$plain" 2>/dev/null)"
  VERIFY_TOC="$(printf '%s\n' "$toc" | grep -c '^[0-9]')"
  if [ "${VERIFY_TOC:-0}" -lt "$MIN_TOC_ENTRIES" ]; then
    VERIFY_ERROR="the table of contents holds only ${VERIFY_TOC:-0} entries (expected at least $MIN_TOC_ENTRIES) -- this is not a full school database"
    rm -f "$plain"; return 1
  fi
  if ! printf '%s\n' "$toc" | grep -q "$EXPECT_TABLE"; then
    VERIFY_ERROR="the table of contents does not mention $EXPECT_TABLE -- this dump is not of this application"
    rm -f "$plain"; return 1
  fi

  if pg_restore -f /dev/null "$plain" >/dev/null 2>&1; then
    VERIFY_FULL="true"
  else
    VERIFY_ERROR="the archive listed but would not read end to end -- it is truncated or corrupt"
    rm -f "$plain"; return 1
  fi

  # Prove the encryption. A wrong passphrase must either be refused outright or
  # produce something that is not a Postgres archive; if it opens, this file is not
  # actually protected and saying so is more useful than a green tick.
  if openssl enc -d "${ENC_ARGS[@]}" -pass "pass:$WRONG_PASS" -in "$enc" -out "$wrong" 2>/dev/null \
     && [ "$(head -c 5 "$wrong" 2>/dev/null)" = "PGDMP" ]; then
    VERIFY_ENC="false"
  else
    VERIFY_ENC="true"
  fi
  rm -f "$plain" "$wrong" 2>/dev/null
  return 0
}

# --- pruning ----------------------------------------------------------------
prune() {
  local keep_list survivors sized name bytes
  keep_list="$(db_files | retention_keep)"
  # Size the survivors newest-first, then let the byte cap trim further.
  sized=""
  for name in $keep_list; do
    bytes="$(file_bytes "$BACKUP_DIR/$name")"
    # printf builds the separator rather than a literal tab in the source: a tab
    # that an editor helpfully turns into spaces would make every line one field,
    # and cap_keep would then read the SIZE as the filename and delete nothing.
    sized="$sized$(printf '%s\t%s' "$bytes" "$name")
"
  done
  survivors="$(printf '%s' "$sized" | grep -v '^$' | cap_keep)"

  local total=0 count=0
  for name in $(db_files); do
    # -F, because this decides what gets DELETED. Without it the `.` in a filename is
    # a regex wildcard and a name can match a neighbour it is not.
    if printf '%s\n' "$survivors" | grep -qxF "$name"; then
      bytes="$(file_bytes "$BACKUP_DIR/$name")"
      total=$((total + bytes))
      count=$((count + 1))
    else
      log "pruning $name"
      rm -f "$BACKUP_DIR/$name" 2>/dev/null
    fi
  done

  # Media has its own, much shorter, retention: an image tree is the bulkiest thing
  # on the box and the least reconstructible thing is not it.
  local n=0
  for name in $(media_files); do
    n=$((n + 1))
    if [ "$n" -gt "$MEDIA_KEEP" ]; then
      log "pruning $name"
      rm -f "$BACKUP_DIR/$name" 2>/dev/null
    else
      bytes="$(file_bytes "$BACKUP_DIR/$name")"
      total=$((total + bytes))
      count=$((count + 1))
    fi
  done

  S_KEPT_FILES="$count"
  S_KEPT_BYTES="$total"
  S_FREE_BYTES="$(free_bytes)"
}

# --- off-box copy -----------------------------------------------------------
# The copy that actually survives a dead disk. Everything above this line protects
# against a bad migration, a wrong delete and a lost pgdata volume; NONE of it
# protects against the SSD failing, because it all lives on that SSD. Point
# RMC_BOX_BACKUP_OFFBOX_DIR at a mounted USB disk or a NAS share and this happens by
# itself, every run, with no step for anyone to remember.
#
# The default is a named volume, which is on the same disk -- honest rather than
# convenient. The device-number comparison below is what lets box-audit.sh say which
# of the two a given box actually has, instead of assuming the good case.
offbox_copy() {
  S_OFFBOX_STATUS="none"
  S_OFFBOX_INDEPENDENT="unknown"
  [ -d "$OFFBOX_DIR" ] || return 0
  local dev_b dev_o
  dev_b="$(stat -c %d "$BACKUP_DIR" 2>/dev/null)"
  dev_o="$(stat -c %d "$OFFBOX_DIR" 2>/dev/null)"
  if [ -n "$dev_b" ] && [ "$dev_b" = "$dev_o" ]; then
    S_OFFBOX_INDEPENDENT="false"
  elif [ -n "$dev_o" ]; then
    S_OFFBOX_INDEPENDENT="true"
  fi
  local need free_o
  need=$(( $(file_bytes "$BACKUP_DIR/$S_LAST_FILE") + MIN_FREE_BYTES ))
  free_o="$(free_bytes "$OFFBOX_DIR")"
  if [ -z "$free_o" ] || [ "$free_o" -lt "$need" ]; then
    S_OFFBOX_STATUS="skipped: only ${free_o:-0} bytes free at $OFFBOX_DIR, needed $need"
    return 0
  fi
  if cp -f "$BACKUP_DIR/$S_LAST_FILE" "$OFFBOX_DIR/$S_LAST_FILE.part" 2>/dev/null \
     && mv -f "$OFFBOX_DIR/$S_LAST_FILE.part" "$OFFBOX_DIR/$S_LAST_FILE" 2>/dev/null; then
    S_OFFBOX_STATUS="copied"
    S_OFFBOX_AT="$(now_iso)"
    # Same retention there, so a USB stick cannot be filled either.
    local keep name
    keep="$(ls -1 "$OFFBOX_DIR" 2>/dev/null | grep "^$DB_PREFIX" | grep '\.dump\.enc$' | sort -r | retention_keep)"
    for name in $(ls -1 "$OFFBOX_DIR" 2>/dev/null | grep "^$DB_PREFIX" | grep '\.dump\.enc$'); do
      printf '%s\n' "$keep" | grep -qxF "$name" || rm -f "$OFFBOX_DIR/$name" 2>/dev/null
    done
  else
    rm -f "$OFFBOX_DIR/$S_LAST_FILE.part" 2>/dev/null
    S_OFFBOX_STATUS="failed to copy to $OFFBOX_DIR"
  fi
  return 0
}

# --- one backup -------------------------------------------------------------
run_backup() {
  state_load
  S_LAST_ATTEMPT_AT="$(now_iso)"

  if ! preflight || ! ensure_passphrase; then
    S_LAST_STATUS="failed"
    S_LAST_ERROR="$PREFLIGHT_ERROR"
    log "FAILED: $PREFLIGHT_ERROR"
    state_write
    return 0
  fi

  # Space FIRST, always. The estimate is the last dump this box actually produced,
  # which beats any constant: a school of 300 and a school of 3000 are an order of
  # magnitude apart and neither should be told the other's number. Two dumps' worth
  # is needed because the read-back writes a decrypted copy beside the encrypted one,
  # and MIN_FREE_BYTES on top of that is the floor this service will not take the
  # machine below under any circumstances.
  local est need free
  est="${S_LAST_BYTES:-0}"
  [ "$est" -gt 0 ] || est="$FIRST_ESTIMATE_BYTES"
  need=$(( est * 2 + MIN_FREE_BYTES ))
  free="$(free_bytes)"
  if [ -z "$free" ] || [ "$free" -lt "$need" ]; then
    prune
    free="$(free_bytes)"
  fi
  if [ -z "$free" ] || [ "$free" -lt "$need" ]; then
    S_LAST_STATUS="skipped"
    S_LAST_ERROR="only ${free:-0} bytes free, need $need (2 x $est estimate + $MIN_FREE_BYTES floor)"
    log "SKIPPED: $S_LAST_ERROR"
    log "This is deliberate. Filling the disk stops Postgres writing and takes the"
    log "school offline, which is worse than the missed backup it would have bought."
    state_write
    return 0
  fi

  local st name tmp rc_dump rc_enc
  st="$(stamp)"
  name="$DB_PREFIX$st.dump.enc"
  tmp="$WORK_DIR/$name.part"
  rm -f "$tmp" 2>/dev/null

  log "dumping $PGDATABASE -> $name"
  # Straight into the encryptor. The plaintext never exists as a file, so there is no
  # window in which a readable copy of a school's records is sitting on the disk.
  nice -n 19 pg_dump --format=custom --compress=6 \
       --lock-wait-timeout="$LOCK_WAIT_MS" 2>"$WORK_DIR/dump.err" \
    | encrypt_to "$tmp"
  rc_dump="${PIPESTATUS[0]}"
  rc_enc="${PIPESTATUS[1]}"
  if [ "$rc_dump" != "0" ] || [ "$rc_enc" != "0" ] || [ ! -s "$tmp" ]; then
    rm -f "$tmp" 2>/dev/null
    S_LAST_STATUS="failed"
    S_LAST_ERROR="pg_dump exited $rc_dump, openssl exited $rc_enc: $(tail -2 "$WORK_DIR/dump.err" 2>/dev/null)"
    log "FAILED: $S_LAST_ERROR"
    state_write
    return 0
  fi

  mv -f "$tmp" "$BACKUP_DIR/$name" 2>/dev/null
  S_LAST_FILE="$name"
  S_LAST_BYTES="$(file_bytes "$BACKUP_DIR/$name")"

  if verify_dump "$name"; then
    S_LAST_STATUS="ok"
    S_LAST_ERROR=""
    S_LAST_SUCCESS_AT="$(now_iso)"
    S_LAST_SUCCESS_EPOCH="$(now_epoch)"
    S_VERIFIED_AT="$S_LAST_SUCCESS_AT"
    S_VERIFIED_FILE="$name"
    S_VERIFIED_TOC="$VERIFY_TOC"
    S_VERIFIED_FULL_READ="$VERIFY_FULL"
    S_ENCRYPTION_REAL="$VERIFY_ENC"
    log "ok $name ($S_LAST_BYTES bytes, $VERIFY_TOC archive entries, read back end to end)"
  else
    # A dump that will not read back is not a backup, and keeping it would let the
    # retention policy count it as one. It goes, and the older verified dumps stay.
    rm -f "$BACKUP_DIR/$name" 2>/dev/null
    # Point `last_file` back at whatever survived, not at nothing. The audit prints it
    # as "newest dump", and a box that still holds four good dumps must not report
    # `<none>` because tonight's attempt was bad.
    S_LAST_FILE="$(db_files | head -1)"
    S_LAST_STATUS="failed"
    S_LAST_ERROR="read-back failed: $VERIFY_ERROR"
    log "FAILED: $S_LAST_ERROR"
    log "the unreadable dump has been deleted; the last verified one is untouched"
    state_write
    return 0
  fi

  prune
  offbox_copy
  state_write
  log "kept $S_KEPT_FILES artefact(s), $S_KEPT_BYTES bytes, $S_FREE_BYTES bytes free"
  return 0
}

# --- media ------------------------------------------------------------------
# THE DECISION ABOUT MEDIA, stated where it is implemented.
#
# Media IS backed up -- uploaded documents, photographs, evaluation evidence and
# receipts are as irreplaceable as any row, and leaving them out would have left
# exactly the hole this service was built to close. But NOT on the same terms as the
# database, for two reasons that are about this hardware rather than about principle:
#
#   * it is the bulkiest thing on the box by an order of magnitude, and fourteen
#     rolling copies of an image tree would fill a mini-PC's disk on its own;
#   * a photograph usually still exists on the phone that took it, and a scanned
#     document usually still exists on paper. A fee ledger exists nowhere else.
#
# So: weekly rather than nightly, ONE copy rather than fourteen, and it is the first
# thing dropped when space is short. When it is skipped it is skipped ON THE RECORD,
# with the measured size and the cap in the message, so nobody discovers the omission
# during a restore.
run_media() {
  state_load
  [ "$MEDIA_MODE" = "off" ] && { S_MEDIA_STATUS="off (RMC_BOX_BACKUP_MEDIA=off)"; state_write; return 0; }
  preflight || return 0
  ensure_passphrase || return 0
  if [ ! -d "$MEDIA_SRC" ]; then
    S_MEDIA_STATUS="no media tree mounted at $MEDIA_SRC"
    state_write
    return 0
  fi

  local size free need st name tmp rc_tar rc_enc
  size="$(dir_bytes "$MEDIA_SRC")"
  : "${size:=0}"
  if [ "$MEDIA_MODE" = "auto" ] && [ "$size" -gt "$MEDIA_MAX_BYTES" ]; then
    S_MEDIA_STATUS="skipped: media is $size bytes, over the $MEDIA_MAX_BYTES cap"
    S_MEDIA_BYTES="$size"
    log "media SKIPPED: $S_MEDIA_STATUS"
    log "raise RMC_BOX_BACKUP_MEDIA_MAX_BYTES only if the disk can carry it, or copy"
    log "$MEDIA_SRC off the box by another route. It is NOT being backed up today."
    state_write
    return 0
  fi
  need=$(( size + MIN_FREE_BYTES ))
  free="$(free_bytes)"
  if [ -z "$free" ] || [ "$free" -lt "$need" ]; then
    S_MEDIA_STATUS="skipped: only ${free:-0} bytes free, need $need"
    S_MEDIA_BYTES="$size"
    log "media SKIPPED: $S_MEDIA_STATUS"
    state_write
    return 0
  fi

  st="$(stamp)"
  name="$MEDIA_PREFIX$st.tar.enc"
  tmp="$WORK_DIR/$name.part"
  rm -f "$tmp" 2>/dev/null
  log "archiving media ($size bytes) -> $name"
  # Not compressed: a media tree is photographs and PDFs, which are already
  # compressed, so gzip would buy a rounding error and cost the CPU of a mini-PC for
  # an hour. Encrypted, because it leaves the box exactly like the database does.
  nice -n 19 tar -C "$MEDIA_SRC" -cf - . 2>"$WORK_DIR/media.err" | encrypt_to "$tmp"
  rc_tar="${PIPESTATUS[0]}"
  rc_enc="${PIPESTATUS[1]}"
  if [ "$rc_tar" != "0" ] || [ "$rc_enc" != "0" ] || [ ! -s "$tmp" ]; then
    rm -f "$tmp" 2>/dev/null
    S_MEDIA_STATUS="failed: tar exited $rc_tar, openssl exited $rc_enc"
    log "media FAILED: $S_MEDIA_STATUS"
    state_write
    return 0
  fi
  # Read back before it counts, same rule as the database.
  if decrypt_from "$tmp" /dev/stdout 2>/dev/null | tar -tf - >/dev/null 2>&1; then
    mv -f "$tmp" "$BACKUP_DIR/$name" 2>/dev/null
    S_MEDIA_STATUS="ok"
    S_MEDIA_AT="$(now_iso)"
    S_MEDIA_EPOCH="$(now_epoch)"
    S_MEDIA_BYTES="$(file_bytes "$BACKUP_DIR/$name")"
    log "media ok $name ($S_MEDIA_BYTES bytes, read back)"
  else
    rm -f "$tmp" 2>/dev/null
    S_MEDIA_STATUS="failed: the archive would not read back"
    log "media FAILED: $S_MEDIA_STATUS"
  fi
  prune
  state_write
  return 0
}

# --- the full drill ---------------------------------------------------------
# The read-back on every run proves the archive is intact and restorable-as-SQL. This
# proves POSTGRES ACCEPTS IT, which is a different claim and the one an operator is
# actually betting the school's year on. It costs a full second copy of the database
# on disk, so it is monthly by default, it is gated on measured free space, and when
# it cannot afford to run it says so rather than running anyway.
run_drill() {
  state_load
  preflight || return 0
  ensure_passphrase || return 0
  local newest plain free need rows
  newest="$(db_files | head -1)"
  if [ -z "$newest" ]; then
    S_DRILL_STATUS="no dump to drill"
    state_write
    return 0
  fi
  need=$(( $(file_bytes "$BACKUP_DIR/$newest") * DRILL_HEADROOM + MIN_FREE_BYTES ))
  # Measured on the BACKUP volume, not on the database's. The scratch database lands
  # in the db container's volume, which this container cannot see without the docker
  # socket -- and on a box that is one physical disk, which is what a box is, both
  # volumes and the image layers share a filesystem. An honest proxy, named as one.
  free="$(free_bytes)"
  : "${free:=0}"
  if [ "$free" -lt "$need" ]; then
    S_DRILL_STATUS="skipped: ${free} bytes free, a restore of $newest wants about $need"
    log "drill SKIPPED: $S_DRILL_STATUS"
    state_write
    return 0
  fi

  plain="$WORK_DIR/drill.dump"
  rm -f "$plain" 2>/dev/null
  if ! decrypt_from "$BACKUP_DIR/$newest" "$plain"; then
    S_DRILL_STATUS="failed: $newest does not decrypt"
    rm -f "$plain" 2>/dev/null
    state_write
    return 0
  fi

  log "restore drill: $newest -> database $DRILL_DB"
  dropdb --if-exists "$DRILL_DB" >/dev/null 2>&1
  if ! createdb "$DRILL_DB" >/dev/null 2>&1; then
    S_DRILL_STATUS="failed: could not create the scratch database $DRILL_DB"
    rm -f "$plain" 2>/dev/null
    state_write
    return 0
  fi
  if nice -n 19 pg_restore --dbname="$DRILL_DB" --no-owner --exit-on-error "$plain" >/dev/null 2>&1; then
    rows="$(psql -d "$DRILL_DB" -At -c "select count(*) from $EXPECT_TABLE" 2>/dev/null)"
    : "${rows:=0}"
    if [ "$rows" -gt 0 ]; then
      S_DRILL_STATUS="ok"
      S_DRILL_AT="$(now_iso)"
      S_DRILL_EPOCH="$(now_epoch)"
      S_DRILL_ROWS="$rows"
      log "drill ok: Postgres accepted the dump, $EXPECT_TABLE holds $rows rows"
    else
      S_DRILL_STATUS="failed: restored, but $EXPECT_TABLE came back empty"
    fi
  else
    S_DRILL_STATUS="failed: pg_restore refused the dump"
  fi
  # Always, on every path. A scratch database left behind is a second copy of the
  # school's data sitting on a disk this service exists to keep from filling.
  dropdb --if-exists "$DRILL_DB" >/dev/null 2>&1
  rm -f "$plain" 2>/dev/null
  state_write
  return 0
}

# --- the real restore -------------------------------------------------------
# Orchestrated from the host by deploy/selfhost/box-restore.sh, which stops the app
# services first. Refuses outright to overwrite the live database without the long
# flag, because there is no undo and the person typing it is usually having a bad day.
do_restore() {
  local which="${1:-latest}"; shift || true
  local into="$PGDATABASE" confirmed=0 plain file
  while [ "$#" -gt 0 ]; do
    case "$1" in
      --into) into="${2:-}"; shift 2 || true ;;
      --yes-destroy-current-data) confirmed=1; shift ;;
      *) shift ;;
    esac
  done
  preflight || { printf 'STOPPED %s\n' "$PREFLIGHT_ERROR" >&2; return 1; }
  if [ "$which" = "latest" ]; then
    file="$(db_files | head -1)"
  else
    file="$which"
  fi
  if [ -z "$file" ] || [ ! -s "$BACKUP_DIR/$file" ]; then
    printf 'STOPPED no such dump: %s\n' "${which}" >&2
    return 1
  fi
  if [ "$into" = "$PGDATABASE" ] && [ "$confirmed" != "1" ]; then
    printf 'STOPPED restoring into the LIVE database %s destroys what is in it now.\n' "$PGDATABASE" >&2
    printf '        Use deploy/selfhost/box-restore.sh on the host -- it stops the app\n' >&2
    printf '        services first -- or pass --yes-destroy-current-data if you know\n' >&2
    printf '        exactly why you are doing this by hand.\n' >&2
    return 1
  fi
  printf 'reading %s back before restoring it\n' "$file"
  if ! verify_dump "$file"; then
    printf 'STOPPED %s\n' "$VERIFY_ERROR" >&2
    printf '        Refusing to drop a working database for a dump that does not read.\n' >&2
    return 1
  fi
  plain="$WORK_DIR/restore.dump"
  rm -f "$plain" 2>/dev/null
  decrypt_from "$BACKUP_DIR/$file" "$plain" || { printf 'STOPPED decrypt failed\n' >&2; return 1; }
  printf 'restoring %s into %s\n' "$file" "$into"
  pg_restore --dbname="$into" --clean --if-exists --no-owner --single-transaction "$plain"
  local rc=$?
  rm -f "$plain" 2>/dev/null
  if [ "$rc" = "0" ]; then
    printf 'restored. Start the app services again and check the box.\n'
  else
    printf 'STOPPED pg_restore exited %s. The transaction rolled back; the database is\n' "$rc" >&2
    printf '        as it was before this ran.\n' >&2
  fi
  return "$rc"
}

# --- read-only reporting ----------------------------------------------------
cmd_status() {
  if [ -s "$STATE_FILE" ]; then cat "$STATE_FILE"; else printf '{}\n'; fi
}

cmd_list() {
  local name
  for name in $(db_files) $(media_files); do
    printf '%s\t%s\n' "$(file_bytes "$BACKUP_DIR/$name")" "$name"
  done
}

# What box-audit.sh calls to ask the two questions it cannot answer from the host:
# is the encryption real, and is the key still sitting beside the backups it opens.
cmd_proof() {
  local newest wrong="$WORK_DIR/proof-wrong.bin"
  newest="$(db_files | head -1)"
  if [ -z "$newest" ]; then
    printf 'NEWEST=\nWRONGPASS=unknown\nKEY_ON_BOX=%s\n' "$([ -s "$PASS_FILE" ] && printf yes || printf no)"
    return 0
  fi
  mkdir -p "$WORK_DIR" 2>/dev/null
  local opens=no
  if openssl enc -d "${ENC_ARGS[@]}" -pass "pass:$WRONG_PASS" -in "$BACKUP_DIR/$newest" -out "$wrong" 2>/dev/null \
     && [ "$(head -c 5 "$wrong" 2>/dev/null)" = "PGDMP" ]; then
    opens=yes
  fi
  rm -f "$wrong" 2>/dev/null
  printf 'NEWEST=%s\nWRONGPASS_OPENS=%s\nKEY_ON_BOX=%s\nOFFBOX_DEV=%s\nBACKUP_DEV=%s\n' \
    "$newest" "$opens" \
    "$([ -s "$PASS_FILE" ] && printf yes || printf no)" \
    "$(stat -c %d "$OFFBOX_DIR" 2>/dev/null)" \
    "$(stat -c %d "$BACKUP_DIR" 2>/dev/null)"
  return 0
}

cmd_export_key() {
  if [ -s "$PASS_FILE" ]; then cat "$PASS_FILE"; return 0; fi
  printf 'no passphrase on this box yet -- it is written on the first backup run\n' >&2
  return 1
}

# --- scheduling -------------------------------------------------------------
# Due if it is overdue AND (we are in the quiet window OR it is REALLY overdue). The
# second arm is not a nicety: a school box is switched off at the end of the day and
# on again at eight, so a rule that only ever fires between 01:00 and 05:00 would fire
# never. Half an interval past due, the backup matters more than the quiet.
#
# The interval is a parameter so the media archive and the restore drill go through
# the SAME rule rather than a bare age comparison. They are the two heaviest things
# this service does -- a whole-tree tar and a whole-database restore -- and a bare age
# check would happily start one at eleven on a Tuesday morning.
is_due() {
  local last="${1:-0}" interval hour age
  interval=$(( ${2:-$INTERVAL_HOURS} * 3600 ))
  age=$(( $(now_epoch) - last ))
  [ "$age" -lt "$interval" ] && return 1
  [ "$age" -ge $(( interval + interval / 2 )) ] && return 0
  hour="$(date +%H)"
  hour="${hour#0}"
  : "${hour:=0}"
  if [ "$WINDOW_START" -le "$WINDOW_END" ]; then
    [ "$hour" -ge "$WINDOW_START" ] && [ "$hour" -lt "$WINDOW_END" ] && return 0
  else
    { [ "$hour" -ge "$WINDOW_START" ] || [ "$hour" -lt "$WINDOW_END" ]; } && return 0
  fi
  return 1
}

run_loop() {
  log "box backup service starting"
  log "dumps in $BACKUP_DIR, key in $KEY_DIR, off-box target $OFFBOX_DIR"
  log "every ${INTERVAL_HOURS}h, window ${WINDOW_START}:00-${WINDOW_END}:00, keep ${RET_DAILY}d/${RET_WEEKLY}w/${RET_MONTHLY}m under ${CAP_BYTES} bytes"
  # Let the box finish booting. Migrations run on web's boot and hold DDL locks; a
  # dump that starts into the middle of them just waits out its lock timeout and
  # records a skip for nothing.
  sleep "$SETTLE_SECONDS" &
  wait $! 2>/dev/null
  while true; do
    state_load
    if is_due "${S_LAST_SUCCESS_EPOCH:-0}"; then
      run_backup
    fi
    state_load
    if [ "$MEDIA_MODE" != "off" ] && is_due "${S_MEDIA_EPOCH:-0}" "$MEDIA_INTERVAL_HOURS"; then
      run_media
    fi
    state_load
    if [ "$DRILL_DAYS" -gt 0 ] && is_due "${S_DRILL_EPOCH:-0}" $(( DRILL_DAYS * 24 )); then
      run_drill
    fi
    sleep "$POLL_SECONDS" &
    wait $! 2>/dev/null
  done
}

# --- dispatch ---------------------------------------------------------------
main() {
  local cmd="${1:-loop}"
  shift 2>/dev/null || true
  case "$cmd" in
    loop)    run_loop ;;
    once)    run_backup ;;
    media)   run_media ;;
    drill)   run_drill ;;
    verify)
      state_load
      preflight || { printf 'STOPPED %s\n' "$PREFLIGHT_ERROR" >&2; exit 1; }
      local newest
      newest="$(db_files | head -1)"
      [ -n "$newest" ] || { printf 'no dump on this box\n' >&2; exit 1; }
      if verify_dump "$newest"; then
        S_VERIFIED_AT="$(now_iso)"
        S_VERIFIED_FILE="$newest"
        S_VERIFIED_TOC="$VERIFY_TOC"
        S_VERIFIED_FULL_READ="$VERIFY_FULL"
        S_ENCRYPTION_REAL="$VERIFY_ENC"
        state_write
        printf 'ok %s: %s archive entries, read back end to end, encryption real=%s\n' \
          "$newest" "$VERIFY_TOC" "$VERIFY_ENC"
      else
        printf 'FAILED %s: %s\n' "$newest" "$VERIFY_ERROR" >&2
        exit 1
      fi
      ;;
    restore)    do_restore "$@" ;;
    status)     cmd_status ;;
    list)       cmd_list ;;
    proof)      cmd_proof ;;
    export-key) cmd_export_key ;;
    *)
      printf 'usage: box-backup.sh {loop|once|media|drill|verify|restore|status|list|proof|export-key}\n' >&2
      exit 2
      ;;
  esac
}

main "$@"
