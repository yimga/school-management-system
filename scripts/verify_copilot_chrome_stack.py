"""Platform-wide copilot chrome stack — tenant rail anchoring + z-index ladder.

Ensures tenant school surfaces (mission strip, pinned header, main canvas) never
paint over or under the fixed AI copilot rail, while the operator /super/ grid
contract stays separate.

The rail clears the tenant header by ANCHORING BELOW IT (mount top = the live
measured header height), not by insetting the header. The header carrying a
copilot gutter is the regression, not the contract.

PASS exits 0 with COPILOT_CHROME_STACK_PASS; any breach exits 1.
"""

from __future__ import annotations

import pathlib
import re
import sys

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent


def _read(rel: str) -> str:
    return (REPO_ROOT / rel).read_text(encoding="utf-8", errors="replace")


_RULE_RE = re.compile(r"([^{}]+)\{([^{}]*)\}", re.S)
_COMMENT_RE = re.compile(r"/\*.*?\*/", re.S)
# Either spelling of "inset me from the right edge by the rail width".
_RAIL_INSET_PROPS = ("padding-right", "padding-inline-end")
_HEADER_H_VARS = ("--rmc-app-shell-header-h", "--rmc-tenant-header-h")


def _rules_with_values(text: str) -> list[tuple[str, dict[str, str]]]:
    """[(selector, {prop: value})] for every rule, comments stripped.

    Values matter: this gate previously asserted one property SPELLING
    (``padding-inline-end``) in one file, so the surviving rule -- same effect,
    written ``padding-right``, living in the neighbouring stylesheet -- read as
    a breach for two months.
    """
    stripped = _COMMENT_RE.sub("", text)
    out: list[tuple[str, dict[str, str]]] = []
    for match in _RULE_RE.finditer(stripped):
        selector = match.group(1).strip().split("}")[-1].strip()
        if not selector or selector.startswith("@"):
            continue
        decls: dict[str, str] = {}
        for chunk in match.group(2).split(";"):
            prop, sep, value = chunk.partition(":")
            if sep:
                decls[prop.strip().lower()] = value.strip()
        for part in selector.split(","):
            part = part.strip()
            if part and not part.startswith("@"):
                out.append((part, decls))
    return out


def _insets_by_rail_width(decls: dict[str, str]) -> str | None:
    """Property inset from the right edge by the copilot rail width, if any."""
    for prop in _RAIL_INSET_PROPS:
        if "--rmc-app-shell-copilot-w" in decls.get(prop, ""):
            return prop
    return None


def main() -> int:
    findings: list[str] = []

    compact = _read("static/css/rmc-platform-vertical-compact.css")
    canvas = _read("static/css/rmc-tenant-workspace-canvas.css")
    portal = _read("templates/portal_base.html")
    mission = _read("templates/partials/tenant/tp_mission_strip.html")

    if "--rmc-copilot-rail-z:" not in compact:
        findings.append("rmc-platform-vertical-compact.css: missing --rmc-copilot-rail-z token")

    if "z-index: var(--rmc-copilot-rail-z" not in compact:
        findings.append(
            "rmc-platform-vertical-compact.css: copilot mount must use --rmc-copilot-rail-z"
        )

    if "z-index: 45" in compact:
        findings.append(
            "rmc-platform-vertical-compact.css: legacy copilot z-index 45 must be retired"
        )

    # ---- the tenant header/rail contract, asserted as behaviour ----------
    # This used to be a single grep for "padding-inline-end: calc(var(
    # --rmc-app-shell-copilot-w" in rmc-tenant-workspace-canvas.css. That gutter
    # was deliberately deleted in 47b0b1f7d (2026-06-28) after a headless-Chrome
    # probe on the real authenticated tenant render measured railTop 53 ==
    # headerBottom 53: the rail anchors BELOW the header and never beside it, so
    # the gutter only inset the header content and its LIVE banner 64px from the
    # right edge and the header read as "not full width". The gate kept asserting
    # the deleted word and failed continuously from that day, which is also why
    # nobody could tell whether the four things below were still true.
    compact_rules = _rules_with_values(compact)
    canvas_rules = _rules_with_values(canvas)

    mount_anchored = [
        selector
        for selector, decls in compact_rules
        if ".rmc-tenant-portal-copilot-mount" in selector
        and decls.get("position") == "fixed"
        and any(var in decls.get("top", "") for var in _HEADER_H_VARS)
    ]
    if not mount_anchored:
        findings.append(
            "rmc-platform-vertical-compact.css: tenant copilot rail mount must be "
            "position:fixed with top anchored to the live header height "
            "(--rmc-app-shell-header-h) -- that anchor, not a header gutter, is "
            "what keeps the rail from painting over .tp-header"
        )

    metrics = _read("static/js/rmc-tenant-shell-metrics.js")
    publishes_header_h = re.search(
        r"""heightOf\(\s*['"]\.tp-header['"]\s*\)""", metrics
    ) and re.search(
        r"""setProperty\(\s*['"]--rmc-app-shell-header-h['"]""", metrics
    )
    if not publishes_header_h:
        findings.append(
            "rmc-tenant-shell-metrics.js: must publish --rmc-app-shell-header-h from "
            "the MEASURED .tp-header height -- without it the rail top falls back to "
            "a magic number and can overlap a taller header"
        )

    main_inset = [
        selector
        for selector, decls in compact_rules
        if 'data-rmc-tenant-copilot-rail="1"' in selector
        and (".portal-main-col" in selector or "#main-content" in selector)
        and _insets_by_rail_width(decls)
    ]
    if not main_inset:
        findings.append(
            "rmc-platform-vertical-compact.css: tenant main canvas must stay inset by "
            "--rmc-app-shell-copilot-w -- the main column IS beside the rail, so "
            "without it page content paints under the copilot rail"
        )

    for rel, rules in (
        ("rmc-tenant-workspace-canvas.css", canvas_rules),
        ("rmc-platform-vertical-compact.css", compact_rules),
    ):
        for selector, decls in rules:
            if ".tp-header" not in selector:
                continue
            prop = _insets_by_rail_width(decls)
            if prop:
                findings.append(
                    f"{rel}: .tp-header re-adds a copilot gutter ({prop}) -- the rail "
                    f"is below the header, not beside it; this is the measured 64px "
                    f"lopsided-header regression 47b0b1f7d removed"
                )

    idx = portal.find("tp_mission_strip.html")
    if idx < 0:
        findings.append("portal_base.html: missing tp_mission_strip include")
    else:
        window = portal[max(0, idx - 500) : idx]
        if "tp_v3_tenant_shell" not in window:
            findings.append(
                "portal_base.html: tp_mission_strip must be gated to tp_v3_tenant_shell (tenant only)"
            )
        if "public_host_kind == 'manager'" in window:
            findings.append(
                "portal_base.html: tp_mission_strip must not render on manager host"
            )

    if "TENANT SCHOOL SURFACE ONLY" not in mission:
        findings.append(
            "tp_mission_strip.html: missing tenant-only surface documentation"
        )

    if "control-plane-shell" in mission:
        findings.append("tp_mission_strip.html: must not reference control-plane shell")

    if findings:
        for f in findings:
            print(f"FAIL: {f}", file=sys.stderr)
        return 1

    print("COPILOT_CHROME_STACK_PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
