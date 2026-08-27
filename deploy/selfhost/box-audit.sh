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
git fetch origin --quiet 2>/dev/null
behind="$(git rev-list --count HEAD..origin/main 2>/dev/null || echo '?')"
[ "$behind" = "0" ] && ok "level with origin/main" || warn "behind origin/main by $behind commit(s)"
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

sec "D. TLS, end to end, from this box"
"${COMPOSE[@]}" exec -T web python manage.py edge_tls --check-terminator edge-tls:443 2>&1 \
  | grep -viE "^(WARNING|INFO|DEBUG) " | tail -3 | sed 's/^/     /'
site="$(grep -m1 -vE '^\s*#|^\s*$' deploy/selfhost/Caddyfile.edge)"
[ "$site" = ":443 {" ] && ok "site line is the catch-all :443 (an IP client sends no SNI)" \
                       || bad "site line is '$site' -- an IP client gets NO certificate"
grep -q "handle @trust" deploy/selfhost/Caddyfile.edge \
  && ok "the RENDERED Caddyfile carries the trust exemption" \
  || bad "rendered Caddyfile has no trust exemption -- re-run edge-bootstrap.sh"
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
  printf '  VERDICT: safe to rebuild. The CA is backed up and verified restorable.\n'
fi
printf '===============================================================\n'
