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

``off``         Plain HTTP. Honest, and what Gilead runs today. Named as a mode rather
                than left as an absence, so readiness can SAY what is off and what
                that costs instead of silently omitting the subject.

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
# Read from the environment rather than a --passphrase flag on purpose: a command
# line is visible in `ps`, in shell history and in docker's own event log, and this
# passphrase protects the CA private key.
ENV_CA_PASSPHRASE = "RMC_EDGE_TLS_CA_PASSPHRASE"

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


# ---------------------------------------------------------------------------
# RELOCATION
# ---------------------------------------------------------------------------
# A box is a physical object. It moves: to a new room, a new campus, a new
# country, or onto new hardware after a failure. Exactly one thing it carries
# cannot be regenerated -- the box CA's private key. Everything else (the leaf
# certificate, the Caddyfile, ALLOWED_HOSTS, the origins) is derived and can be
# rebuilt in a minute.
#
# That asymmetry is the whole design. Preserve the CA and a relocation is a
# five-minute reissue that no device notices. Lose it and every phone, laptop
# and tablet that trusted this box must be physically revisited -- which, for a
# school that has just moved country, is the difference between an afternoon and
# a term.
#
# The functions below exist to make the recoverable path the easy one.


HOST_PUBLIC_DNS = "public_dns"
HOST_PRIVATE_DNS = "private_dns"
HOST_PUBLIC_IP = "public_ip"
HOST_PRIVATE_IP = "private_ip"
HOST_LOOPBACK = "loopback"

#: DNS suffixes that no public certificate authority can ever issue for, because
#: nobody can demonstrate ownership of them: they are reserved for local use, and
#: the same name resolves to a different machine in every building on earth.
#: RFC 6762 (.local), RFC 8375 (.home.arpa), RFC 2606 (.test/.example/.invalid/
#: .localhost) and the ICANN permanently-reserved high-risk strings.
PRIVATE_DNS_SUFFIXES: tuple[str, ...] = (
    ".local",
    ".lan",
    ".internal",
    ".intranet",
    ".private",
    ".home",
    ".home.arpa",
    ".corp",
    ".mail",
    ".localdomain",
    ".test",
    ".example",
    ".invalid",
    ".localhost",
)

#: What changed about the box's situation. Used to build a relocation plan --
#: the steps genuinely differ, and a plan that lists every step for every move is
#: a plan people stop reading.
CHANGE_ADDRESS = "address"      # new IP and/or new hostname, same building
CHANGE_SITE = "site"            # new building or campus, same country
CHANGE_COUNTRY = "country"      # new jurisdiction
CHANGE_HARDWARE = "hardware"    # rebuilt / re-imaged / replaced appliance

RELOCATION_CHANGES: tuple[str, ...] = (
    CHANGE_ADDRESS,
    CHANGE_SITE,
    CHANGE_COUNTRY,
    CHANGE_HARDWARE,
)

#: Filename of the portable CA bundle. PKCS#12 because it is the one container
#: every platform's import tooling already understands, and because it is
#: encrypted by construction -- this file holds the CA PRIVATE KEY.
CA_BUNDLE_FILENAME = "box-ca-bundle.p12"


def classify_host(name: str) -> str:
    """What kind of address is this, for the purpose of getting a certificate?

    The answer decides which TLS modes are even possible. A public CA can issue
    for ``sms.gilead-tech.org``; it can never issue for ``gilead.school.lan`` or
    ``10.10.20.137``, no matter how the school fills in the form.
    """
    candidate = str(name or "").strip().strip(".")
    if not candidate:
        return HOST_PRIVATE_DNS
    if candidate.count(":") == 1 and not candidate.startswith("["):
        candidate = candidate.split(":", 1)[0]
    try:
        ip = ipaddress.ip_address(candidate)
    except ValueError:
        lowered = candidate.lower()
        if "." not in lowered:
            # A single-label name ("boxroom", "server") is by definition local.
            return HOST_PRIVATE_DNS
        for suffix in PRIVATE_DNS_SUFFIXES:
            if lowered == suffix.lstrip(".") or lowered.endswith(suffix):
                return HOST_PRIVATE_DNS
        return HOST_PUBLIC_DNS
    if ip.is_loopback:
        return HOST_LOOPBACK
    # is_global is the honest test: it excludes RFC1918, CGNAT (100.64/10),
    # link-local, unique-local IPv6 and every other special-use range in one
    # place, and it tracks the IANA registries as Python updates.
    return HOST_PUBLIC_IP if ip.is_global else HOST_PRIVATE_IP


