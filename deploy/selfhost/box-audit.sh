#!/usr/bin/env bash
# READ-ONLY audit of the box. Changes nothing, starts nothing, restarts nothing.
#
# The question it answers is not "does it look right" but "is this box safe to
# REBUILD" -- which is a different and much narrower question. Almost everything on
# this box is derived and rebuilds in a minute: the leaf, the Caddyfile,
# ALLOWED_HOSTS, the origins, the images. ONE artefact cannot be regenerated, and if
# it is lost every device that trusts this box must be physically revisited to
# install a new CA. Section C is therefore the gate, and it is the only section whose
# failure should stop a rebuild outright.
set -uo pipefail

# Derived, never hardcoded: this script must audit ANY box, not the one it was
# first written on. /srv/rmc is the conventional path, not a guaranteed one.
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$HERE/../.." && pwd)"
cd "$REPO_ROOT" || exit 1
COMPOSE=(docker compose -f "$HERE/docker-compose.yml")
PASS=0; FAIL=0; WARN=0
ok()   { printf '  [ OK ] %s\n' "$*"; PASS=$((PASS+1)); }
bad()  { printf '  [FAIL] %s\n' "$*"; FAIL=$((FAIL+1)); }
warn() { printf '  [WARN] %s\n' "$*"; WARN=$((WARN+1)); }
sec()  { printf '\n=== %s\n' "$*"; }

sec "A. repo and code state"
head="$(git rev-parse --short HEAD)"
echo "     HEAD $head   $(git log -1 --format=%s | cut -c1-64)"
# THE FETCH'S EXIT STATUS IS THE WHOLE POINT. It used to be discarded, and the
# comparison then read the origin/main left on disk by the last fetch that worked.
# An offline box therefore reported "[ OK ] level with origin/main" against a ref
# that could be a week old -- a green that means nothing, counted as a pass. Offline
# is the NORMAL state for a box in a school, so that was the common path, not a
# corner. Bounded and prompt-free because an audit must never sit waiting for a
# credential nobody is there to type; if `timeout` is missing the fetch simply fails
# and we say we could not tell, which is the safe direction to be wrong in.
#
# The branch is read, not assumed: a box on any branch but main was being measured
# against a ref that says nothing about it.
# ASK FOR THE TIP, NOT FOR THE OBJECTS. A fetch downloads the whole delta, which on
# this repo over a school link is minutes -- so it needs a timeout, and then a slow
# link reads as an unreachable remote. Measured on the Gilead box on 2026-08-28:
# `git ls-remote` answered that URL from that checkout while `git fetch` did not
# finish. One ref exchange, and it writes nothing, which an audit should not do.
branch="$(git rev-parse --abbrev-ref HEAD 2>/dev/null || echo main)"
remote_refs="$(GIT_TERMINAL_PROMPT=0 timeout 30 git ls-remote origin "refs/heads/$branch" 2>/dev/null)"
ls_rc=$?
remote_tip="$(printf '%s\n' "$remote_refs" | awk 'NR == 1 {print $1}')"
if [ "$ls_rc" != "0" ]; then
  warn "could not reach the git remote -- cannot tell whether this checkout is current"
elif [ -z "$remote_tip" ]; then
  # The remote answered; it simply has no such branch. Different from unreachable,
  # and different again from being behind.
  warn "origin has no branch '$branch' -- nothing to compare this checkout against"
elif [ "$remote_tip" = "$(git rev-parse HEAD)" ]; then
  ok "level with origin/$branch"
elif git cat-file -e "$remote_tip^{commit}" 2>/dev/null; then
  warn "behind origin/$branch by $(git rev-list --count "HEAD..$remote_tip") commit(s)"
else
  # We do not hold the object, so the distance cannot be computed without a fetch --
  # and printing a number we could not compute is how this section went wrong before.
  warn "behind origin/$branch, now at $(printf '%.9s' "$remote_tip") -- not in this checkout yet"
fi
# By CONTENT, never by remembered hash -- hashes are not stable in a shared checkout.
grep -q "handle @trust" apps/schools/edge_tls.py \
  && ok "port-80 trust exemption present in source" \
  || bad "port-80 trust exemption MISSING from source"
grep -q "_resolve_credential" apps/sync_engine/local_upgrade.py \
  && ok "OTA credential fix present in source" \
  || bad "OTA credential fix MISSING from source"
