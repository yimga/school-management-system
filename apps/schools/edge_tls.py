"""How a sovereign box gets an HTTPS origin -- and how it changes its mind later.

A box on a school LAN is reached at ``http://10.10.20.137:10000``. That origin is
not a *secure context*, so the browser withholds ``crypto.subtle`` -- and the offline
capability vault, which derives its PIN key with WebCrypto, can never seal. The PIN
dialog said "Local access could not be enabled on this browser", which named the
wrong culprit: every browser behaves this way, and changing browsers cannot help.
Offline continuity has never worked on any plain-HTTP box, and no amount of
application code can make it work. The box needs a certificate.

Which certificate is the SCHOOL's decision, not ours, and the honest answers pull in
opposite directions:

``selfsigned``  The box mints its own. Works with no internet, no domain, no registrar
                and no money -- the only option that holds on a LAN that has never
                seen the outside world. Costs a one-time trust install on each device
                (or a click-through warning, which trains people to click through
                warnings).

``provided``    Certificate and key files supplied by a CA the school already trusts:
                a district / ministry internal CA, or a commercial one. Devices joined
                to the school's directory already trust it -- nothing to install.

``acme``        Fetched automatically from a public CA (Let's Encrypt). No trust
                install anywhere on earth, and renews itself. Requires a PUBLIC DNS
                name and reachability for the challenge, which many sovereign boxes
                deliberately do not have.

``off``         Plain HTTP. Honest, and what the pilot box runs today. Named as a
                mode rather than left as an absence, so readiness can SAY what is
                off and what that costs instead of silently omitting the subject.

THE TRANSITION IS THE FEATURE. A school starts self-signed because it is the only
thing that works on day one, and moves to a real CA when it gets a domain -- or moves
BACK when the domain lapses. Three things make that reversible, and all three are
easy to get wrong:

1. The dependent Django flags are DERIVED from the mode, not hand-set. Four booleans
   (``SECURE_SSL_REDIRECT``, ``SESSION_COOKIE_SECURE``, ``CSRF_COOKIE_SECURE``,
   ``SECURE_HSTS_SECONDS``) decide whether login works at all; ``.env.edge.example``
   already carries a warning block about them because getting them wrong locks
   everyone out with a silent 302 loop. A school flipping ONE mode value must not
   also have to know which four booleans follow from it.

2. HSTS stays off for ``selfsigned`` and ``provided``. This is the load-bearing
   decision. HSTS tells the browser "never speak HTTP to this origin again, for a
   year" -- and an IP literal or a ``.lan`` name is an origin a DIFFERENT box may
   occupy next term. Turning HSTS on for a LAN box makes the choice irreversible from
   the browser side: revert to HTTP and every device that ever visited refuses to
   connect, with no remedy but per-device surgery. Only ``acme`` -- a public name the
   school controls permanently -- gets HSTS.

3. Nothing here is read from the database. These values are consumed while Django
   settings load, before any connection exists, so the cascade is env -> platform
   default. The school's DECISION is recorded during edge onboarding (see
   ``docs/EDGE_TLS_RUNBOOK.md``) and written to the box's ``.env``; ``manage.py
   edge_tls`` reads it back and ``check_edge_readiness`` fails the bring-up when the
   mode and the flags disagree. Do not add a ``SiteSettings`` field for this: it
   would be read too late to matter and would look authoritative while being ignored.
"""
from __future__ import annotations

import ipaddress
import os
import re
from dataclasses import dataclass
from typing import Any

MODE_OFF = "off"
MODE_SELF_SIGNED = "selfsigned"
MODE_PROVIDED = "provided"
MODE_ACME = "acme"

#: Declaration order is also the order they appear in operator-facing output.
TLS_MODES: tuple[str, ...] = (MODE_OFF, MODE_SELF_SIGNED, MODE_PROVIDED, MODE_ACME)

#: Modes that terminate TLS and therefore produce a secure context in the browser.
HTTPS_MODES: frozenset[str] = frozenset({MODE_SELF_SIGNED, MODE_PROVIDED, MODE_ACME})

