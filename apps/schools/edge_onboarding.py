"""Turn a school's answers into a deployable edge plan.

The edge onboarding runbook asks a school to make about six decisions and then
translates them into files. Doing that by hand is where the mistakes live: a
missing IP in the certificate, an origin left on ``http://``, a Caddyfile
rendered before the certificate existed, an ACME mode chosen for a box that no
public CA can ever reach.

This module is the translation, as one pure function. ``build_edge_plan`` takes
the answers and returns everything the box needs -- the ``.env`` lines, the
terminator config, an ordered runbook, and the feasibility problems with the
combination the school actually chose. It touches no database and no filesystem,
so it is cheap to test and safe to call from a wizard step, a management command
or a template.

``record_edge_plan`` is the thin domain hook the wizard writer delegates to.

Related: ``apps/schools/edge_tls.py`` owns the certificate policy this consumes;
``docs/EDGE_TLS_RUNBOOK.md`` is the prose version of what this emits.
"""
from __future__ import annotations

import logging
from typing import Any

from apps.schools import edge_tls

logger = logging.getLogger(__name__)

#: How likely is this box to move? The answer changes how loudly the plan talks
#: about CA escrow -- which is the one irreversible mistake available here.
MOVE_NEVER = "static"
MOVE_WITHIN_SITE = "within_site"
MOVE_BETWEEN_SITES = "between_sites"
MOVE_BETWEEN_COUNTRIES = "between_countries"

MOBILITY_CHOICES: tuple[str, ...] = (
    MOVE_NEVER,
    MOVE_WITHIN_SITE,
    MOVE_BETWEEN_SITES,
    MOVE_BETWEEN_COUNTRIES,
)

#: Mobility -> the relocation changes that class of move implies.
_MOBILITY_TO_CHANGES: dict[str, set[str]] = {
    MOVE_NEVER: set(),
    MOVE_WITHIN_SITE: {edge_tls.CHANGE_ADDRESS},
    MOVE_BETWEEN_SITES: {edge_tls.CHANGE_ADDRESS, edge_tls.CHANGE_SITE},
    MOVE_BETWEEN_COUNTRIES: {
        edge_tls.CHANGE_ADDRESS,
        edge_tls.CHANGE_SITE,
        edge_tls.CHANGE_COUNTRY,
    },
}

#: Re-exported, not redeclared: the port and the enrolment path belong to edge_tls,
#: which is what the box itself reads at runtime. Two copies of a port number is how
#: a runbook ends up naming an address nothing answers on.
DEFAULT_WEB_PORT = edge_tls.DEFAULT_WEB_PORT


def split_addresses(raw: Any) -> tuple[list[str], list[str]]:
    """Parse a free-text list of addresses into (dns_names, ip_addresses).

    Reuses the certificate layer's own splitter so that what the wizard shows a
    school and what the certificate ends up asserting cannot drift apart.
    """
    text = ", ".join(raw) if isinstance(raw, (list, tuple)) else str(raw or "")
    return edge_tls.san_candidates(environ={edge_tls.ENV_HOSTNAMES: text})


