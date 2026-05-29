"""v4.00.66 — OneRoster v1.2 Roster Service spec § 4.13 ?filter= grammar.

Spec grammar (verbatim from the v1.2 PDF):

  filter        ::= predicate (logical_op predicate)*
  predicate     ::= field comparison_op 'value'
  logical_op    ::= 'AND' | 'OR'
  comparison_op ::= '=' | '!=' | '>' | '>=' | '<' | '<=' | '~'

The ``~`` operator is "contains" (case-insensitive substring match).
String literals are single-quoted; escape an embedded ``'`` with ``\\'``.
Field names are bare identifiers. AND has higher precedence than OR.

Implementation contract:

  parse_filter(expr: str) -> Callable[[dict], bool]

The callable returns True for rows matching the filter. Operator-facing
surface: a bad / unparseable expression returns the always-True callable
(NEVER 400) so a typo in the URL doesn't drop the operator into an empty
result set without warning. ``apply_filter`` is the convenience wrapper.

Numeric comparisons (``>`` / ``>=`` / ``<`` / ``<=``) coerce values to
``float`` when the row value looks numeric AND the literal looks numeric;
otherwise fall through to lexicographic string compare (works for ISO
timestamps and version strings).

NEVER raises — parser is fail-safe by design.
"""
from __future__ import annotations

import logging
import re
from typing import Any, Callable, Iterable

logger = logging.getLogger(__name__)


_COMPARISON_OPS = ("!=", ">=", "<=", "=", ">", "<", "~")

# Tokenizer regex: match either a single-quoted string (with backslash escape),
# an AND/OR keyword (case-sensitive per spec), a comparison op, or a bare ident.
_TOKEN_RE = re.compile(
    r"""
    \s+                                    # whitespace (consumed but skipped)
    | '(?:\\.|[^'\\])*'                    # single-quoted string literal
    | \b(?:AND|OR)\b                       # boolean keyword
    | !=|>=|<=|[=<>~]                      # comparison op
    | [A-Za-z_][A-Za-z0-9_.]*              # identifier (field name)
    """,
    re.VERBOSE,
)


def _tokenize(expr: str) -> list[str]:
    """Lex into tokens; whitespace dropped, quoted strings preserved with quotes."""
    out = []
    pos = 0
    while pos < len(expr):
        m = _TOKEN_RE.match(expr, pos)
        if m is None:
            return []  # un-lex-able input
        tok = m.group(0)
        pos = m.end()
        if tok.strip() == "":
            continue
        out.append(tok)
    return out


def _unquote_literal(tok: str) -> str:
    """Strip the surrounding single quotes + unescape ``\\'`` and ``\\\\``."""
    if len(tok) >= 2 and tok[0] == "'" and tok[-1] == "'":
        inner = tok[1:-1]
        # Unescape: \' -> '   and  \\ -> \
        return inner.replace(r"\'", "'").replace(r"\\", "\\")
    return tok


def _try_float(v: Any) -> tuple[bool, float]:
    try:
        return True, float(v)
    except (ValueError, TypeError):
        return False, 0.0


def _cmp(row_val: Any, op: str, lit: str) -> bool:
    if op == "=":
        return str(row_val or "") == lit
    if op == "!=":
        return str(row_val or "") != lit
    if op == "~":
        return lit.lower() in str(row_val or "").lower()
    # Ordering ops: try numeric, fall back to string.
    ok_row, num_row = _try_float(row_val)
    ok_lit, num_lit = _try_float(lit)
    if ok_row and ok_lit:
        a, b = num_row, num_lit
    else:
        a, b = str(row_val or ""), lit
    if op == ">":
        return a > b
    if op == ">=":
        return a >= b
    if op == "<":
        return a < b
    if op == "<=":
        return a <= b
    return False


def _make_pred(field: str, op: str, lit: str) -> Callable[[dict], bool]:
    def pred(row: dict) -> bool:
        return _cmp(row.get(field), op, lit)
    return pred


_ALWAYS_TRUE: Callable[[dict], bool] = lambda _row: True  # noqa: E731


def parse_filter(expr: str) -> Callable[[dict], bool]:
    """Parse a filter expression. Returns the always-True callable on
    empty / unparseable input (operator-facing surface — don't 400)."""
    expr = (expr or "").strip()
    if not expr:
        return _ALWAYS_TRUE

    tokens = _tokenize(expr)
    if not tokens:
        logger.debug("oneroster filter: un-lex-able expr=%r", expr)
        return _ALWAYS_TRUE

    # Parse predicates separated by AND / OR. Build flat list:
    # [pred, op, pred, op, ...]
    items: list = []
    i = 0
    while i < len(tokens):
        # predicate: field comparison_op 'value'
        if i + 2 >= len(tokens):
            logger.debug("oneroster filter: trailing tokens at %r", tokens[i:])
            return _ALWAYS_TRUE
        field, op, lit_tok = tokens[i], tokens[i + 1], tokens[i + 2]
        if op not in _COMPARISON_OPS:
            logger.debug("oneroster filter: expected comparison op, got %r", op)
            return _ALWAYS_TRUE
        if not (lit_tok.startswith("'") and lit_tok.endswith("'")):
            logger.debug("oneroster filter: expected quoted literal, got %r", lit_tok)
            return _ALWAYS_TRUE
        lit = _unquote_literal(lit_tok)
        items.append(_make_pred(field, op, lit))
        i += 3
        if i < len(tokens):
            kw = tokens[i]
            if kw not in ("AND", "OR"):
                logger.debug("oneroster filter: expected AND/OR, got %r", kw)
                return _ALWAYS_TRUE
            items.append(kw)
            i += 1

    if not items:
        return _ALWAYS_TRUE

    # Apply AND precedence first: collapse runs of preds joined by AND
    # into a single AND-group, then OR the groups together.
    or_groups: list[list[Callable]] = [[]]
    j = 0
    while j < len(items):
        node = items[j]
        if callable(node):
            or_groups[-1].append(node)
            j += 1
            continue
        # node is "AND" or "OR"
        if node == "AND":
            j += 1
            continue
        # OR — start a new group
        or_groups.append([])
        j += 1

    def evaluator(row: dict) -> bool:
        for group in or_groups:
            if not group:
                continue
            if all(p(row) for p in group):
                return True
        return False

    return evaluator


def apply_filter(items: Iterable[dict], expr: str) -> list[dict]:
    """Convenience wrapper. Returns the original iterable as a list on
    empty/unparseable expr."""
    pred = parse_filter(expr)
    return [r for r in items if pred(r)]