#: Modes whose certificate is a pair of files on disk we can inspect and expire.
FILE_BACKED_MODES: frozenset[str] = frozenset({MODE_SELF_SIGNED, MODE_PROVIDED})

ENV_MODE = "RMC_EDGE_TLS_MODE"
ENV_DIR = "RMC_EDGE_TLS_DIR"
ENV_CERT = "RMC_EDGE_TLS_CERT"
ENV_KEY = "RMC_EDGE_TLS_KEY"
ENV_HOSTNAMES = "RMC_EDGE_TLS_HOSTNAMES"
ENV_ACME_EMAIL = "RMC_EDGE_TLS_ACME_EMAIL"
ENV_ACME_CA = "RMC_EDGE_TLS_ACME_CA"

DEFAULT_DIR = "/app/var/edge-tls"
DEFAULT_SELF_SIGNED_DAYS = 825  # CA/Browser-Forum leaf ceiling; browsers reject longer

#: Spellings an operator plausibly types, mapped to the canonical mode. ``ca`` is
#: deliberately ``provided``: a certificate FROM a CA arrives as files. Automatic
#: issuance is ``acme``, which is a protocol rather than a kind of authority.
_ALIASES: dict[str, str] = {
    "": MODE_OFF,
    "0": MODE_OFF,
    "no": MODE_OFF,
    "off": MODE_OFF,
    "none": MODE_OFF,
    "http": MODE_OFF,
    "plain": MODE_OFF,
    "disabled": MODE_OFF,
    "1": MODE_SELF_SIGNED,
    "self": MODE_SELF_SIGNED,
    "selfsigned": MODE_SELF_SIGNED,
    "self-signed": MODE_SELF_SIGNED,
    "self_signed": MODE_SELF_SIGNED,
    "internal": MODE_SELF_SIGNED,
    "local": MODE_SELF_SIGNED,
    "ca": MODE_PROVIDED,
    "provided": MODE_PROVIDED,
    "file": MODE_PROVIDED,
    "files": MODE_PROVIDED,
    "custom": MODE_PROVIDED,
    "imported": MODE_PROVIDED,
    "internal-ca": MODE_PROVIDED,
    "internal_ca": MODE_PROVIDED,
    "authority": MODE_PROVIDED,
    "acme": MODE_ACME,
    "auto": MODE_ACME,
    "letsencrypt": MODE_ACME,
    "lets-encrypt": MODE_ACME,
    "public": MODE_ACME,
    "public-ca": MODE_ACME,
}

#: One line per mode for operator-facing output. Kept beside the aliases so a new
#: mode cannot be added without also saying what it costs.
MODE_SUMMARY: dict[str, str] = {
    MODE_OFF: (
        "Plain HTTP. Login works, but the origin is not a secure context: WebCrypto "
        "is withheld, so offline PIN / local-mode enrolment cannot work on any browser."
    ),
    MODE_SELF_SIGNED: (
        "The box mints its own certificate. No internet, domain or cost required. "
        "Install the box CA once per device, or accept a warning each time."
    ),
    MODE_PROVIDED: (
        "Certificate and key files issued by a CA the school already trusts "
        "(district / ministry internal CA, or a commercial one). No trust install "
        "on managed devices; the school owns renewal."
    ),
    MODE_ACME: (
        "Automatic issuance from a public CA (Let's Encrypt). Trusted everywhere and "
        "self-renewing, but needs a public DNS name and reachability for the challenge."
    ),
}


class UnknownTlsMode(ValueError):
    """Raised for a mode spelling we do not recognise. Never silently coerced."""


def normalize_mode(raw: Any) -> str:
    """Canonicalise an operator-typed mode. Raises rather than guessing.

    A typo must not silently become ``off``: that would hand a school plain HTTP
    while its runbook says it chose HTTPS, and nothing downstream would disagree.
    """
    key = str(raw if raw is not None else "").strip().lower()
    if key in _ALIASES:
        return _ALIASES[key]
    raise UnknownTlsMode(
        f"unknown TLS mode {raw!r}; expected one of {', '.join(TLS_MODES)}"
    )