def build_edge_plan(answers: dict[str, Any]) -> dict[str, Any]:
    """The whole turnkey bundle, derived from the school's answers.

    Answers understood (all optional; absent means "not decided yet", never a
    guess -- a plan that invents an address is worse than one that says it is
    missing):

    ``site_name``      free text, used only for labelling
    ``addresses``      comma/space list of hostnames and IPs people will type
    ``tls_mode``       off | selfsigned | provided | acme
    ``mobility``       one of MOBILITY_CHOICES
    ``acme_email``     contact mailbox, acme only
    ``web_port``       the app's own port, default 10000
    """
    site_name = str(answers.get("site_name") or "").strip()
    dns_names, ip_addresses = split_addresses(answers.get("addresses"))

    raw_mode = answers.get("tls_mode")
    mode_error = ""
    try:
        mode = edge_tls.normalize_mode(raw_mode) if raw_mode else edge_tls.MODE_OFF
    except edge_tls.UnknownTlsMode as exc:
        mode, mode_error = edge_tls.MODE_OFF, str(exc)

    mobility = str(answers.get("mobility") or MOVE_NEVER).strip()
    if mobility not in MOBILITY_CHOICES:
        mobility = MOVE_NEVER

    web_port = str(answers.get("web_port") or DEFAULT_WEB_PORT).strip()
    acme_email = str(answers.get("acme_email") or "").strip()

    blocking = list(edge_tls.mode_feasibility(mode, dns_names, ip_addresses))
    if mode_error:
        blocking.insert(0, ("fail", mode_error))
    if mode == edge_tls.MODE_ACME and not acme_email:
        blocking.append((
            "fail",
            "acme needs a contact mailbox the school actually reads: expiry and "
            "revocation notices go there, and they are the only warning before a "
            "certificate lapses.",
        ))

    scheme = "https" if mode in edge_tls.HTTPS_MODES else "http"
    port_suffix = "" if mode in edge_tls.HTTPS_MODES else f":{web_port}"
    # host_header_form, not the bare address: an IPv6 literal has to be bracketed in
    # a URL and in ALLOWED_HOSTS, and bare in the certificate. Getting that backwards
    # produces a 400 on every request with nothing in it that names the address.
    origins = [
        f"{scheme}://{edge_tls.host_header_form(name)}{port_suffix}"
        for name in (*dns_names, *ip_addresses)
    ]

    env_lines = _env_lines(
        mode=mode,
        dns_names=dns_names,
        ip_addresses=ip_addresses,
        origins=origins,
        acme_email=acme_email,
        web_port=web_port,
        mobility=mobility,
    )

    try:
        terminator = edge_tls.caddyfile(
            mode,
            dns_names,
            ip_addresses,
            upstream=f"web:{web_port}",
            cert_path=(
                f"{edge_tls.DEFAULT_DIR}/tls.crt"
                if mode in edge_tls.FILE_BACKED_MODES
                else ""
            ),
            key_path=(
                f"{edge_tls.DEFAULT_DIR}/tls.key"
                if mode in edge_tls.FILE_BACKED_MODES
                else ""
            ),
            acme_email=acme_email,
            # A school that has just said its box moves must not be handed a
            # terminator config with this morning's address pinned into the site
            # matcher -- the certificate would heal on the next start and the box
            # would still answer nothing at the new address.
            address_may_change=mobility != MOVE_NEVER,
        )
    except ValueError as exc:
        terminator = ""
        blocking.append(("fail", str(exc)))

    return {
        "site_name": site_name,
        "mode": mode,
        "mode_summary": edge_tls.MODE_SUMMARY.get(mode, ""),
        "dns_names": dns_names,
        "ip_addresses": ip_addresses,
        "origins": origins,
        "mobility": mobility,
        "blocking": [m for severity, m in blocking if severity == "fail"],
        "advisory": [m for severity, m in blocking if severity != "fail"],
        "ready": not any(severity == "fail" for severity, _ in blocking),
        "security_flags": edge_tls.derived_security_flags(mode),
        "env_lines": env_lines,
        "caddyfile": terminator,
        "steps": _runbook(mode, dns_names, ip_addresses, mobility, web_port),
        "relocation_steps": edge_tls.relocation_plan(
            mode,
            _MOBILITY_TO_CHANGES.get(mobility, set()) | {edge_tls.CHANGE_HARDWARE},
            hsts_seconds=int(
                edge_tls.derived_security_flags(mode).get("SECURE_HSTS_SECONDS", 0) or 0
            ),
        ),
    }


