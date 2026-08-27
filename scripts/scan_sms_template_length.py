"""Scan: SMS template bodies must fit in 160 chars after substitution.

The bug class this catches (SMS carrier multipart charge + delivery
unreliability):

    SMS_X = {
        "en": "Long body that exceeds 160 chars after substitution "
              "with realistic values + currency + threshold..."
    }
    → Twilio splits into 2 segments → 2x cost per send + delivery race.

Scanner contract:
  * AST-parses every `apps/**/sms_templates*.py` and `apps/**/sms.py` /
    `apps/**/*_sms.py`.
  * For each module-level string assignment OR dict-of-strings literal,
    substitutes placeholders (`{first}`, `{amount}`, `{currency}`, etc.)
    with realistic SMS-sized values and asserts ≤160 chars.
  * Honors `# sms-multipart-allow: <reason>` on the same line OR within
    the call/assignment expression's leading comment block — for the
    rare case where multipart IS the desired behavior (e.g. 2-part
    emergency broadcast).

Substitution placeholders default:
  * {first}    → "Aleksandra"          (12 chars; long-name worst case)
  * {amount}   → "1,234.56"            (8 chars; 5-figure balance)
  * {currency} → "NGN"                 (3 chars)
  * {school}   → "Saint Sebastien"     (15 chars; long-name worst case)
  * {url}      → "https://r.mc/a1B2c"  (18 chars; bitly-style short URL)
  * any other placeholder → 16-char default.

Zero-tolerance gate from day 1 (v3.57.1, 2026-05-21).

Usage:
    python scripts/scan_sms_template_length.py [--strict] [--json] [--update-baseline]
"""

from __future__ import annotations

import argparse
import ast
import json
import pathlib
import re
import sys


REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
APPS_ROOT = REPO_ROOT / "apps"
BASELINE_PATH = REPO_ROOT / "var" / "security-audit-baseline-sms-template-length.json"

MAX_SMS_CHARS = 160
ALLOW_MARKER = "sms-multipart-allow:"

# Worst-case substitution values (long names, max digits, short URLs).
DEFAULT_SUBSTITUTIONS: dict[str, str] = {
    "first": "Aleksandra",
    "name": "Aleksandra",
    "student": "Aleksandra",
    "amount": "1,234.56",
    "balance": "1,234.56",
    "value": "1,234.56",
    "currency": "NGN",
    "school": "Saint Sebastien",
    "url": "https://r.mc/a1B2c",
    "link": "https://r.mc/a1B2c",
    "code": "493812",
    "time": "5:30 PM",
    "date": "2026-05-21",
    # The catalog in apps/communication spells its variables out in full, and a
    # placeholder with no entry here falls back to 16 chars. That fallback is a
    # fiction for a day count or a clock time, and it inflates every body that
    # uses one -- measuring a template as over-length when it is not is the same
    # kind of false report as missing one that is. Worst case, but the real
    # worst case.
    "guardian_first_name": "Aleksandra",
    "student_name": "Aleksandra Nowak",
    "applicant_name": "Aleksandra Nowak",
    "school_name": "Saint Sebastien",
    "days_overdue": "120",
    "delay_minutes": "120",
    "invoice_reference": "INV-2026-004821",
    "payment_reference": "PAY-2026-004821",
    "absent_date": "2026-05-21",
    "closure_date": "2026-05-21",
    "effective_date": "2026-05-21",
    "interview_date": "2026-05-21",
    "arrival_time": "5:30 PM",
    "interview_time": "5:30 PM",
    "new_eta": "5:30 PM",
    "route_name": "North Ridge Loop",
    "weather_event": "heavy rainfall",
    "location": "Main Hall, Block C",
}
GENERIC_FALLBACK = "x" * 16

PLACEHOLDER_RE = re.compile(r"\{([a-zA-Z_][a-zA-Z_0-9]*)\}")


def _substitute(template: str) -> str:
    def _resolve(match: re.Match[str]) -> str:
        key = match.group(1)
        return DEFAULT_SUBSTITUTIONS.get(key.lower(), GENERIC_FALLBACK)

    return PLACEHOLDER_RE.sub(_resolve, template)


# Declarative catalogs: a dict of entries where one key lists the channels and
# another holds the body. These do not live in a file whose NAME says sms, and
# they are where every SMS the platform sends is actually written.
#   module -> (dict name, channels key, body key)
CHANNEL_CATALOGS: dict[str, tuple[str, str, str]] = {
    "apps/communication/template_catalog.py": (
        "COMMUNICATION_TEMPLATES",
        "channels",
        "body_template",
    ),
}