@dataclass(frozen=True)
class TlsResolution:
    """The resolved mode plus WHERE it came from, so readiness can explain itself."""

    mode: str
    source: str
    raw: str = ""
    error: str = ""

    @property
    def serves_https(self) -> bool:
        return self.mode in HTTPS_MODES


def resolve_mode(environ: dict[str, str] | None = None) -> TlsResolution:
    """Resolve the box's TLS mode from the environment.

    Cascade: explicit env var -> platform default (``off``). Deliberately short --
    see the module docstring on why the database is not a layer here.
    """
    env = os.environ if environ is None else environ
    raw = str(env.get(ENV_MODE, "") or "").strip()
    if not raw:
        return TlsResolution(mode=MODE_OFF, source="default", raw="")
    try:
        return TlsResolution(mode=normalize_mode(raw), source=ENV_MODE, raw=raw)
    except UnknownTlsMode as exc:
        # Fall back to the safe-to-boot value, but CARRY the error so
        # check_edge_readiness fails on it, rather than the box quietly serving
        # plain HTTP under a configuration that claims otherwise.
        return TlsResolution(mode=MODE_OFF, source="default", raw=raw, error=str(exc))


def derived_security_flags(mode: str) -> dict[str, Any]:
    """The four Django flags that follow from the mode.

    ``SECURE_HSTS_SECONDS`` is 0 for every LAN mode on purpose -- see point 2 of the
    module docstring. That zero is the difference between a decision and a one-way door.
    """
    mode = normalize_mode(mode)
    https = mode in HTTPS_MODES
    return {
        "SECURE_SSL_REDIRECT": https,
        "SESSION_COOKIE_SECURE": https,
        "CSRF_COOKIE_SECURE": https,
        "SECURE_HSTS_SECONDS": 31536000 if mode == MODE_ACME else 0,
    }


def certificate_paths(environ: dict[str, str] | None = None) -> tuple[str, str, str]:
    """(cert, key, ca) paths. Explicit env wins; else conventional names in the dir."""
    env = os.environ if environ is None else environ
    directory = str(env.get(ENV_DIR, "") or DEFAULT_DIR).strip() or DEFAULT_DIR
    cert = str(env.get(ENV_CERT, "") or "").strip() or os.path.join(directory, "tls.crt")
    key = str(env.get(ENV_KEY, "") or "").strip() or os.path.join(directory, "tls.key")
    ca = os.path.join(directory, "ca.crt")
    return cert, key, ca


_HOST_SPLIT = re.compile(r"[,\s]+")


def san_candidates(
    environ: dict[str, str] | None = None,
    allowed_hosts: list[str] | None = None,
) -> tuple[list[str], list[str]]:
    """(dns_names, ip_addresses) the box must be reachable at, de-duplicated.

    Explicit ``RMC_EDGE_TLS_HOSTNAMES`` wins; otherwise ``ALLOWED_HOSTS``, which the
    box already had to get right for Django to answer at all. A wildcard entry is
    dropped: ``*`` in ALLOWED_HOSTS means "we did not decide", and a certificate
    cannot assert that.

    IP addresses are separated from DNS names because a certificate must carry an IP
    in an ``IPAddress`` SAN entry -- an IP put in a ``DNSName`` entry is ignored by
    every browser, which is the classic way a hand-rolled LAN certificate still shows
    a name-mismatch warning at the address people actually type.
    """
    env = os.environ if environ is None else environ
    raw = str(env.get(ENV_HOSTNAMES, "") or "").strip()
    if raw:
        entries = [e for e in _HOST_SPLIT.split(raw) if e]
    else:
        entries = list(allowed_hosts or [])
    dns: list[str] = []
    ips: list[str] = []
    for entry in entries:
        candidate = str(entry or "").strip().strip(".")
        if not candidate or "*" in candidate:
            continue
        # A host:port entry is common when pasting from CSRF_TRUSTED_ORIGINS; a
        # certificate names the HOST and never the port.
        if candidate.count(":") == 1 and not candidate.startswith("["):
            candidate = candidate.split(":", 1)[0]
        try:
            ipaddress.ip_address(candidate)
        except ValueError:
            if candidate.lower() not in {d.lower() for d in dns}:
                dns.append(candidate)
        else:
            if candidate not in ips:
                ips.append(candidate)
    return dns, ips