def _env_lines(
    *,
    mode: str,
    dns_names: list[str],
    ip_addresses: list[str],
    origins: list[str],
    acme_email: str,
    web_port: str,
    mobility: str = MOVE_NEVER,
) -> list[str]:
    """The exact lines to put in ``deploy/selfhost/.env``.

    Deliberately does NOT emit SECURE_SSL_REDIRECT / SESSION_COOKIE_SECURE /
    CSRF_COOKIE_SECURE / SECURE_HSTS_SECONDS: those follow from the mode, and an
    explicit value in .env silently overrides the mode later. Writing them here
    would re-create the exact trap this whole design removes.
    """
    every = [*dns_names, *ip_addresses]
    lines = [
        f"RMC_EDGE_TLS_MODE={mode}",
    ]
    if every:
        # ALLOWED_HOSTS is matched against the Host header, so an IPv6 entry is
        # bracketed here; RMC_EDGE_TLS_HOSTNAMES feeds a certificate, which needs the
        # bare address. Same addresses, two spellings, and each is wrong in the
        # other's place.
        lines.append(
            "ALLOWED_HOSTS="
            + ",".join(
                ["localhost", "127.0.0.1", *[edge_tls.host_header_form(h) for h in every]]
            )
        )
        lines.append("RMC_EDGE_TLS_HOSTNAMES=" + ",".join(every))
    if mobility != MOVE_NEVER:
        # This is not one of the derived security flags -- it is the school's own
        # answer about whether the box holds still, and without it the box refuses
        # requests at the address it just healed onto.
        lines.append(f"{edge_tls.ENV_TRUST_LOCAL}=1")
    if origins:
        lines.append("CSRF_TRUSTED_ORIGINS=" + ",".join(origins))
    if mode == edge_tls.MODE_ACME and acme_email:
        lines.append(f"{edge_tls.ENV_ACME_EMAIL}={acme_email}")
    if web_port and web_port != DEFAULT_WEB_PORT:
        lines.append(f"WEB_PORT={web_port}")
    return lines