def _catalog_census(rel: str, spec: tuple[str, str, str]) -> list[tuple[int, int, str]]:
    """(rendered_length, lineno, name) for EVERY catalog entry that sends over sms.

    Every entry, not just the over-length ones, because a gate that prints
    nothing when it finds nothing is indistinguishable from a gate that is not
    looking. This scanner spent its whole life reporting a clean zero while
    reading a file that holds no SMS bodies at all; the census is what makes its
    zero checkable by a person.
    """
    dict_name, channels_key, body_key = spec
    path = REPO_ROOT / rel
    if not path.is_file():
        return []
    try:
        tree = ast.parse(path.read_text(encoding='utf-8'), filename=str(path))
    except (OSError, SyntaxError):
        return []
    census: list[tuple[int, int, str]] = []
    for node in tree.body:
        targets = (
            [node.target]
            if isinstance(node, ast.AnnAssign)
            else getattr(node, 'targets', [])
        )
        if not any(getattr(t, 'id', None) == dict_name for t in targets):
            continue
        if not isinstance(node.value, ast.Dict):
            continue
        for key_node, entry_node in zip(node.value.keys, node.value.values):
            if not isinstance(entry_node, ast.Dict):
                continue
            entry = {
                k.value: v
                for k, v in zip(entry_node.keys, entry_node.values)
                if isinstance(k, ast.Constant)
            }
            channels_node = entry.get(channels_key)
            channels = (
                [c.value for c in channels_node.elts if isinstance(c, ast.Constant)]
                if isinstance(channels_node, ast.List)
                else []
            )
            if "sms" not in channels:
                continue
            body_node = entry.get(body_key)
            try:
                body = ast.literal_eval(body_node)
            except (ValueError, TypeError, SyntaxError):
                continue
            if not isinstance(body, str):
                continue
            rendered = _substitute(body)
            name = key_node.value if isinstance(key_node, ast.Constant) else "?"
            census.append((len(rendered), entry_node.lineno, name))
    return census