@dataclass(frozen=True)
class CertificateFacts:
    """What we can say about a certificate file without trusting its filename."""

    path: str
    exists: bool
    readable: bool = False
    subject: str = ""
    issuer: str = ""
    self_signed: bool = False
    dns_names: tuple[str, ...] = ()
    ip_addresses: tuple[str, ...] = ()
    not_before: str = ""
    not_after: str = ""
    days_remaining: int | None = None
    error: str = ""

    def covers(self, dns: list[str], ips: list[str]) -> list[str]:
        """Names the box answers at that this certificate does NOT assert."""
        have_dns = {d.lower() for d in self.dns_names}
        have_ip = set(self.ip_addresses)
        missing = [d for d in dns if d.lower() not in have_dns]
        missing += [i for i in ips if i not in have_ip]
        return missing


def inspect_certificate(path: str, now: Any = None) -> CertificateFacts:
    """Read a PEM certificate and report what it actually asserts.

    Presence is not usability -- the same lesson ``_fernet_key_defects`` learned in
    ``check_edge_readiness``: a file at the configured path satisfied every
    ``if os.path.exists(...)`` in the codebase while being an expired certificate for
    a hostname the box no longer answers at. Nothing ever tried to parse one.
    """
    if not path or not os.path.exists(path):
        return CertificateFacts(path=path, exists=False)
    try:
        with open(path, "rb") as handle:
            raw = handle.read()
    except OSError as exc:
        return CertificateFacts(path=path, exists=True, error=f"unreadable: {exc}")
    try:
        # Local import: cryptography is a hard dependency of the app, but this module
        # is also imported by settings-adjacent code where an ImportError would take
        # the whole box down rather than produce a finding.
        from cryptography import x509
        from cryptography.x509.oid import ExtensionOID
    except Exception as exc:  # noqa: BLE001 - any import failure is a finding, not a crash
        return CertificateFacts(
            path=path, exists=True, error=f"cannot parse (cryptography unavailable): {exc}"
        )
    try:
        cert = x509.load_pem_x509_certificate(raw)
    except Exception as exc:  # noqa: BLE001 - malformed PEM is a finding
        return CertificateFacts(path=path, exists=True, error=f"not a PEM certificate: {exc}")

    dns_names: tuple[str, ...] = ()
    ip_addresses: tuple[str, ...] = ()
    try:
        san = cert.extensions.get_extension_for_oid(ExtensionOID.SUBJECT_ALTERNATIVE_NAME)
        dns_names = tuple(san.value.get_values_for_type(x509.DNSName))
        ip_addresses = tuple(str(i) for i in san.value.get_values_for_type(x509.IPAddress))
    except Exception:  # noqa: BLE001 - a certificate with no SAN is legal and useless
        pass

    not_after = cert.not_valid_after_utc
    not_before = cert.not_valid_before_utc
    if now is None:
        from datetime import datetime, timezone

        now = datetime.now(timezone.utc)
    days = (not_after - now).days

    return CertificateFacts(
        path=path,
        exists=True,
        readable=True,
        subject=cert.subject.rfc4514_string(),
        issuer=cert.issuer.rfc4514_string(),
        self_signed=cert.subject == cert.issuer,
        dns_names=dns_names,
        ip_addresses=ip_addresses,
        not_before=not_before.isoformat(),
        not_after=not_after.isoformat(),
        days_remaining=days,
    )