def publicly_issuable(name: str) -> bool:
    """Could a public CA ever issue a certificate asserting this name?"""
    return classify_host(name) in (HOST_PUBLIC_DNS, HOST_PUBLIC_IP)


def mode_feasibility(
    mode: str,
    dns: list[str] | tuple[str, ...],
    ips: list[str] | tuple[str, ...],
) -> list[tuple[str, str]]:
    """Is this mode actually achievable for these addresses?

    Returns ``(severity, message)`` pairs where severity is ``"fail"`` or
    ``"warn"``. Empty means the combination is achievable.

    This exists because the failure it prevents is invisible. A school that picks
    "use a certificate authority" for a box reachable only at ``10.10.20.137``
    has chosen something no CA on earth can deliver, and the symptom is not an
    error message -- it is a terminator that retries an ACME order forever while
    the box serves nothing.
    """
    mode = normalize_mode(mode)
    names = [str(d) for d in dns] + [str(i) for i in ips]
    findings: list[tuple[str, str]] = []

    if mode == MODE_ACME:
        if not names:
            findings.append((
                "fail",
                "acme needs at least one address to request a certificate for, and none "
                "are configured. Set RMC_EDGE_TLS_HOSTNAMES or ALLOWED_HOSTS.",
            ))
            return findings

        unissuable = [n for n in names if not publicly_issuable(n)]
        if unissuable:
            # The subtle part: an ACME order is all-or-nothing. One private name
            # in the SAN list fails the WHOLE order, so the box gets no
            # certificate at all -- not a partial one covering the public names.
            findings.append((
                "fail",
                "acme cannot be issued for "
                + ", ".join(sorted(unissuable))
                + ". A public CA cannot validate ownership of a private address, and an "
                "ACME order is all-or-nothing: one such name means the box gets NO "
                "certificate, not a partial one. Either remove these names from "
                "RMC_EDGE_TLS_HOSTNAMES and reach the box only by its public name, or "
                "choose selfsigned/provided instead.",
            ))
        public_names = [n for n in names if publicly_issuable(n)]
        if public_names and not unissuable:
            findings.append((
                "warn",
                "acme validates over the public internet: "
                + ", ".join(sorted(public_names))
                + " must resolve to THIS box and reach it on port 80 (HTTP-01) at renewal "
                "time, not merely at first issue. A box that moves without its DNS record "
                "moving renews nothing and fails closed when the certificate expires.",
            ))
        return findings

    if mode == MODE_PROVIDED:
        private = [n for n in names if not publicly_issuable(n)]
        if private:
            findings.append((
                "warn",
                "The certificate files must come from a CA that will issue for "
                + ", ".join(sorted(private))
                + ". No PUBLIC CA will; this needs your organisation's own internal CA, "
                "whose root must then be installed on every device exactly like the "
                "selfsigned path. If there is no internal CA, selfsigned is the same "
                "thing with less paperwork.",
            ))
        return findings

    if mode == MODE_SELF_SIGNED:
        if not names:
            findings.append((
                "fail",
                "Nothing to put in the certificate: no RMC_EDGE_TLS_HOSTNAMES and no "
                "usable ALLOWED_HOSTS entries.",
            ))
        return findings

    return findings