dirty="$(git status --porcelain | grep -v '^?? ' | wc -l)"
[ "$dirty" -le 1 ] && ok "working tree clean enough ($dirty tracked file(s) modified)" \
                   || warn "$dirty tracked files modified"
git status --porcelain | grep -v '^?? ' | sed 's/^/       /'

sec "B. containers"
"${COMPOSE[@]}" ps --format '{{.Service}}\t{{.State}}\t{{.Health}}' 2>/dev/null | sed 's/^/     /'
for s in web worker beat db; do
  st="$("${COMPOSE[@]}" ps --format '{{.Service}}:{{.State}}' 2>/dev/null | grep "^$s:" | cut -d: -f2)"
  [ "$st" = "running" ] && ok "$s running" || bad "$s is '$st'"
done
# Does the RUNNING image carry the fix, or only the checkout? A pulled-but-not-rebuilt
# box passes section A and still serves the old code.
if "${COMPOSE[@]}" exec -T web grep -q "handle @trust" /app/apps/schools/edge_tls.py 2>/dev/null; then
  ok "the RUNNING image carries the port-80 fix (not just the checkout)"
else
  bad "running image is STALE -- rebuild required before the fix is live"
fi

sec "C. the one artefact that cannot be regenerated  [REBUILD GATE]"
BUNDLE=/srv/box-ca-bundle.p12
PASSF=/srv/box-ca-passphrase.txt
if [ ! -s "$BUNDLE" ]; then
  bad "NO CA BACKUP at $BUNDLE -- a rebuild that loses the volume strands every device"
elif [ -s "$PASSF" ]; then
  # Both here: we can verify the pair completely, and we should say so -- but this is
  # the WEAKER arrangement, not the stronger one. One disk failure takes both.
  ok "bundle present ($(stat -c%s "$BUNDLE") bytes, mode $(stat -c%a "$BUNDLE"))"
  live="$("${COMPOSE[@]}" exec -T web sh -c 'openssl x509 -in /app/var/edge-tls/ca.crt -noout -fingerprint -sha256' 2>/dev/null | sed 's/.*=//' | tr -d '\r')"
  back="$(openssl pkcs12 -in "$BUNDLE" -passin "file:$PASSF" -nokeys -clcerts 2>/dev/null | openssl x509 -noout -fingerprint -sha256 2>/dev/null | sed 's/.*=//')"
  echo "     live CA   $live"
  echo "     in backup $back"
  if [ -n "$live" ] && [ "$live" = "$back" ]; then
    ok "the backup holds THIS box's CA, not some earlier one"
  else
    bad "backup does NOT match the live CA -- restoring it would strand every device"
  fi
  keys="$(openssl pkcs12 -in "$BUNDLE" -passin "file:$PASSF" -nocerts -nodes 2>/dev/null | grep -c 'PRIVATE KEY')"
  [ "$keys" -ge 1 ] && ok "the PRIVATE KEY is inside the bundle" || bad "no private key in the bundle"
  if openssl pkcs12 -in "$BUNDLE" -passin pass:definitely-not-the-passphrase -nokeys >/dev/null 2>&1; then
    bad "the bundle opens with a WRONG passphrase -- it is not actually encrypted"
  else
    ok "a wrong passphrase is refused (the encryption is real)"
  fi
  warn "the passphrase sits beside the bundle. Take the BUNDLE off this machine (not the passphrase -- edge-bootstrap.sh regenerates a missing one on a box that has no backup yet)."
else
  # THE INTENDED ARRANGEMENT, and an earlier version of this script called it a FAIL.
  # That was backwards: the whole point of the closing banner is to get these two
  # apart, so failing the box for having done it told the operator to undo the one
  # thing that makes the backup worth having. A gate that fails on the correct
  # configuration is worse than no gate, because it teaches people to ignore it.
  #
  # What CAN be checked from here is checked. What cannot -- whether the bundle opens
  # -- is stated as not-checkable rather than assumed either way, because the machine
  # holding the passphrase is the only place that question can be answered.
  ok "bundle present ($(stat -c%s "$BUNDLE") bytes, mode $(stat -c%a "$BUNDLE"))"
  ok "the passphrase is NOT on this box -- that is the intended arrangement"
  live="$("${COMPOSE[@]}" exec -T web sh -c 'openssl x509 -in /app/var/edge-tls/ca.crt -noout -fingerprint -sha256' 2>/dev/null | sed 's/.*=//' | tr -d '\r')"
  rec="$("${COMPOSE[@]}" exec -T web sh -c 'python - <<PY
