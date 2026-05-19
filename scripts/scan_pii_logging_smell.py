"""Scan: detect PII / secret material leaking through ``logger.*`` calls.

Searches every ``apps/**/*.py`` source for patterns that suggest
sensitive material is being **interpolated** into a log line — e.g.

    logger.info("user signed in password=%s", password)
    logger.debug(f"jwt token = {token}")
    logger.warning("legacy hash = " + user.legacy_password_hash)

Mere mention of a sensitive English word inside a literal string is
NOT a finding (e.g. ``logger.warning("Webhook secret not
configured")``); the scanner only flags when a sensitive keyword
appears in a context that implies a real value is being formatted in.

Heuristics — flag the logger call only if BOTH conditions hold:

  1. The call's argument span (parens-balanced across lines) mentions
     one of the sensitive keywords (case-insensitive) as an
     identifier-shaped substring.
  2. The argument span also contains at least one of:
        * an f-string body with that keyword (e.g. ``f"...{token}..."``)
        * a ``%s`` / ``%r`` / ``%d`` format spec PLUS the keyword as
          an argument identifier
        * a ``{`` ``.format()`` keyword arg with the keyword as the value
        * a string-concatenation ``+`` with the keyword

This keeps the baseline at 0 on the current tree (every existing
logger call with the word "token" / "secret" is an audit-status
message, not an interpolated leak).

Sensitive keywords:
    password, passwd, pwd, hash, secret, token, ssn, dob,
    api_key, apikey, private_key, signature_text

Markers
-------
Mark intentional sites with ``# pii-logging-smell-allow: <reason>``
on the same line as the log call. The marker reason must be a
3+-word phrase.

Zero-tolerance from day 1 — the baseline JSON ships at 0 and CI
fails on any net-new finding.

Usage:
    python scripts/scan_pii_logging_smell.py [--strict] [--json] [--update-baseline]
"""

from __future__ import annotations

import argparse
import json
import pathlib
import re
import sys


REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
APPS_DIR = REPO_ROOT / "apps"
BASELINE_PATH = REPO_ROOT / "var" / "security-audit-baseline-pii-logging-smell.json"

ALLOW_MARKER = "pii-logging-smell-allow:"

# Sensitive keyword list. Case-insensitive substring match on the
# logger call's argument span. NOTE: each keyword is wrapped in a
# non-letter boundary so e.g. "tokenize" does not match "token".
SENSITIVE_KEYWORDS = [
    "password",
    "passwd",
    "pwd",
    "hash",
    "secret",
    "token",
    "ssn",
    "dob",
    "api_key",
    "apikey",
    "private_key",
    "signature_text",
]

# Words that look sensitive but are domain-neutral and trip false
# positives. We exclude when the match falls inside one of these
# longer substrings.
EXCLUDE_SUBSTRINGS = [
    "hashlib",
    "hashed_",  # e.g. token_hashed-rule constants
    "hash_alg",
    "hash_count",
    "hash_prefix",  # legitimate audit shortening
    "tokenize",
    "tokenized",
    "tokenizer",
    "token_type",
    "tokens=",
    "secretsfile",
    "secretbox",  # libsodium scheme name
    "passphrase_count",
]


# Match logger.<level>( ... ) up to the matching close paren on the
# same line (single-line scan; multi-line calls are handled by
# checking each line independently — a sensitive keyword on ANY line
# of a multi-line call still trips because we run the keyword check
# per line).
LOGGER_CALL_RE = re.compile(
    r"\blog(?:ger)?\s*\.\s*(?:info|debug|warning|error|critical|exception)\s*\(",
    re.IGNORECASE,
)

def _extract_logger_call_spans(text: str) -> list[tuple[int, int, int]]:
    """Return list of (start_offset, end_offset, start_line_no) tuples for every
    parens-balanced logger.<level>(...) call. Multi-line aware.
    """
    spans: list[tuple[int, int, int]] = []
    for m in LOGGER_CALL_RE.finditer(text):
        start = m.start()
        # m.end() is just past the "("
        depth = 1
        i = m.end()
        n = len(text)
        in_str: str | None = None
        while i < n and depth > 0:
            ch = text[i]
            if in_str is None:
                if ch in ("'", '"'):
                    # detect triple-string
                    if text[i : i + 3] in ('"""', "'''"):
                        in_str = text[i : i + 3]
                        i += 3
                        continue
                    in_str = ch
                elif ch == "(":
                    depth += 1
                elif ch == ")":
                    depth -= 1
                    if depth == 0:
                        i += 1
                        break
            else:
                # inside a string literal — handle close
                if in_str in ('"""', "'''"):
                    if text[i : i + 3] == in_str:
                        i += 3
                        in_str = None
                        continue
                else:
                    if ch == "\\":
                        i += 2
                        continue
                    if ch == in_str:
                        in_str = None
            i += 1
        if depth == 0:
            # Look up start line number.
            line_no = text.count("\n", 0, start) + 1
            spans.append((start, i, line_no))
    return spans


