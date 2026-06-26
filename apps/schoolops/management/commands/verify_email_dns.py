"""Verify the email-deliverability DNS posture for a domain (SPF / DKIM / DMARC).

The RunMyCampus sending path (Brevo SMTP via ``apps.schoolops.email_delivery``)
is already correct; the recurring deliverability gap is DNS, which lives in the
registrar (Porkbun) and can drift silently. This command turns "remember to
check the dashboard" into one auditable command:

    python manage.py verify_email_dns                 # checks MULTI_TENANT_BASE_DOMAIN
    python manage.py verify_email_dns --domain x.org
    python manage.py verify_email_dns --json          # machine-readable, for CI / cron

Checks (all read-only DNS lookups):
  1. SPF  — a single root TXT ``v=spf1 …`` that authorizes Brevo
            (``include:spf.brevo.com``).
  2. DKIM — ``brevo1`` / ``brevo2._domainkey`` CNAME into ``*.dkim.brevo.com``.
  3. Stray DKIM — ``s1._domainkey`` must NOT point at the web-app host
                  (``*.onrender.com``); a leftover record there is a red flag.
  4. DMARC — ``_dmarc`` TXT ``v=DMARC1`` exists; the current policy is reported
             with the recommended ``none → quarantine → reject`` progression.

The verdict helpers are pure functions (no network) so they unit-test without
live DNS; ``handle`` only does the resolving + presentation. Exits non-zero when
any CRITICAL check fails, so it can gate a deploy or run as a cron canary.
"""

from __future__ import annotations

import json
from typing import Optional

from django.conf import settings
from django.core.management.base import BaseCommand

# ── Expected values (the Brevo + Porkbun contract; not hardcoded per-domain) ──
BREVO_SPF_INCLUDE = "include:spf.brevo.com"
BREVO_DKIM_SELECTORS = ("brevo1", "brevo2")
BREVO_DKIM_TARGET_SUFFIX = "dkim.brevo.com"
STRAY_DKIM_SELECTOR = "s1"
STRAY_DKIM_BAD_SUBSTR = "onrender.com"
DMARC_MARKER = "v=dmarc1"

SEVERITY_CRITICAL = "critical"
SEVERITY_WARNING = "warning"
SEVERITY_INFO = "info"


def _result(name, severity, passed, message, fix=""):
    return {
        "name": name,
        "severity": severity,
        "passed": bool(passed),
        "message": message,
        "fix": fix,
    }


def evaluate_spf(txt_records, domain: str) -> dict:
    """Verdict for the root SPF record. ``txt_records`` = list of root TXT strings."""
    spf = [t for t in txt_records if t.strip().lower().startswith("v=spf1")]
    if not spf:
        return _result(
            "spf",
            SEVERITY_CRITICAL,
            False,
            "No SPF record found at the domain root.",
            fix=f'Add a TXT record on {domain}: "v=spf1 include:_spf.porkbun.com {BREVO_SPF_INCLUDE} ~all"',
        )
    if len(spf) > 1:
        return _result(
            "spf",
            SEVERITY_CRITICAL,
            False,
            f"Multiple SPF records ({len(spf)}) — RFC 7208 allows exactly one; mail will fail SPF.",
            fix="Merge into ONE TXT record; never publish a second v=spf1 record.",
        )
    record = spf[0]
    if BREVO_SPF_INCLUDE not in record.lower():
        return _result(
            "spf",
            SEVERITY_CRITICAL,
            False,
            f"SPF does not authorize Brevo (missing {BREVO_SPF_INCLUDE}): {record!r}",
            fix=f'Edit the single SPF TXT to include Brevo, e.g. "v=spf1 include:_spf.porkbun.com {BREVO_SPF_INCLUDE} ~all"',
        )
    return _result("spf", SEVERITY_CRITICAL, True, f"SPF authorizes Brevo: {record!r}")


def evaluate_dkim(selector: str, cname_target: Optional[str], domain: str) -> dict:
    """Verdict for one Brevo DKIM selector CNAME (target string or None)."""
    fqdn = f"{selector}._domainkey.{domain}"
    if not cname_target:
        return _result(
            f"dkim_{selector}",
            SEVERITY_CRITICAL,
            False,
            f"{fqdn} does not resolve (no CNAME).",
            fix=f"Add the Brevo DKIM CNAME for {selector} from the Brevo → Senders → Domains panel.",
        )
    if BREVO_DKIM_TARGET_SUFFIX not in cname_target.lower():
        return _result(
            f"dkim_{selector}",
            SEVERITY_CRITICAL,
            False,
            f"{fqdn} CNAME points to {cname_target!r}, not *.{BREVO_DKIM_TARGET_SUFFIX}.",
            fix=f"Repoint {selector}._domainkey to the Brevo-provided *.{BREVO_DKIM_TARGET_SUFFIX} target.",
        )
    return _result(
        f"dkim_{selector}",
        SEVERITY_CRITICAL,
        True,
        f"{fqdn} → {cname_target} (Brevo DKIM ok).",
    )


def evaluate_stray_dkim(cname_target: Optional[str], domain: str) -> dict:
    """Verdict for the stray ``s1._domainkey`` record (should be absent / not the app host)."""
    fqdn = f"{STRAY_DKIM_SELECTOR}._domainkey.{domain}"
    if not cname_target:
        return _result(
            "stray_dkim",
            SEVERITY_INFO,
            True,
            f"{fqdn} is absent (good).",
        )
    if STRAY_DKIM_BAD_SUBSTR in cname_target.lower():
        return _result(
            "stray_dkim",
            SEVERITY_WARNING,
            False,
            f"{fqdn} CNAMEs to the web-app host ({cname_target!r}) — a leftover, not a DKIM key.",
            fix=f"DELETE the {fqdn} record; it is not a signing key and confuses DKIM validators.",
        )
    return _result(
        "stray_dkim",
        SEVERITY_INFO,
        True,
        f"{fqdn} resolves to {cname_target} (not the app host; review if unexpected).",
    )