def clock_findings(
    facts: "CertificateFacts",
    ca_facts: "CertificateFacts | None" = None,
    now: Any = None,
) -> list[tuple[str, str]]:
    """Is the box's clock consistent with the certificate it is serving?

    A relocated appliance is the classic victim here. Ship a box across a border,
    let the RTC battery die in transit, and it powers on believing it is years in
    the past. Every certificate it holds is then "not yet valid", TLS fails
    completely, and nothing in the browser error mentions the clock. Meanwhile
    the sync rail's cursors and every attendance timestamp are equally wrong.

    We can detect this WITHOUT a network: the box's own CA certificate records a
    moment the box demonstrably existed. Any system time before that is
    impossible, so it is the clock that is wrong, not the certificate.
    """
    from datetime import datetime, timezone

    current = now or datetime.now(timezone.utc)
    findings: list[tuple[str, str]] = []

    def _parse(value: str):
        if not value:
            return None
        try:
            return datetime.fromisoformat(value)
        except ValueError:
            return None

    floor = _parse(ca_facts.not_before) if (ca_facts and ca_facts.exists) else None
    if floor is not None and current < floor:
        findings.append((
            "fail",
            f"The system clock reads {current.isoformat()}, which is BEFORE this box's own "
            f"CA was created ({floor.isoformat()}). The clock is wrong, not the "
            "certificate. Every TLS handshake will fail as 'not yet valid', and any "
            "timestamp the box writes -- attendance, sync cursors, audit rows -- is wrong "
            "too. Fix the clock (NTP, or the hardware RTC battery) BEFORE anything else; "
            "reissuing certificates against a bad clock only bakes the error in.",
        ))
        return findings

    not_before = _parse(facts.not_before)
    if not_before is not None and current < not_before:
        findings.append((
            "fail",
            f"The certificate is not valid until {not_before.isoformat()} but the box "
            f"believes it is {current.isoformat()}. Browsers will refuse it outright. "
            "Either the clock is behind or the certificate was minted on a machine whose "
            "clock is ahead.",
        ))
    return findings


def export_ca_bundle(
    passphrase: bytes,
    directory: str | None = None,
    environ: dict[str, str] | None = None,
    friendly_name: bytes = b"RunMyCampus Edge CA",
) -> bytes:
    """Serialise the box CA (certificate + private key) as encrypted PKCS#12.

    This is the ONLY artefact on the box that cannot be regenerated. Without it a
    rebuilt or replaced appliance mints a NEW CA, and every device that trusted
    the old one must be physically revisited.

    Encryption is not optional and there is no default passphrase: this file
    grants the power to impersonate any name to every device that trusts this
    box. Treat the exported file exactly as you would treat the box itself.
    """
    if not passphrase:
        raise ValueError(
            "A passphrase is required. This bundle contains the CA private key; "
            "whoever holds it unencrypted can impersonate any site to every device "
            "that trusts this box."
        )
    from cryptography import x509
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.serialization import pkcs12

    env = os.environ if environ is None else environ
    base = directory or env.get(ENV_DIR) or DEFAULT_DIR
    ca_cert_path = os.path.join(base, "ca.crt")
    ca_key_path = os.path.join(base, "ca.key")

    if not os.path.exists(ca_cert_path) or not os.path.exists(ca_key_path):
        raise FileNotFoundError(
            f"No box CA at {base} (need both ca.crt and ca.key). Nothing to export -- "
            "run `edge_tls --issue-selfsigned` first, or this box does not use a box CA."
        )

    with open(ca_cert_path, "rb") as handle:
        cert = x509.load_pem_x509_certificate(handle.read())
    with open(ca_key_path, "rb") as handle:
        key = serialization.load_pem_private_key(handle.read(), password=None)

    # AES-256 + SHA-256, not the library default. The default container uses
    # legacy PKCS#12 algorithms that OpenSSL 3 refuses to read without -legacy,
    # so a school could not inspect or re-wrap its own backup with standard
    # tooling. Round-tripping through this module would work either way; being
    # readable by anything else is what makes it a real backup.
    try:
        encryption = (
            serialization.PrivateFormat.PKCS12.encryption_builder()
            .key_cert_algorithm(pkcs12.PBES.PBESv2SHA256AndAES256CBC)
            .hmac_hash(hashes.SHA256())
            .build(passphrase)
        )
    except (AttributeError, ValueError, NotImplementedError):
        # Older cryptography has no builder. Still encrypted, still restorable by
        # this command -- just a legacy container.
        encryption = serialization.BestAvailableEncryption(passphrase)

    return pkcs12.serialize_key_and_certificates(
        name=friendly_name,
        key=key,
        cert=cert,
        cas=None,
        encryption_algorithm=encryption,
    )