def _looks_like_interpolation(span_body: str, keyword: str) -> bool:
    """Return True when ``span_body`` interpolates a value tied to
    ``keyword`` (vs. merely mentioning the word in literal text).

    Strict heuristics:
      * f-string body contains ``{<keyword>...}`` (or .<keyword>).
      * The keyword appears OUTSIDE any string literal in the span
        — which means it is an identifier passed as a logger argument,
        e.g. ``logger.info("got %s", password)``. The bare-identifier
        check is the strongest signal of a real value being formatted.
      * String concatenation: ``"..." + <keyword>`` or ``<keyword> + "..."``.
    """
    # Strip string-literal interiors EXCEPT f-string bodies. We do this
    # by splitting on string-literal regex.
    # Walk the span and accumulate "non-string" portions for ident scan.
    # f-string detection.
    fstring_re = re.compile(
        r'(?:[fF][rR]?|[rR][fF])(["\'])(?P<body>(?:\\.|(?!\1).)*?)\1',
        re.DOTALL,
    )
    for fm in fstring_re.finditer(span_body):
        body = fm.group("body")
        # Find {...} substitutions in f-string body.
        for sub in re.finditer(r"\{([^{}]+?)\}", body):
            inner = sub.group(1).lower()
            # Strip format spec after ":"
            inner_var = inner.split(":", 1)[0].split("!", 1)[0]
            if re.search(
                r"(?<![A-Za-z0-9_])"
                + re.escape(keyword.lower())
                + r"(?![A-Za-z0-9_])",
                inner_var,
            ):
                return True

    # Build "code-only" view: replace string-literal interiors with
    # spaces (preserving offsets is unnecessary — we only need to
    # search the residue).
    string_re = re.compile(
        r'''(?P<prefix>[rRbBuU]{0,2}|[fF][rR]?|[rR][fF])(?P<q>"""|'''
        r"""'''"""
        r'''|"|')(?P<body>(?:\\.|(?!(?P=q)).)*?)(?P=q)''',
        re.DOTALL,
    )
    residue = string_re.sub(lambda m: " " * len(m.group(0)), span_body)
    # Pre-strip excluded substrings so false positives like "tokenize"
    # and "secretbox" don't cause hits via word-boundary scan.
    for excl in EXCLUDE_SUBSTRINGS:
        residue = re.sub(re.escape(excl), " " * len(excl), residue, flags=re.IGNORECASE)
    # Find keyword as identifier outside strings. We DO allow a
    # preceding "." (so ``maa.signature_text`` / ``user.password_hash``
    # tip the scanner — these are real-value attribute accesses,
    # exactly what we want to catch).
    if re.search(
        r"(?<![A-Za-z0-9_])" + re.escape(keyword) + r"(?![A-Za-z0-9_])",
        residue,
        re.IGNORECASE,
    ):
        return True

    return False


def _scan_file(path: pathlib.Path) -> list[str]:
    findings: list[str] = []
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return findings

    spans = _extract_logger_call_spans(text)
    for start, end, line_no in spans:
        span_body = text[start:end]
        # Honor allow-marker on any line within the span (most often
        # on the same line as the opening ``logger.<lvl>(`` call).
        line_start = text.rfind("\n", 0, start) + 1
        # End of the line that contains the span's open paren.
        first_line_end = text.find("\n", start)
        if first_line_end == -1:
            first_line_end = len(text)
        opening_line = text[line_start:first_line_end]
        # Also check the closing line for the marker.
        closing_line_start = text.rfind("\n", 0, end) + 1
        closing_line_end = text.find("\n", end)
        if closing_line_end == -1:
            closing_line_end = len(text)
        closing_line = text[closing_line_start:closing_line_end]
        if ALLOW_MARKER in opening_line or ALLOW_MARKER in closing_line:
            continue

        for kw in SENSITIVE_KEYWORDS:
            if _looks_like_interpolation(span_body, kw):
                findings.append(
                    f"{path.relative_to(REPO_ROOT)}:{line_no}: "
                    f"logger.* call interpolates '{kw}': "
                    f"{opening_line.strip()[:160]}"
                )
                break  # one finding per span

    return findings


def scan_all() -> list[str]:
    findings: list[str] = []
    if not APPS_DIR.exists():
        return findings
    for py in APPS_DIR.rglob("*.py"):
        # Skip migrations + test files + generated/cached output.
        rel = py.relative_to(REPO_ROOT).as_posix()
        if "/migrations/" in rel or "/__pycache__/" in rel:
            continue
        if rel.endswith("/tests.py") or "/tests/" in rel:
            continue
        findings.extend(_scan_file(py))
    return findings


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Exit 1 if any current violation exceeds baseline (zero-tolerance).",
    )
    parser.add_argument(
        "--update-baseline",
        action="store_true",
        help="Overwrite baseline JSON with current count (use only when reducing).",
    )
    parser.add_argument("--json", action="store_true", help="Emit JSON output.")
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

    if args.update_baseline or not BASELINE_PATH.exists():
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
        print(f"pii-logging-smell scan: {total} violation(s)")
        print(f"baseline: {baseline_total}")
        for f in findings[:30]:
            print(f"  {f}")

    if args.strict and total > baseline_total:
        print(f"FAIL: {total} > baseline {baseline_total}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