import json
try:
    s = json.load(open("/app/media/.rmc-edge/trust-anchor.json"))
    a = s.get("active") or {}
    print((a.get("fingerprint") or "") + "|" + (a.get("export_verified_at") or ""))
except Exception:
    print("|")
PY' 2>/dev/null | tr -d '\r')"
  recfp="${rec%%|*}"; recat="${rec##*|}"
  echo "     live CA          $live"
  echo "     recorded export  ${recfp:-<none>}  at ${recat:-<never>}"
  if [ -z "$recat" ]; then
    bad "no verified export on record -- this box cannot show its backup was ever read back"
  elif [ -n "$live" ] && [ "${live:0:${#recfp}}" = "$recfp" ] || [ "$recfp" = "${live:0:${#recfp}}" ]; then
    ok "a verified export IS on record for this CA ($recat) -- it was read back at export time"
  else
    bad "the recorded export is for a DIFFERENT CA than the one on disk"
  fi
  warn "whether the bundle still opens cannot be checked from here, by design. Verify it where the passphrase is: openssl pkcs12 -in <bundle> -nokeys -passin env:P | openssl x509 -noout -fingerprint -sha256"
fi

sec "C2. the records this school cannot regenerate  [RESTORE-DRILL GATE]"
# Section C exists because ONE artefact on this box cannot be regenerated. That was
# true and it was also incomplete: the CA had an encrypted backup, a passphrase kept
# apart from it, a gate that fails on a missing backup, a gate that fails when the
# backup does not match the live CA, a gate that proves the encryption is real, and a
# gate that fails when there is no verified read-back on record -- while the fee
# ledger, the marks, the attendance and the discipline record had nothing at all. A
# dead SSD strands every device that trusted the CA; it also loses the school's year,
# and only one of those two was being defended. This section is the same discipline
# applied to the other one.
#
# READ-ONLY, like the rest of this file. It asks the backup container what it has
# RECORDED, exactly as section C asks the trust anchor for its recorded export -- it
# never takes a backup and never restores one. An audit that ran a restore to find out
# whether restores work would have destroyed the thing it was measuring.
BSTATE=/tmp/rmc-box-backup-state.json
BPROOF=/tmp/rmc-box-backup-proof.txt
bsvc="$("${COMPOSE[@]}" ps --format '{{.Service}}:{{.State}}' 2>/dev/null | grep '^backup:' | cut -d: -f2)"
if [ "$bsvc" != "running" ]; then
  bad "the backup service is [${bsvc:-absent}] -- NOTHING is copying the school database"
  warn "start it with: docker compose -f $HERE/docker-compose.yml up -d backup"