def import_ca_bundle(
    data: bytes,
    passphrase: bytes,
    directory: str | None = None,
    environ: dict[str, str] | None = None,
    force: bool = False,
) -> dict[str, Any]:
    """Restore a previously exported box CA onto this box.

    Run this BEFORE issuing a leaf on rebuilt hardware. Restore first and the
    reissued leaf chains to the CA the devices already trust, so the move is
    invisible to them. Issue first and you have already minted a competing CA.
    """
    from cryptography import x509
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.serialization import pkcs12

    env = os.environ if environ is None else environ
    base = directory or env.get(ENV_DIR) or DEFAULT_DIR
    ca_cert_path = os.path.join(base, "ca.crt")
    ca_key_path = os.path.join(base, "ca.key")

    key, cert, _extra = pkcs12.load_key_and_certificates(data, passphrase)
    if key is None or cert is None:
        raise ValueError(
            "The bundle does not contain both a certificate and a private key. "
            "Either the passphrase is wrong or this is not a box CA bundle."
        )

    basic = cert.extensions.get_extension_for_class(x509.BasicConstraints).value
    if not basic.ca:
        raise ValueError(
            "The bundle's certificate is not a CA. You have probably exported or been "
            "given a LEAF certificate; restoring it would not re-establish device trust."
        )

    replaced = os.path.exists(ca_cert_path)
    if replaced and not force:
        with open(ca_cert_path, "rb") as handle:
            existing = x509.load_pem_x509_certificate(handle.read())
        if existing.fingerprint(hashes.SHA256()) != cert.fingerprint(hashes.SHA256()):
            raise FileExistsError(
                f"A DIFFERENT box CA already exists at {ca_cert_path}. Overwriting it "
                "invalidates every device that trusts the current one. Pass force=True "
                "only if you are certain the incoming CA is the one the devices trust."
            )

    os.makedirs(base, exist_ok=True)
    with open(ca_cert_path, "wb") as handle:
        handle.write(cert.public_bytes(serialization.Encoding.PEM))
    with open(ca_key_path, "wb") as handle:
        handle.write(
            key.private_bytes(
                encoding=serialization.Encoding.PEM,
                # Match what issue_self_signed writes, so a restored CA and a
                # locally minted one are byte-comparable and reload identically.
                format=serialization.PrivateFormat.TraditionalOpenSSL,
                encryption_algorithm=serialization.NoEncryption(),
            )
        )
    try:
        os.chmod(ca_key_path, 0o600)
    except OSError:
        # Windows / bind-mounted volumes may not support it. Not fatal, but the
        # runbook says to check it, so do not pretend it succeeded.
        pass
    return {
        "ca_cert": ca_cert_path,
        "ca_key": ca_key_path,
        "replaced": replaced,
        "subject": cert.subject.rfc4514_string(),
        "fingerprint": cert.fingerprint(hashes.SHA256()).hex(":").upper(),
    }


