#!/usr/bin/env python3
"""Verify the dual-plane theme layer is delivered by every authenticated shell.

WHY THREE CHECKS IN HERE ASSERTED A WORD, NOT A BEHAVIOUR

    Nothing runs this gate -- `git grep verify_theme_experience_dual_plane_shell`
    finds two docs and no workflow, no hook, no composite verifier -- and three
    of its checks explain why: each was red by construction, and a gate that
    cannot be wired is not a gate.

    1. `SW_MARKER = "sms-v4.01.46-dual-plane-theme-sweep3-2026-06-02"` pinned
       `static/js/service-worker.js`'s CACHE_VERSION to the exact string shipped
       by the wave that wrote the check (00af0624a, 2026-06-03).  CLAUDE.md's
       deploy checklist step 3 requires that token to be bumped by EVERY wave
       that ships CSS or JS, so the equality is false the moment the next wave
       lands and false forever after.  It was the only `sms-v4.` literal
       anywhere in scripts/ outside a unit-test fixture.  Four artefacts claimed
       to know this one value and all four disagreed.

       Equality was never the invariant.  This stylesheet declares its own wave
       in its banner -- `rmc-theme-experience-dual-plane.css - vMAJOR.MINOR.PATCH
       (YYYY-MM-DD)` -- and the pinned SW string carried the SAME triple and the
       SAME date: the wave that revised the sheet also bumped the cache
       generation, so returning browsers stopped being served the pre-revision
       sheet from the service worker's static cache.  The durable form of that
       is monotonic:

           shipped CACHE_VERSION >= the wave the dual-plane sheet declares

       It compares two independent artefacts (a stylesheet banner and a JS
       declaration), it survives every future SW bump, and it goes red on the
       accident it exists to catch: revising the sheet's wave without bumping
       the cache generation.  The parsing is imported from
       scripts/admin_build_lock.py rather than copied -- that module already
       established this exact shape for three admin gates with the identical
       defect, and its `shipped_version()` reads the CACHE_VERSION DECLARATION
       rather than the whole file, which matters because service-worker.js's
       own header comments quote a dozen older version strings.

    2. `portal_base.html: expected >=3 ... includes (head, deferred, terminal)`
       (and the `>=2` variants for base.html, control_plane_skeleton.html and
       admin/base_site.html) counted INCLUDE STATEMENTS.  The triple-include was
       a cascade mechanism -- re-emitting the same <link> late in <body> puts a
       second copy of the sheet at a later position in the CSSOM -- and
       959584f4f (2026-07-31) deliberately retired it, hoisting the conditional
       late-body sheets (reduce-motion-low-power.css, rmc-lifecycle-concierge.css,
       rmc-support-quick-create.css) up into <head> AHEAD of one head-owned
       include: "Terminal dual-plane stylesheet is owned by head, never injected
       from body."  The count check has been asserting a retired mechanism for
       roughly a month longer than it was ever true.

       Measured rather than assumed: run
       scripts/shell_css_contract.order_decided_collisions between the dual-plane
       sheet and every sheet the retired body pass used to sit after
       (rmc-tour.css, rmc-notification-corner.css, reduce-motion-low-power.css,
       rmc-lifecycle-concierge.css, rmc-support-quick-create.css) and the answer
       is 0 for all five.  Not one declaration between them is decided by <link>
       order alone; every collision is settled by specificity or !important,
       which position cannot change.  The terminal pass protected nothing.

    3. `terminal dual-plane include too far from </body>` measured the byte
       distance from the last include to `</body>` against a threshold of 800.
       After (2) there is no terminal include: the last one is in <head>, some
       35 kB earlier, so the check reported a distance for a thing that no longer
       exists.  Distance was a proxy for "applies after the late body CSS"; that
       late body CSS now loads in <head> before the include, so the contract it
       was proxying is the head-ownership one asserted below.

WHAT IS ASSERTED INSTEAD

    * DELIVERY -- each shell must actually deliver the sheet, resolved through
      scripts/shell_css_contract: bundle-aware (portal-shell-enhanced.min.css
      concatenates 77 sources, so a filename grep answers the wrong question),
      `{% if False %}`-aware, and it follows {% include %} and {% extends %}.
      All five shells reach it through partials/rmc_authenticated_theme_tail.html.
    * HEAD OWNERSHIP -- on the three shells that own a <html><head><body>
      skeleton, the include lives in <head> and is not injected from <body>.
      That is the contract 959584f4f wrote, in the form a machine can check.
    * The `theme-platform-contrast.css` ordering check is KEPT, because unlike
      the three above it has a measured subject: 92 declarations between the two
      sheets are decided by <link> order alone, including the identical selector
      `html[data-resolved-theme="light"] body.control-plane-shell #cp-main-content`
      setting `color` in both files.

KNOWN LIMIT
    shell_css_contract answers "is it referenced on a path this shell can take",
    not "on every path": base.html's include sits in the `{% else %}` arm of
    `{% if RMC_AUTH_LANDING_LITE %}`, so the immersive login screen does not get
    the authenticated theme tail.  That is deliberate (it is the AUTHENTICATED
    theme layer) and evaluating arbitrary template conditions would be guesswork,
    so it is recorded here rather than asserted.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import admin_build_lock  # noqa: E402  (sibling helper; scripts/ is sys.path[0])
import shell_css_contract  # noqa: E402

CSS = ROOT / "static/css/rmc-theme-experience-dual-plane.css"
MARKER = "rmc-theme-experience-dual-plane.css"
PARTIAL = "rmc_theme_experience_dual_plane_styles.html"
PASS = "THEME_EXPERIENCE_DUAL_PLANE_SHELL_PASS"

#: `rmc-theme-experience-dual-plane.css - vMAJOR.MINOR.PATCH (YYYY-MM-DD)`, the
#: sheet's own wave banner.  Matched on one line so a later mention of the
#: filename in prose cannot supply the version.
BANNER = re.compile(
    r"rmc-theme-experience-dual-plane\.css[^\r\n]{0,8}?"
    r"v(?P<major>\d+)\.(?P<minor>\d+)\.(?P<patch>\d+)\s*"
    r"\((?P<date>\d{4}-\d{2}-\d{2})\)"
)

SHELLS = (
    "templates/base.html",
    "templates/portal_base.html",
    "templates/control_plane_skeleton.html",
    "templates/admin/base_site.html",
    "templates/admin/login.html",
)

#: The shells that own a document skeleton.  admin/base_site.html and
#: admin/login.html extend admin/base.html and write only {% block %} bodies, so
#: they have no <head>/<body> of their own and head-ownership is not theirs to
#: keep -- asserting it against their raw text would be asserting block order,
#: which the parent decides.
SKELETON_SHELLS = (
    "templates/base.html",
    "templates/portal_base.html",
    "templates/control_plane_skeleton.html",
)


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace")


def _check_service_worker_cache_generation(css: str, errors: list[str]) -> None:
    """Shipped CACHE_VERSION must be at least the wave this stylesheet declares.

    Replaces an equality pin on a June literal.  See the module docstring for
    why equality could never hold and what the pin was actually reaching for.
    """
    banner = BANNER.search(css)
    if banner is None:
        errors.append(
            f"{MARKER}: banner no longer declares its wave as "
            "'<filename> - vMAJOR.MINOR.PATCH (YYYY-MM-DD)'; without it there is "
            "nothing to check the service worker's cache generation against"
        )
        return

    shipped = admin_build_lock.shipped_version()
    if not shipped:
        errors.append(
            "static/js/service-worker.js: no `const CACHE_VERSION = \"...\";` "
            "declaration found"
        )
        return
    have = admin_build_lock.parse_version(shipped)
    if have is None:
        errors.append(
            f"static/js/service-worker.js: CACHE_VERSION {shipped!r} is not a "
            "parseable sms-vMAJOR.MINOR.PATCH string"
        )
        return

    want = (
        int(banner.group("major")),
        int(banner.group("minor")),
        int(banner.group("patch")),
    )
    if have < want:
        errors.append(
            f"static/js/service-worker.js: CACHE_VERSION {shipped} is OLDER than "
            f"the v{want[0]}.{want[1]}.{want[2]} ({banner.group('date')}) wave "
            f"declared by {MARKER} -- returning browsers keep serving the cached "
            f"pre-v{want[0]}.{want[1]}.{want[2]} stylesheet. Bump CACHE_VERSION "
            f"(CLAUDE.md deploy checklist step 3)"
        )


def _check_shell_delivery(errors: list[str]) -> None:
    """Every authenticated shell must actually deliver the dual-plane sheet."""
    for rel in SHELLS:
        if not (ROOT / rel).is_file():
            errors.append(f"missing shell: {rel}")
            continue
        finding = shell_css_contract.missing_stylesheet(rel, MARKER)
        if finding:
            errors.append(finding)
            continue
        text = shell_css_contract.reachable_text(rel)
        idx = max(text.rfind(MARKER), text.rfind(PARTIAL))
        contrast_idx = text.rfind("theme-platform-contrast.css")
        if contrast_idx != -1 and idx < contrast_idx:
            collisions = shell_css_contract.order_decided_collisions(
                "static/css/theme-platform-contrast.css",
                "static/css/rmc-theme-experience-dual-plane.css",
            )
            if collisions:
                first = collisions[0]
                errors.append(
                    f"{rel}: dual-plane loads BEFORE theme-platform-contrast.css "
                    f"and {len(collisions)} declaration(s) are decided by that "
                    f"order alone -- e.g. {first['property']} at specificity "
                    f"{first['specificity']} on {first['a']!r} vs {first['b']!r}"
                )


def _check_head_ownership(errors: list[str]) -> None:
    """959584f4f: the dual-plane layer is head-owned, never injected from body."""
    for rel in SKELETON_SHELLS:
        text = shell_css_contract.reachable_text(rel)
        head_close = text.find("</head>")
        body_open = re.search(r"<body\b", text)
        if head_close == -1 or body_open is None:
            errors.append(
                f"{rel}: no <head>...</head><body> skeleton found, so the "
                f"dual-plane layer has nowhere to be head-owned"
            )
            continue
        hits = [m.start() for m in re.finditer(re.escape(PARTIAL), text)]
        hits += [m.start() for m in re.finditer(re.escape(MARKER), text)]
        if not hits:
            errors.append(f"{rel}: no dual-plane include in reachable template text")
            continue
        if not any(pos < head_close for pos in hits):
            errors.append(
                f"{rel}: the dual-plane include is not in <head> -- since "
                f"959584f4f the terminal theme layer is head-owned and loads "
                f"after every conditional shell stylesheet"
            )
        if any(pos > body_open.start() for pos in hits):
            errors.append(
                f"{rel}: the dual-plane include is injected from <body> -- the "
                f"body-tail pass was retired by 959584f4f (measured: 0 of its "
                f"declarations against the late body sheets are decided by "
                f"<link> order), and a body <link> re-applies the sheet at a "
                f"later cascade position"
            )


def _check_shell_coherence(errors: list[str]) -> None:
    portal_path = ROOT / "templates/portal_base.html"
    portal = _read(portal_path)
    if "portal-sidebar-tone-light" in portal or "portal-sidebar-tone-dark" in portal:
        errors.append(
            "portal_base.html: portal-sidebar-tone-* body classes must not be SSR'd "
            "(resolved theme drives tenant sidebar via dual-plane CSS)"
        )
    base = _read(ROOT / "templates/base.html")
    if "rmc-platform-vertical-compact.css" in base:
        compact_idx = base.rfind("rmc-platform-vertical-compact.css")
        dual_idx = base.rfind(PARTIAL)
        if dual_idx < compact_idx:
            errors.append("base.html: dual-plane must load after rmc-platform-vertical-compact.css in head")
    if "header_theme_chip" in portal:
        errors.append(
            "portal_base.html: theme chip must live in user_dropdown only, not shell header"
        )

    theme_js = _read(ROOT / "static/js/theme-preference-bootstrap.js")
    for token in (
        "shouldSyncPortalBackendPalette",
        "manager-portal-bridge",
        "control-plane-shell",
    ):
        if token not in theme_js:
            errors.append(f"theme-preference-bootstrap.js missing operator guard: {token}")

    topbar = _read(ROOT / "templates/partials/manager_operator_topbar.html")
    if "_activity_ticker_inline.html" not in topbar:
        errors.append("manager_operator_topbar.html: Tier-1 inline LIVE badge missing")
    if "header_theme_chip" in topbar:
        errors.append(
            "manager_operator_topbar.html: theme controls belong in user_dropdown, not header"
        )

    user_dd = _read(ROOT / "templates/components/user_dropdown.html")
    if "Appearance" not in user_dd:
        errors.append("user_dropdown.html: Appearance section missing")
    if 'theme_chip_layout="dropdown"' not in user_dd:
        errors.append("user_dropdown.html: header_theme_chip dropdown layout missing")

    for rel, token in (
        ("static/css/design-tokens-luxury.css", "calc(72px * 1.1)"),
        ("static/css/rmc-platform-header.css", "calc(64px * 1.1)"),
    ):
        text = _read(ROOT / rel)
        if token not in text:
            errors.append(f"{rel}: platform header +10% height token missing")


def main() -> int:
    errors: list[str] = []

    if not CSS.is_file():
        errors.append(f"missing {CSS.relative_to(ROOT)}")
    else:
        css = _read(CSS)
        for token in (
            "--rmc-chrome-plane",
            "data-rmc-host-kind=\"tenant\"",
            "data-rmc-host-kind=\"manager\"",
            "manager-portal-bridge",
            "marketing-surface",
            "[data-rmc-authenticated-shell]",
            "body.backend-shell",
            "body.control-plane-shell .rmc-app-shell__header",
            "html[data-theme=\"dark\"] body.control-plane-shell .rmc-app-shell__canvas",
            "body.portal-body-with-layout:not(.control-plane-shell)",
            ".cp-primary-nav__pill--active",
            "html[data-surface=\"tenant\"] body.base-document-shell",
            ".cp-header .cp-topbar-search-input",
            ".bg-light",
            ".rmc-civic-footer a:hover",
            "body.manager-portal-bridge .cp-sidebar-col",
            "body.manager-portal-bridge .page-wrap",
            "cp-header--consolidated",
            "html[data-resolved-theme=\"light\"] body.portal-body-with-layout",
            ".rmc-workflow-progress-strip",
            "operator-civic",
            "body.manager-portal-bridge.control-plane-shell",
            ".metric-card",
            ".activity-section",
            ".child-card",
        ):
            if token not in css:
                errors.append(f"dual-plane CSS missing marker: {token}")
        _check_service_worker_cache_generation(css, errors)

    partial = ROOT / "templates/partials/rmc_theme_experience_dual_plane_styles.html"
    tail = ROOT / "templates/partials/rmc_authenticated_theme_tail.html"
    partial_src = _read(partial)
    if MARKER not in partial_src and "rmc_authenticated_theme_tail.html" not in partial_src:
        errors.append("partial missing stylesheet link")
    if MARKER not in _read(tail):
        errors.append("authenticated theme tail missing stylesheet link")

    _check_shell_delivery(errors)
    _check_head_ownership(errors)
    _check_shell_coherence(errors)

    if errors:
        for err in errors:
            print(f"FAIL: {err}", file=sys.stderr)
        return 1

    print(PASS)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