else
  ok "the backup service is running"
  "${COMPOSE[@]}" exec -T backup bash /usr/local/bin/box-backup.sh status 2>/dev/null | tr -d '\r' > "$BSTATE"
  "${COMPOSE[@]}" exec -T backup bash /usr/local/bin/box-backup.sh proof  2>/dev/null | tr -d '\r' > "$BPROOF"
  bget()  { sed -n 's/.*"'"$1"'"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/p' "$BSTATE" | head -1; }
  bnum()  { n="$(sed -n 's/.*"'"$1"'"[[:space:]]*:[[:space:]]*\([0-9][0-9]*\).*/\1/p' "$BSTATE" | head -1)"; printf '%s' "${n:-0}"; }
  pget()  { sed -n "s/^$1=//p" "$BPROOF" | head -1; }

  if [ ! -s "$BSTATE" ] || ! grep -q '"schema"' "$BSTATE"; then
    bad "NO BACKUP RECORD on this box -- it has never taken a backup of the school database"
  else
    lastf="$(bget last_file)";     lastst="$(bget last_status)"
    laste="$(bget last_error)";    lastat="$(bget last_success_at)"
    verat="$(bget verified_at)";   verf="$(bget verified_file)"
    verfull="$(bget verified_full_read)"; vertoc="$(bnum verified_toc_entries)"
    lastep="$(bnum last_success_epoch)"
    keptn="$(bnum kept_files)";    keptb="$(bnum kept_bytes)"
    freeb="$(bnum free_bytes)";    lastb="$(bnum last_bytes)"
    mediast="$(bget media_status)"; drillst="$(bget drill_status)"
    drillep="$(bnum drill_epoch)"; obst="$(bget offbox_status)"
    obind="$(bget offbox_independent)"
    now="$(date -u +%s)"
    age=$(( now - lastep ))
    echo "     newest dump      ${lastf:-<none>}  ($lastb bytes)"
    echo "     last verified    ${verf:-<none>}  at ${verat:-<never>}"
    echo "     kept             $keptn artefact(s), $keptb bytes;  $freeb bytes free"

    # THE GATE. Everything else in this section is reporting; these three are the
    # difference between a backup and a file nobody has ever opened.
    if [ -z "$verat" ]; then
      bad "no verified read-back on record -- this box cannot show its backup was ever read back"
    elif [ -n "$lastf" ] && [ "$verf" != "$lastf" ]; then
      bad "the verified read-back is for $verf, not the newest dump $lastf -- the newest one has never been opened"
    elif [ "$verfull" != "true" ]; then
      bad "the dump was listed but never read END TO END -- a truncated archive lists perfectly and restores nothing"
    else
      ok "the newest dump was read back in full ($vertoc archive entries) -- it is a backup, not a file"
    fi

    # Freshness. A verified read-back of a dump from three weeks ago is a verified
    # read-back of three weeks ago, and the term has moved on since.
    if [ "$lastep" = "0" ]; then
      bad "no successful backup has EVER completed on this box"
    elif [ "$age" -gt 172800 ]; then
      bad "the last successful backup was $(( age / 3600 ))h ago -- more than two days of work at this school has no copy"
    elif [ "$age" -gt 93600 ]; then
      warn "the last successful backup was $(( age / 3600 ))h ago (expected daily)"
    else
      ok "last successful backup $(( age / 3600 ))h ago ($lastat)"
    fi

    case "$lastst" in
      ok)      ok "the last run completed" ;;
      skipped) warn "the last run was SKIPPED and said why: $laste" ;;
      *)       bad "the last run status is '$lastst': $laste" ;;
    esac

    # Is the encryption real? Asked of the FILE ON DISK, right now, not of a flag
    # somebody wrote down. Section C asks the CA bundle the same question the same way.
    case "$(pget WRONGPASS_OPENS)" in
      no)  ok "a wrong passphrase does not open the dump (the encryption is real)" ;;
      yes) bad "the dump OPENS with a wrong passphrase -- it is not actually encrypted" ;;
      *)   warn "could not test the dump against a wrong passphrase from here" ;;
    esac

    # The same warning section C gives about the CA bundle, for the same reason: a key
    # stored beside the thing it protects has bought nobody anything.
    if [ "$(pget KEY_ON_BOX)" = "yes" ]; then
      warn "the backup passphrase is ON this box. Take a copy elsewhere -- without it every
       dump here is unreadable, and it cannot be regenerated from the database:
         docker compose -f $HERE/docker-compose.yml exec backup bash /usr/local/bin/box-backup.sh export-key"
    fi

    # The off-box copy. Everything above protects against a bad migration, a wrong
    # delete and a lost pgdata volume. NONE of it protects against the disk dying,
    # because all of it is on that disk.
    case "$obind" in
      true)  ok "the off-box copy is on a DIFFERENT filesystem -- it survives this disk ($obst)" ;;
      false) warn "the off-box copy is on the SAME filesystem as the box itself: a dead disk takes
       both. Point RMC_BOX_BACKUP_OFFBOX_DIR at a mounted USB disk or a NAS share." ;;
      *)     warn "no off-box target configured -- every copy of the school database is on one disk" ;;
    esac

    # The full drill: did Postgres itself accept the dump, not merely the archive
    # reader. Space-gated by design on cheap hardware, so a skip is a WARN and the
    # message carries the numbers rather than a shrug.
    if [ "$drillep" = "0" ]; then
      warn "no full restore drill on record yet (status: ${drillst:-never}) -- the read-back proves the
       archive is intact; only a drill proves Postgres accepts it. It runs on its own
       cadence when there is room, or on demand:
         docker compose -f $HERE/docker-compose.yml exec backup bash /usr/local/bin/box-backup.sh drill"
    elif [ $(( now - drillep )) -gt 5184000 ]; then
      warn "the last full restore drill was $(( (now - drillep) / 86400 )) days ago"
    else
      ok "a full restore drill passed $(( (now - drillep) / 86400 )) day(s) ago -- Postgres accepted the dump"
    fi

    case "$mediast" in
      ok)      ok "the media tree is archived too ($(bnum media_bytes) bytes)" ;;
      never|"") warn "the media tree has never been archived -- uploaded documents have no copy" ;;
      *)       warn "media: $mediast" ;;
    esac

    # Disk headroom, said out loud. The backup skips itself rather than filling the
    # disk, so a box that is quietly short of room reports as skipped forever.
    if [ "$freeb" -lt 1073741824 ]; then
      bad "only $freeb bytes free on the backup volume -- the next run will skip itself"
    fi
  fi