def issue_self_signed(
    directory: str,
    dns_names: list[str],
    ip_addresses: list[str],
    days: int = DEFAULT_SELF_SIGNED_DAYS,
    common_name: str = "",
) -> dict[str, str]:
    """Mint a box-local CA and a leaf certificate for the names the box answers at.

    Two certificates, not one, and that is the whole point: a bare self-signed LEAF
    cannot be installed as a trust anchor on Android or in Chrome's own store, so a
    school that mints one is stuck clicking through a warning forever. A tiny local
    CA can be installed once per device, and the leaf beneath it can then be reissued
    (new IP, new hostname, expiry) WITHOUT redoing the trust install on every phone in
    the building. That is what makes self-signed survivable past week one.
    """
    from cryptography import x509
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import rsa
    from cryptography.x509.oid import ExtendedKeyUsageOID, NameOID
    from datetime import datetime, timedelta, timezone

    if not dns_names and not ip_addresses:
        raise ValueError(
            "refusing to issue a certificate with no SAN entries: set "
            f"{ENV_HOSTNAMES} or ALLOWED_HOSTS to the names this box answers at"
        )

    os.makedirs(directory, exist_ok=True)
    now = datetime.now(timezone.utc)
    # Backdate slightly: a box whose clock is a few minutes fast would otherwise
    # reject its own brand-new certificate as not-yet-valid. Offline boxes drift.
    valid_from = now - timedelta(minutes=5)
    leaf_cn = common_name or (dns_names[0] if dns_names else ip_addresses[0])

    ca_cert_path = os.path.join(directory, "ca.crt")
    ca_key_path = os.path.join(directory, "ca.key")
    # REUSE the CA if this box already has one. Minting a fresh CA on every issue
    # would silently void the trust install on every phone, laptop and tablet in the
    # building -- which would make the whole two-certificate design pointless. The CA
    # key therefore has to persist, and it is the one file on the box that must never
    # leave it: anyone holding it can mint a certificate for any name and every
    # device that trusted this box would believe them.
    ca_key = None
    ca_cert = None
    if os.path.exists(ca_cert_path) and os.path.exists(ca_key_path):
        try:
            with open(ca_key_path, "rb") as handle:
                ca_key = serialization.load_pem_private_key(handle.read(), password=None)
            with open(ca_cert_path, "rb") as handle:
                ca_cert = x509.load_pem_x509_certificate(handle.read())
            if ca_cert.not_valid_after_utc <= now:
                ca_key = ca_cert = None  # expired: a new one is unavoidable
        except Exception:  # noqa: BLE001 - unreadable CA means mint a fresh one
            ca_key = ca_cert = None

    reused_ca = ca_key is not None and ca_cert is not None
    if reused_ca:
        ca_name = ca_cert.subject
    else:
        ca_key = rsa.generate_private_key(public_exponent=65537, key_size=4096)
        ca_name = x509.Name(
            [
                x509.NameAttribute(NameOID.ORGANIZATION_NAME, "RunMyCampus Edge"),
                x509.NameAttribute(NameOID.COMMON_NAME, f"RunMyCampus Edge CA ({leaf_cn})"),
            ]
        )
        ca_cert = (
            x509.CertificateBuilder()
            .subject_name(ca_name)
            .issuer_name(ca_name)
            .public_key(ca_key.public_key())
            .serial_number(x509.random_serial_number())
            .not_valid_before(valid_from)
            # The CA outlives the leaf so a reissue does not force a re-install.
            .not_valid_after(now + timedelta(days=max(days * 4, 3650)))
            .add_extension(x509.BasicConstraints(ca=True, path_length=0), critical=True)
            .add_extension(
                x509.KeyUsage(
                    digital_signature=True,
                    content_commitment=False,
                    key_encipherment=False,
                    data_encipherment=False,
                    key_agreement=False,
                    key_cert_sign=True,
                    crl_sign=True,
                    encipher_only=False,
                    decipher_only=False,
                ),
                critical=True,
            )
            .sign(ca_key, hashes.SHA256())
        )

    leaf_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    san_entries: list[Any] = [x509.DNSName(d) for d in dns_names]
    san_entries += [x509.IPAddress(ipaddress.ip_address(i)) for i in ip_addresses]
    leaf_cert = (
        x509.CertificateBuilder()
        .subject_name(
            x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, leaf_cn[:64])])
        )
        .issuer_name(ca_name)
        .public_key(leaf_key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(valid_from)
        .not_valid_after(now + timedelta(days=days))
        .add_extension(x509.SubjectAlternativeName(san_entries), critical=False)
        .add_extension(x509.BasicConstraints(ca=False, path_length=None), critical=True)
        .add_extension(
            x509.ExtendedKeyUsage([ExtendedKeyUsageOID.SERVER_AUTH]),
            critical=False,
        )
        .sign(ca_key, hashes.SHA256())
    )

    cert_path = os.path.join(directory, "tls.crt")
    key_path = os.path.join(directory, "tls.key")
    ca_path = ca_cert_path
    # Chain order: leaf first, then issuer. A server that presents only the leaf
    # makes even a device that HAS installed the CA do extra work, and some clients
    # simply fail.
    with open(cert_path, "wb") as handle:
        handle.write(leaf_cert.public_bytes(serialization.Encoding.PEM))
        handle.write(ca_cert.public_bytes(serialization.Encoding.PEM))
    with open(key_path, "wb") as handle:
        handle.write(
            leaf_key.private_bytes(
                encoding=serialization.Encoding.PEM,
                format=serialization.PrivateFormat.TraditionalOpenSSL,
                encryption_algorithm=serialization.NoEncryption(),
            )
        )
    if not reused_ca:
        with open(ca_path, "wb") as handle:
            handle.write(ca_cert.public_bytes(serialization.Encoding.PEM))
        with open(ca_key_path, "wb") as handle:
            handle.write(
                ca_key.private_bytes(
                    encoding=serialization.Encoding.PEM,
                    format=serialization.PrivateFormat.TraditionalOpenSSL,
                    encryption_algorithm=serialization.NoEncryption(),
                )
            )
    for path in (key_path, ca_key_path):
        try:
            os.chmod(path, 0o600)
        except OSError:
            # Windows / bind-mounted volumes may not support it. Not fatal, but the
            # runbook says to check it, so do not pretend it succeeded.
            pass
    return {
        "cert": cert_path,
        "key": key_path,
        "ca": ca_path,
        "ca_key": ca_key_path,
        "common_name": leaf_cn,
        "reused_ca": reused_ca,
    }