def evaluate_dmarc(txt_records, domain: str) -> dict:
    """Verdict for the ``_dmarc`` TXT policy (presence + policy strength)."""
    dmarc = [t for t in txt_records if t.strip().lower().startswith(DMARC_MARKER)]
    if not dmarc:
        return _result(
            "dmarc",
            SEVERITY_WARNING,
            False,
            f"No DMARC record at _dmarc.{domain}.",
            fix=f'Add TXT _dmarc.{domain}: "v=DMARC1; p=none; rua=mailto:postmaster@{domain}" then progress to quarantine/reject.',
        )
    record = dmarc[0]
    policy = ""
    for part in record.split(";"):
        part = part.strip()
        if part.lower().startswith("p="):
            policy = part.split("=", 1)[1].strip().lower()
            break
    if policy in ("quarantine", "reject"):
        return _result(
            "dmarc",
            SEVERITY_INFO,
            True,
            f"DMARC enforced (p={policy}): {record!r}",
        )
    return _result(
        "dmarc",
        SEVERITY_WARNING,
        True,
        f"DMARC present but monitoring-only (p={policy or 'none'}).",
        fix="After ~2 weeks of clean aggregate reports, step p=none → p=quarantine; pct=100 → p=reject.",
    )


def _default_domain() -> str:
    return (getattr(settings, "MULTI_TENANT_BASE_DOMAIN", "") or "").strip().lower()


class Command(BaseCommand):
    help = "Verify email-deliverability DNS (SPF / DKIM / DMARC) for a domain."

    def add_arguments(self, parser):
        parser.add_argument(
            "--domain",
            default="",
            help="Domain to check (default: settings.MULTI_TENANT_BASE_DOMAIN).",
        )
        parser.add_argument(
            "--json",
            action="store_true",
            help="Emit machine-readable JSON instead of a human-readable report.",
        )

    # -- DNS resolution (kept out of the pure verdict helpers) --------------
    def _resolve_txt(self, name: str):
        try:
            import dns.resolver  # noqa: PLC0415 — optional dep, lazy

            answers = dns.resolver.resolve(name, "TXT")
            out = []
            for r in answers:
                # dnspython TXT rdata splits long records into chunks of bytes.
                strings = getattr(r, "strings", None)
                if strings:
                    out.append(b"".join(strings).decode("utf-8", "replace"))
                else:
                    out.append(str(r).strip('"'))
            return out
        except Exception:  # noqa: BLE001 — NXDOMAIN/NoAnswer/lib-missing → empty
            return []

    def _resolve_cname(self, name: str) -> Optional[str]:
        try:
            import dns.resolver  # noqa: PLC0415

            answers = dns.resolver.resolve(name, "CNAME")
            for r in answers:
                return str(getattr(r, "target", r)).rstrip(".")
            return None
        except Exception:  # noqa: BLE001 — NXDOMAIN means "absent", which is data
            return None

    def handle(self, *args, **options):
        domain = (options.get("domain") or _default_domain()).strip().lower().rstrip(".")
        as_json = options.get("json")
        if not domain:
            self.stderr.write(
                "No domain — pass --domain or set MULTI_TENANT_BASE_DOMAIN."
            )
            raise SystemExit(2)

        try:
            import dns.resolver  # noqa: F401,PLC0415
        except Exception:  # noqa: BLE001
            msg = "dnspython is not importable; install dnspython>=2.4 to run DNS checks."
            if as_json:
                self.stdout.write(json.dumps({"domain": domain, "error": msg}))
            else:
                self.stderr.write(msg)
            raise SystemExit(2)

        root_txt = self._resolve_txt(domain)
        dmarc_txt = self._resolve_txt(f"_dmarc.{domain}")
        results = [evaluate_spf(root_txt, domain)]
        for selector in BREVO_DKIM_SELECTORS:
            target = self._resolve_cname(f"{selector}._domainkey.{domain}")
            results.append(evaluate_dkim(selector, target, domain))
        results.append(
            evaluate_stray_dkim(
                self._resolve_cname(f"{STRAY_DKIM_SELECTOR}._domainkey.{domain}"),
                domain,
            )
        )
        results.append(evaluate_dmarc(dmarc_txt, domain))

        critical_failures = [
            r for r in results if not r["passed"] and r["severity"] == SEVERITY_CRITICAL
        ]
        verdict = "FAIL" if critical_failures else "PASS"

        if as_json:
            self.stdout.write(
                json.dumps(
                    {
                        "domain": domain,
                        "verdict": verdict,
                        "critical_failures": len(critical_failures),
                        "checks": results,
                    },
                    indent=2,
                )
            )
        else:
            self.stdout.write(f"Email DNS posture for {domain}: {verdict}\n")
            for r in results:
                icon = "OK " if r["passed"] else "!! "
                self.stdout.write(f"  {icon}[{r['severity']:<8}] {r['name']}: {r['message']}")
                if not r["passed"] and r["fix"]:
                    self.stdout.write(f"        fix -> {r['fix']}")
            if critical_failures:
                self.stdout.write(
                    f"\n{len(critical_failures)} critical issue(s). Edit DNS at the registrar (Porkbun), then re-run."
                )

        if critical_failures:
            raise SystemExit(1)