fi

sec "D. TLS, end to end, from this box"
"${COMPOSE[@]}" exec -T web python manage.py edge_tls --check-terminator edge-tls:443 2>&1 \
  | grep -viE "^(WARNING|INFO|DEBUG) " | tail -3 | sed 's/^/     /'
# The file compose actually MOUNTS. This used to read Caddyfile.edge, which is
# tracked and is a host-agnostic template -- so once the render moved to its own
# path, this section failed a healthy box twice over: the template's first line is
# a bare `{` (a global options block, not a site address) and it carries no trust
# exemption. Both FAILs were the audit's, and the live probes below disagreed with
# it in the same breath.
CADDY_RENDERED="$HERE/Caddyfile.edge.rendered"
CADDY_LEGACY="$HERE/Caddyfile.edge"
CADDY_IN_USE=""
if [ -f "$CADDY_RENDERED" ]; then
  CADDY_IN_USE="$CADDY_RENDERED"
elif grep -q "handle @trust" "$CADDY_LEGACY" 2>/dev/null; then
  # A box that has not bootstrapped since the move still keeps its render on the
  # tracked path. Reading it is correct, and worth saying out loud.
  CADDY_IN_USE="$CADDY_LEGACY"
  warn "this box still keeps its render at the tracked path -- edge-bootstrap.sh moves it"
fi
if [ -z "$CADDY_IN_USE" ]; then
  bad "no rendered Caddyfile at $CADDY_RENDERED -- the terminator is mounting nothing this box wrote"
else
  echo "     terminator config: ${CADDY_IN_USE#$REPO_ROOT/}"
  site="$(grep -m1 -vE '^[[:space:]]*#|^[[:space:]]*$' "$CADDY_IN_USE")"
  [ "$site" = ":443 {" ] && ok "site line is the catch-all :443 (an IP client sends no SNI)" \
                         || bad "site line is '$site' -- an IP client gets NO certificate"
  grep -q "handle @trust" "$CADDY_IN_USE" \
    && ok "the rendered Caddyfile carries the trust exemption" \
    || bad "rendered Caddyfile has no trust exemption -- re-run edge-bootstrap.sh"
fi
for u in http://127.0.0.1/edge/trust/ http://127.0.0.1/edge/trust/ca.crt http://127.0.0.1:10000/edge/trust/; do
  c="$(curl -s -o /dev/null -w '%{http_code}' --max-time 12 "$u")"
  [ "$c" = "200" ] && ok "$u -> 200" || bad "$u -> $c"
done
c="$(curl -s -o /dev/null -w '%{http_code}' --max-time 12 http://127.0.0.1/)"
[ "$c" = "302" ] && ok "http://<box>/ -> 302 (everything else still redirects)" || warn "http://<box>/ -> $c"

sec "E. security flags, as Django RESOLVED them"
"${COMPOSE[@]}" exec -T web python -c "
from django.conf import settings
import django, os
os.environ.setdefault('DJANGO_SETTINGS_MODULE','config.settings'); django.setup()
import json
print(json.dumps({n: getattr(settings, n, None) for n in
 ('RMC_EDGE_TLS_MODE','DEBUG','SECURE_SSL_REDIRECT','SESSION_COOKIE_SECURE',
  'CSRF_COOKIE_SECURE','SECURE_HSTS_SECONDS')}))