def caddyfile(
    mode: str,
    dns_names: list[str],
    ip_addresses: list[str],
    upstream: str = "web:10000",
    cert_path: str = "",
    key_path: str = "",
    acme_email: str = "",
    acme_ca: str = "",
) -> str:
    """Render the Caddy site block for a mode.

    One file, one directive difference between the three HTTPS modes -- which is
    precisely why the terminator is Caddy and not nginx here. Transitioning a school
    from self-signed to a real CA is a one-line change plus a container restart, with
    no certificate paths, no ``ssl_protocols`` block and no renewal cron to forget.
    """
    mode = normalize_mode(mode)
    if mode == MODE_OFF:
        return (
            "# RMC_EDGE_TLS_MODE=off -- no TLS terminator.\n"
            "# The box is served directly on http://<host>:${WEB_PORT}. WebCrypto\n"
            "# (offline PIN / local mode) cannot work at that origin; see\n"
            "# docs/EDGE_TLS_RUNBOOK.md before enabling it for a school.\n"
        )
    hosts = list(dns_names) + list(ip_addresses)
    if not hosts:
        raise ValueError("no hostnames or IPs to serve; set " + ENV_HOSTNAMES)
    site = ", ".join(hosts)
    if mode == MODE_SELF_SIGNED:
        # `tls internal` = Caddy's own local CA, which it also writes out so the
        # school can install it. We accept a pre-minted pair too (manage.py edge_tls
        # --issue-selfsigned), because a school that wants ONE CA across several
        # appliances needs to control the key.
        if cert_path and key_path:
            tls_line = f"tls {cert_path} {key_path}"
        else:
            tls_line = "tls internal"
    elif mode == MODE_PROVIDED:
        if not cert_path or not key_path:
            raise ValueError(
                f"mode={MODE_PROVIDED} needs {ENV_CERT} and {ENV_KEY} "
                "(the files your CA issued)"
            )
        tls_line = f"tls {cert_path} {key_path}"
    else:  # MODE_ACME
        if not acme_email:
            raise ValueError(f"mode={MODE_ACME} needs {ENV_ACME_EMAIL} for CA registration")
        tls_line = f"tls {acme_email}"
        if acme_ca:
            tls_line += f" {{\n\t\tca {acme_ca}\n\t}}"
    return (
        f"{site} {{\n"
        f"\t{tls_line}\n"
        f"\tencode zstd gzip\n"
        f"\treverse_proxy {upstream} {{\n"
        # Django reads SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https").
        # Without this header every request looks like plain HTTP to Django and
        # SECURE_SSL_REDIRECT sends the browser round a redirect loop.
        f"\t\theader_up X-Forwarded-Proto {{scheme}}\n"
        f"\t\theader_up X-Forwarded-Host {{host}}\n"
        f"\t}}\n"
        f"}}\n"
    )