def _catalog_findings(rel: str, spec: tuple[str, str, str]) -> list[str]:
    """The census entries that will not fit in a single carrier segment."""
    findings: list[str] = []
    for length, lineno, name in _catalog_census(rel, spec):
        if length <= MAX_SMS_CHARS:
            continue
        segments = -(-length // MAX_SMS_CHARS)
        findings.append(
            f"{rel}:{lineno}: "
            f"rendered len={length} > {MAX_SMS_CHARS} "
            f"({segments} SMS segments, {segments}x carrier cost per send) "
            f"-- catalog entry {name!r}"
        )
    return findings


def _is_sms_module(path: pathlib.Path) -> bool:
    name = path.name.lower()
    if "sms_templates" in name:
        return True
    if name == "sms.py":
        return True
    if name.endswith("_sms.py"):
        return True
    return False


def _collect_strings(node: ast.AST) -> list[tuple[int, str]]:
    """Walk module AST, yield (line, literal-string) for every constant string
    that is the value of an assignment OR a dict-value at module scope."""
    out: list[tuple[int, str]] = []
    for child in ast.walk(node):
        # str = "..."  /  str: type = "..."
        if isinstance(child, (ast.Assign, ast.AnnAssign)):
            val = getattr(child, "value", None)
            if isinstance(val, ast.Constant) and isinstance(val.value, str):
                out.append((child.lineno, val.value))
            elif isinstance(val, ast.Dict):
                _walk_dict(val, out)
        elif isinstance(child, ast.Dict):
            _walk_dict(child, out)
    return out


def _walk_dict(node: ast.Dict, out: list[tuple[int, str]]) -> None:
    for v in node.values:
        if isinstance(v, ast.Constant) and isinstance(v.value, str):
            out.append((v.lineno, v.value))
        elif isinstance(v, ast.Dict):
            _walk_dict(v, out)
        elif isinstance(v, (ast.JoinedStr,)):
            # Reconstruct an f-string as best-effort literal
            parts: list[str] = []
            for piece in v.values:
                if isinstance(piece, ast.Constant) and isinstance(piece.value, str):
                    parts.append(piece.value)
                elif isinstance(piece, ast.FormattedValue):
                    # Use a generic 12-char placeholder for interpolated values
                    parts.append("x" * 12)
            out.append((v.lineno, "".join(parts)))


def scan_file(path: pathlib.Path) -> list[str]:
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return []
    if ALLOW_MARKER in text:
        # Module-wide allow opts the whole file out (use sparingly).
        first_500 = text[:500]
        if ALLOW_MARKER in first_500:
            return []
    try:
        tree = ast.parse(text)
    except SyntaxError:
        return []
    findings: list[str] = []
    lines = text.splitlines()
    for lineno, raw in _collect_strings(tree):
        # Skip docstrings + huge multi-line bodies (>500 chars implies it's
        # almost certainly prose, not an SMS body).
        if len(raw) > 500:
            continue
        # Skip empty / single-word constants
        if len(raw.strip()) < 8:
            continue
        # Per-line allow marker
        idx = max(0, lineno - 1)
        nearby = "\n".join(lines[max(0, idx - 1) : idx + 2])
        if ALLOW_MARKER in nearby:
            continue
        rendered = _substitute(raw)
        if len(rendered) > MAX_SMS_CHARS:
            findings.append(
                f"{path.relative_to(REPO_ROOT)}:{lineno}: "
                f"rendered len={len(rendered)} > {MAX_SMS_CHARS} — "
                f"{raw[:60].replace(chr(10), ' ')}…"
            )
    return findings


def scan_all() -> list[str]:
    findings: list[str] = []
    if not APPS_ROOT.exists():
        return findings
    for py in APPS_ROOT.rglob("*.py"):
        if not _is_sms_module(py):
            continue
        findings.extend(scan_file(py))
    # The bodies that actually get sent do not live in a file whose NAME says sms.
    for rel, spec in CHANNEL_CATALOGS.items():
        findings.extend(_catalog_findings(rel, spec))
    return sorted(findings)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--strict",
        action="store_true",
        help="zero tolerance: fail on ANY over-length body, not just new ones",
    )
    parser.add_argument(
        "--compare",
        action="store_true",
        help="accepted for runner uniformity; comparing to the baseline is the default",
    )
    parser.add_argument("--update-baseline", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    findings = scan_all()
    total = len(findings)

    BASELINE_PATH.parent.mkdir(parents=True, exist_ok=True)
    baseline_total = 0
    if BASELINE_PATH.exists():
        try:
            baseline_total = int(
                json.loads(BASELINE_PATH.read_text(encoding="utf-8")).get(
                    "finding_count", 0
                )
            )
        except (json.JSONDecodeError, ValueError):
            baseline_total = 0

    if not BASELINE_PATH.exists() and not args.update_baseline:
        # Authoring the reference during a checking run is how a ratchet quietly
        # re-anchors to a regression. Refuse, and name the deliberate command.
        print(
            f"FAIL: no baseline at {BASELINE_PATH}. Generate it with "
            "--update-baseline and COMMIT it.",
            file=sys.stderr,
        )
        return 1

    if args.update_baseline:
        BASELINE_PATH.write_text(
            json.dumps(
                {"finding_count": total, "findings": findings},
                indent=2,
            ),
            encoding="utf-8",
        )

    if args.json:
        print(
            json.dumps(
                {
                    "finding_count": total,
                    "baseline": baseline_total,
                    "findings": findings,
                },
                indent=2,
            )
        )
    else:
        print(f"sms-template-length scan: {total} body(ies) > {MAX_SMS_CHARS} chars")
        print(f"baseline: {baseline_total}")
        for f in findings[:30]:
            print(f"  {f}")
        # A pass/fail cliff hides the body sitting one character below it. Print
        # the tightest entries so "0 findings" can be read as a measurement
        # rather than taken on trust.
        census: list[tuple[int, int, str]] = []
        for rel, spec in CHANNEL_CATALOGS.items():
            census.extend(_catalog_census(rel, spec))
        if census:
            print(f"headroom (of {len(census)} sms bodies, tightest first):")
            for length, _lineno, name in sorted(census, reverse=True)[:5]:
                left = MAX_SMS_CHARS - length
                note = " <-- NO HEADROOM" if 0 <= left < 10 else ""
                print(f"  {length:4d}/{MAX_SMS_CHARS}  {left:+4d} spare  {name}{note}")

    # Enforcing only under --strict meant the runner had to remember to ask for
    # correctness, and it did not: this gate was wired to nothing and would have
    # printed PASS anyway. A ratchet enforces by default; --strict raises the bar
    # from "no new ones" to "none at all".
    limit = 0 if args.strict else baseline_total
    if total > limit:
        print(
            f"FAIL: {total} over-length SMS bod(ies) > limit {limit}. Each one "
            "costs an extra carrier segment on EVERY send.",
            file=sys.stderr,
        )
        return 1
    if total < baseline_total:
        print(
            f"OK: down to {total} from a baseline of {baseline_total}. "
            "Run --update-baseline and commit it."
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