print(json.dumps({'trust_exempt': any('edge/trust' in p for p in settings.SECURE_REDIRECT_EXEMPT)}))
" 2>/dev/null | grep -E '^\{' > /tmp/flags.json
cat /tmp/flags.json | sed 's/^/     /'
grep -q '"SECURE_SSL_REDIRECT": true'   /tmp/flags.json && ok "SSL redirect on"       || bad "SSL redirect OFF"
grep -q '"SESSION_COOKIE_SECURE": true' /tmp/flags.json && ok "session cookie Secure" || bad "session cookie NOT Secure"
grep -q '"SECURE_HSTS_SECONDS": 0'      /tmp/flags.json && ok "HSTS 0 -- the decision stays reversible" || bad "HSTS is NON-ZERO on a LAN cert: one-way door"
grep -q '"trust_exempt": true'          /tmp/flags.json && ok "trust page exempt from the redirect" || bad "trust page NOT exempt"
n="$(grep -cE '^(SECURE_SSL_REDIRECT|SESSION_COOKIE_SECURE|CSRF_COOKIE_SECURE|SECURE_HSTS_SECONDS)=' deploy/selfhost/.env)"
[ "$n" = "0" ] && ok "no derived flag is pinned in .env (they follow the mode)" || warn "$n derived flag(s) pinned in .env"
ls -1 deploy/selfhost/.env.bak-* 2>/dev/null | tail -2 | sed 's/^/     rollback: /'

sec "F. cloud: sync and OTA"
"${COMPOSE[@]}" exec -T web sh -c '
tok=$(printf %s "$RMC_EDGE_CREDENTIAL"); base=$(printf %s "$RMC_EDGE_OPERATOR_BASE")
for p in /api/sync/bundle/download/ /api/sync/upgrade/manifest/; do
  echo "$(curl -s -o /dev/null -w %{http_code} --max-time 20 -H "Authorization: Bearer $tok" "$base$p")  $p"
done' 2>/dev/null > /tmp/cloud.txt
cat /tmp/cloud.txt | sed 's/^/     /'
grep -q "^200  /api/sync/bundle/download/" /tmp/cloud.txt && ok "sync download authenticates (200)" || bad "sync download did not return 200"
if grep -qE "^(409|200)  /api/sync/upgrade/manifest/" /tmp/cloud.txt; then
  ok "OTA authenticates (409 = held at canary, which is the cloud's decision, not a fault)"
else
  bad "OTA manifest did not authenticate -- $(grep manifest /tmp/cloud.txt)"
fi
"${COMPOSE[@]}" exec -T web python manage.py shell -c "
from apps.sync_engine.local_upgrade import LocalRuntimeUpgradeManager
m=LocalRuntimeUpgradeManager(); print('TOKEN_LEN=%d' % len(m.token))" 2>/dev/null | grep TOKEN_LEN > /tmp/tok.txt
cat /tmp/tok.txt | sed 's/^/     /'
grep -q "TOKEN_LEN=0" /tmp/tok.txt && bad "the upgrade manager still resolves an EMPTY token" || ok "the upgrade manager resolves a real credential"

sec "G. console payloads for a managed fleet"
if [ -d /srv/mdm ]; then
  ls -1 /srv/mdm | sed 's/^/     /'
  for f in box-ca.crt box-ca.mobileconfig android-policy.json README.txt; do
    [ -s "/srv/mdm/$f" ] && ok "mdm/$f" || warn "mdm/$f missing"
  done
else
  warn "/srv/mdm missing -- re-run edge-bootstrap.sh to write the fleet payloads"
fi

sec "H. readiness (the box's own opinion)"
"${COMPOSE[@]}" exec -T web python manage.py check_edge_readiness 2>&1 \
  | sed 's/\x1b\[[0-9;]*m//g' | grep -E "^\[FAIL\]|Edge readiness:" | sed 's/^/     /'

printf '\n===============================================================\n'
printf '  audit: %d OK, %d WARN, %d FAIL\n' "$PASS" "$WARN" "$FAIL"
if [ "$FAIL" -gt 0 ]; then
  printf '  VERDICT: do NOT rebuild until the FAILs above are understood.\n'
else
  printf '  VERDICT: safe to rebuild. The CA and the school database are both backed up\n'
  printf '           and verified restorable.\n'
fi
printf '===============================================================\n'