def transition_plan(from_mode: str, to_mode: str) -> list[str]:
    """The ordered steps to move a live box between modes, in both directions.

    Written as data rather than prose in the runbook so ``manage.py edge_tls
    --plan-to <mode>`` can print the steps for the box's ACTUAL current mode, and so
    the ordering constraints below can never drift out of sync with the code:

    * CSRF_TRUSTED_ORIGINS carries a SCHEME. Flip it before the redirect, or the
      first POST after the switch fails a referer check and login appears broken.
    * Going back DOWN from HTTPS, clear HSTS first and let it expire, or browsers
      that saw the header keep refusing plain HTTP with no way in.
    """
    from_mode = normalize_mode(from_mode)
    to_mode = normalize_mode(to_mode)
    if from_mode == to_mode:
        return [f"Already on {to_mode}; nothing to do."]

    steps: list[str] = []
    going_up = from_mode == MODE_OFF and to_mode in HTTPS_MODES
    going_down = from_mode in HTTPS_MODES and to_mode == MODE_OFF

    if to_mode == MODE_SELF_SIGNED:
        steps.append(
            "Mint the box CA + leaf:  docker compose ... exec web "
            "python manage.py edge_tls --issue-selfsigned"
        )
        steps.append(
            "Distribute var/edge-tls/ca.crt to every device that will use the box "
            "(Windows: Local Machine > Trusted Root; Android: Settings > Security > "
            "Install a certificate > CA certificate; iOS: install profile, then "
            "General > About > Certificate Trust Settings > enable)."
        )
    elif to_mode == MODE_PROVIDED:
        steps.append(
            f"Copy the CA-issued fullchain and key onto the box and point {ENV_CERT} "
            f"/ {ENV_KEY} at them (leaf first, then intermediates, in one PEM)."
        )
        steps.append(
            "Confirm the chain covers every name the box answers at:  "
            "python manage.py edge_tls"
        )
    elif to_mode == MODE_ACME:
        steps.append(
            "Publish a PUBLIC DNS A/AAAA record for the box and open 80/443 inbound "
            "(HTTP-01), or configure a DNS provider plugin for DNS-01."
        )
        steps.append(f"Set {ENV_ACME_EMAIL} to a mailbox the school reads.")

    if going_down:
        steps.append(
            "FIRST set SECURE_HSTS_SECONDS=0 and redeploy, then wait out any max-age "
            "already issued. A browser that cached HSTS refuses plain HTTP for the "
            "full year regardless of what the server now sends."
        )

    steps.append(f"Set {ENV_MODE}={to_mode} in deploy/selfhost/.env")
    steps.append(
        "Update CSRF_TRUSTED_ORIGINS to the "
        + ("https://" if to_mode in HTTPS_MODES else "http://")
        + " scheme for every host the box answers at (the scheme is part of the value)."
    )
    steps.append(
        "Remove any hand-set SECURE_SSL_REDIRECT / SESSION_COOKIE_SECURE / "
        "CSRF_COOKIE_SECURE / SECURE_HSTS_SECONDS from .env so they follow the mode."
    )
    steps.append(
        "docker compose -f deploy/selfhost/docker-compose.yml "
        + ("--profile tls " if to_mode in HTTPS_MODES else "")
        + "up -d"
    )
    steps.append("python manage.py check_edge_readiness --strict")
    if going_up:
        steps.append(
            "Re-enrol offline PIN on each device: local mode could never seal on the "
            "old plain-HTTP origin, and a secure context is a NEW origin to the "
            "browser -- nothing carries over."
        )
    return steps