def _runbook(
    mode: str,
    dns_names: list[str],
    ip_addresses: list[str],
    mobility: str,
    web_port: str = DEFAULT_WEB_PORT,
) -> list[str]:
    """The ordered procedure for THIS school, not a generic one."""
    compose = "docker compose -f deploy/selfhost/docker-compose.yml"
    first = (dns_names or ip_addresses or ["<box-address>"])[0]
    steps: list[str] = [
        f"Confirm the box is healthy before changing anything: `{compose} ps` and "
        f"`curl -s http://127.0.0.1:10000/health/`. Adding TLS to an unwell box gives "
        "you two problems to debug at once.",
    ]

    # Before .env, not after it. The addresses ARE the .env line, and the two
    # conditions that make a '.local' name the wrong choice have to be checked while
    # the name can still be changed for free -- afterwards it means reissuing the
    # certificate and revisiting whatever has already been set up.
    if mobility != MOVE_NEVER:
        steps.append(
            "Decide the NAME first, because the next step writes it down. This box is "
            "expected to move, and a name survives an address change where an IP "
            "cannot -- an mDNS '.local' name needs no DNS server and follows the box "
            "anywhere on the segment. Two local conditions break '.local' and neither "
            "says so when it fails: a Windows domain that is itself named .local (the "
            "domain controller answers instead of the box), and access points that "
            "filter multicast or isolate clients (wired devices resolve it, wireless "
            "ones do not). Where either holds, use a name in the school's own DNS. "
            "Either way add a DHCP reservation for the box's MAC so the address stops "
            "moving in the first place."
        )

    steps.append("Put the lines from this plan into deploy/selfhost/.env.")

    if mode == edge_tls.MODE_SELF_SIGNED:
        steps.append(
            f"Mint the box CA and leaf: `{compose} exec web python manage.py edge_tls "
            "--issue-selfsigned`."
        )
        steps.append(
            "Export the CA and move the copy OFF the box: "
            f"`{compose} exec -e RMC_EDGE_TLS_CA_PASSPHRASE web python manage.py "
            "edge_tls --export-ca /tmp/box-ca-bundle.p12`, then "
            f"`{compose} cp web:/tmp/box-ca-bundle.p12 ./box-ca-bundle.p12`. Write it "
            "to /tmp, NOT the certificate directory: a backup sharing a volume with "
            "the key it protects survives none of the events a backup exists for. It "
            "is the only artefact here that cannot be regenerated."
        )
    elif mode == edge_tls.MODE_PROVIDED:
        steps.append(
            "Copy the certificate and key supplied by your CA into the certificate "
            f"directory ({edge_tls.DEFAULT_DIR}). The certificate file must be the FULL "
            "chain -- leaf first, then any intermediates -- or some devices will trust "
            "it and others will not, which is the hardest variant to diagnose."
        )
    elif mode == edge_tls.MODE_ACME:
        steps.append(
            "Confirm the public DNS record for "
            + ", ".join(dns_names or ["the box"])
            + " points at this box and that port 80 reaches it from the internet. "
            "Validation happens at renewal too, not only at first issue."
        )

    if mode in edge_tls.FILE_BACKED_MODES:
        steps.append(
            f"Render the terminator config FROM the certificate: `{compose} exec -T web "
            "python manage.py edge_tls --print-caddyfile > deploy/selfhost/Caddyfile.edge`, "
            "then check it does not say `tls internal`. Run this AFTER the certificate "
            "exists -- before, it emits a config that serves a different CA than the one "
            "your devices will trust."
            + (
                " Because this box moves, the site line will be `:443` rather than a "
                "list of addresses: a named site block is a host matcher, so pinning "
                "today's address there would leave the box answering nothing at the "
                "address it heals onto tomorrow."
                if mobility != MOVE_NEVER
                else ""
            )
        )

    if mode in edge_tls.HTTPS_MODES:
        steps.append(f"Start the terminator: `{compose} --profile tls up -d`.")
    else:
        steps.append(f"Bring the stack up: `{compose} up -d`.")

    steps.append(
        f"Verify before touching any device: `{compose} exec web python manage.py "
        "check_edge_readiness --strict`."
    )

    if mode == edge_tls.MODE_SELF_SIGNED:
        # A URL, not a file. Copying ca.crt off the box and walking it round the
        # building is thirty chances to hand somebody the .p12 by mistake -- and the
        # .p12 carries the CA private key. The box publishes the public half itself.
        # The path comes from edge_tls, not from a string spelled out here. This is
        # the fourth surface that prints this URL, and the wizard's copy is the one
        # most likely to be read weeks later, off a printout, by somebody who cannot
        # check it against a running box.
        enrol = (
            f"http://{first}:{web_port or DEFAULT_WEB_PORT}"
            f"{edge_tls.TRUST_ENROLMENT_PATH}"
        )
        steps.append(
            f"Send devices to {enrol} "
            "and install it on every device that will use the box. That page carries "
            "the fingerprint, a QR code so a phone need not type an address, and the "
            "per-platform step people skip (iOS needs a second screen under Certificate "
            "Trust Settings; Android needs the 'CA certificate' entry, not 'install "
            "from storage'). Install the CA, never the leaf: the leaf appears to work "
            "and then breaks at the first reissue. The page is plain HTTP on purpose "
            "-- a device reaches it BECAUSE it does not trust the box yet -- so have "
            f"someone compare the fingerprint shown there against `{compose} exec web "
            "python manage.py edge_tls` on the box console before accepting it."
        )

    if mode in edge_tls.HTTPS_MODES:
        steps.append(
            f"Move everyone to https://{first} and re-enrol offline PIN on each device. "
            "The browser treats the new origin as unrelated to the old one, so nothing "
            "carries over -- and offline mode could never have sealed on the old one."
        )
    else:
        steps.append(
            "Offline PIN / local mode cannot be enabled on ANY browser at this origin: "
            "plain HTTP is not a secure context, so the browser withholds the WebCrypto "
            "call the PIN vault needs. Choose a TLS mode when that matters."
        )

    if mobility != MOVE_NEVER:
        steps.append(
            "After any address change the box reissues its own certificate on the "
            f"next start, but the terminator only reads those files at config load: "
            f"`{compose} --profile tls restart edge-tls` to actually serve them. A "
            "whole-box reboot does this for free; restarting only the web container "
            "does not."
        )
    if mobility != MOVE_NEVER and mode == edge_tls.MODE_SELF_SIGNED:
        steps.append(
            "Keep the exported CA bundle and its passphrase somewhere that survives "
            "the box, and see the relocation steps in this plan before it travels."
        )
    return steps


def record_edge_plan(
    *,
    school: Any = None,
    answers: dict[str, Any] | None = None,
    actor_user_id: int | None = None,
) -> dict[str, Any]:
    """Domain hook for the wizard writer: build the plan and log the outcome.

    Intentionally does not create a model row. The plan is a pure function of the
    answers the wizard already persists, so storing a second copy would introduce
    a way for the two to disagree -- and the stale one always wins an argument
    with an operator who is standing at the box.
    """
    plan = build_edge_plan(answers or {})
    logger.info(
        "edge onboarding plan: school=%s mode=%s ready=%s blocking=%d",
        getattr(school, "pk", None),
        plan["mode"],
        plan["ready"],
        len(plan["blocking"]),
    )
    return plan