def relocation_plan(
    mode: str,
    changes: "set[str] | list[str] | tuple[str, ...]",
    hsts_seconds: int = 0,
) -> list[str]:
    """Ordered steps to move a box, for the mode it is on and what changed.

    Order is load-bearing in three places and each one is a mistake that cannot
    be undone from a keyboard:

    * The CA bundle is exported BEFORE the box is powered down. Afterwards, if
      the hardware does not survive the journey, it is gone.
    * On rebuilt hardware the CA is restored BEFORE a leaf is issued. Reversed,
      the box mints a competing CA and every device is stranded.
    * HSTS is stood down BEFORE a public-CA box moves to a LAN mode, and the
      max-age has to be waited out. Reversed, browsers refuse the box at that
      name for up to a year and will not let anyone click through.
    """
    mode = normalize_mode(mode)
    changed = {str(c) for c in (changes or ())}
    steps: list[str] = []

    steps.append(
        "BEFORE the box is switched off: export the box CA and store it somewhere "
        "that is not the box -- `edge_tls --export-ca --out <path>`. It is the only "
        "thing here that cannot be rebuilt."
        if mode == MODE_SELF_SIGNED
        else "BEFORE the box is switched off: back up deploy/selfhost/.env and the "
        "certificate directory. The .env records decisions nobody will remember."
    )

    if CHANGE_COUNTRY in changed:
        steps.append(
            "Confirm the move is permitted before it happens: this box holds student "
            "records, and moving them to another jurisdiction is a data-protection "
            "decision, not a logistics one. See docs/SOVEREIGNTY_PLEDGE.md."
        )

    if mode == MODE_ACME and hsts_seconds:
        steps.append(
            f"HSTS is currently {hsts_seconds}s. If the box is moving to selfsigned or "
            "provided at the SAME name, set SECURE_HSTS_SECONDS=0 and redeploy NOW, then "
            "wait out the max-age already handed to browsers. A browser that cached HSTS "
            "for this name refuses plain HTTP and refuses to let anyone bypass an "
            "untrusted certificate -- there is no way through it from the box side."
        )

    if mode == MODE_ACME and (CHANGE_COUNTRY in changed or CHANGE_SITE in changed):
        steps.append(
            "Renew the certificate BEFORE the move if it expires within ~45 days: the "
            "box cannot answer an HTTP-01 challenge while it is in a crate."
        )
        steps.append(
            "Update the public DNS A/AAAA record to the box's new public address as part "
            "of the move, not after it. ACME renewal happens unattended ~30 days before "
            "expiry; if DNS still points at the old site it fails silently and the first "
            "symptom is a dead box weeks later. Consider DNS-01 for a box that moves, "
            "since it needs no inbound reachability at all."
        )

    if CHANGE_HARDWARE in changed:
        steps.append(
            "On the new hardware, restore the CA FIRST: `edge_tls --import-ca --in <path>`. "
            "Do this before issuing anything. If you issue first you mint a second CA and "
            "every device that trusted the old one must be visited in person."
            if mode == MODE_SELF_SIGNED
            else "On the new hardware, restore the certificate and key files to the "
            "certificate directory before starting the terminator."
        )

    if changed & {CHANGE_ADDRESS, CHANGE_SITE, CHANGE_COUNTRY}:
        steps.append(
            "Set the new address(es) in deploy/selfhost/.env: ALLOWED_HOSTS and "
            "RMC_EDGE_TLS_HOSTNAMES. Django rejects a host it was not told about, so a "
            "box at an unlisted new IP answers nothing at all -- which looks like a dead "
            "box rather than a configuration line."
        )
        if mode == MODE_SELF_SIGNED:
            steps.append(
                "Reissue the leaf for the new addresses: "
                "`edge_tls --issue-selfsigned --force`. The CA on disk is reused, so "
                "devices that installed it need NOTHING done to them."
            )
        elif mode == MODE_PROVIDED:
            steps.append(
                "Obtain replacement certificate files for the new addresses from whoever "
                "issues them. A purchased certificate names specific hosts; a new address "
                "is not covered by the old one, and there is no local way to add it."
            )

    if mode in FILE_BACKED_MODES:
        steps.append(
            "Re-render the terminator config FROM the new certificate: "
            "`edge_tls --print-caddyfile > deploy/selfhost/Caddyfile.edge`. Run it after "
            "the certificate exists, never before -- with no certificate on disk it emits "
            "`tls internal`, which serves a different CA than the one your devices trust."
        )

    if mode in HTTPS_MODES and (changed & {CHANGE_ADDRESS, CHANGE_SITE, CHANGE_COUNTRY}):
        steps.append(
            "Update CSRF_TRUSTED_ORIGINS to the new https:// origins. The scheme and the "
            "host are both part of the value; a stale entry produces a login that submits, "
            "returns to the login page, and reports nothing."
        )

    if CHANGE_COUNTRY in changed:
        steps.append(
            "Set TIME_ZONE for the new country and restart. Attendance, timetables, "
            "schedule due-ness and sync cursors are all evaluated locally on this box; "
            "left on the old zone they are silently wrong by the offset."
        )
        steps.append(
            "Verify the hardware clock survived the journey and NTP can reach a server "
            "reachable from the new network. A box whose RTC died in transit rejects its "
            "own certificate as 'not yet valid'."
        )

    steps.append(
        "Bring the stack up and verify: "
        "`docker compose -f deploy/selfhost/docker-compose.yml --profile tls up -d` then "
        "`edge_tls` and `check_edge_readiness --strict`."
    )

    if CHANGE_HARDWARE in changed and mode == MODE_SELF_SIGNED:
        steps.append(
            "Confirm the CA fingerprint matches what the devices already trust "
            "(`edge_tls --json` reports it). If it does not, the restore did not take and "
            "you are about to discover it one device at a time."
        )

    # Only the modes that use a PRIVATE CA leave trust behind on devices. An acme
    # box's devices trust a public CA that has nothing to do with this appliance.
    if mode in FILE_BACKED_MODES and (changed & {CHANGE_SITE, CHANGE_COUNTRY}):
        steps.append(
            "Devices left behind at the old site still trust this box's CA. If the old "
            "site keeps running a DIFFERENT box, remove the old CA from those devices -- "
            "otherwise they extend trust to an appliance that is no longer yours."
        )

    return steps
