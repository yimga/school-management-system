"""v4.00.66 — OneRoster v1.2 Roster Service spec § 4.13 ?filter= grammar.

Spec grammar (verbatim from the v1.2 PDF):

  filter        ::= predicate (logical_op predicate)*
  predicate     ::= field comparison_op 'value'
  logical_op    ::= 'AND' | 'OR'
  comparison_op ::= '=' | '!=' | '>' | '>=' | '<' | '<=' | '~'

v4.00.67 — Extended to support parenthesized nesting (real-world customers
ship ``(a OR b) AND c`` and similar expressions even though the v1.2 PDF
grammar is technically flat). The extension is conservative: parens
override the AND > OR precedence; outside parens the spec contract is
preserved unchanged.

v4.00.68 — Added unary ``NOT`` operator with the highest precedence (tighter
than AND/OR; loose enough that ``NOT a AND b`` parses as ``(NOT a) AND b``).
Double negation (``NOT NOT x``) is permitted. NOT binds to a single factor
(predicate or parenthesized expression), so ``NOT (a OR b)`` flips the
whole group. Lex-time keyword (case-sensitive per spec section 4.13).

  expression ::= term ( OR term )*
  term       ::= factor ( AND factor )*
  factor     ::= 'NOT' factor | predicate | '(' expression ')'
  predicate  ::= field comparison_op 'value'

The ``~`` operator is "contains" (case-insensitive substring match).
String literals are single-quoted; escape an embedded ``'`` with ``\\'``.
Field names are bare identifiers. NOT > AND > OR precedence.

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
# an AND/OR keyword (case-sensitive per spec), a comparison op, parens (v4.00.67),
# or a bare ident.
_TOKEN_RE = re.compile(
    r"""
    \s+                                    # whitespace (consumed but skipped)
    | '(?:\\.|[^'\\])*'                    # single-quoted string literal
    | \b(?:AND|OR|NOT)\b                   # boolean keyword (NOT added v4.00.68)
    | !=|>=|<=|[=<>~]                      # comparison op
    | [()]                                 # v4.00.67 parens for grouping
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


class _ParseError(Exception):
    """Internal — surfaced to the caller as always-True (fail-safe)."""


class _Parser:
    """v4.00.67 — Recursive-descent parser with paren support.
    v4.00.68 — Added NOT unary operator (tighter precedence than AND/OR).

    Grammar:
      expression ::= term ( OR term )*
      term       ::= factor ( AND factor )*
      factor     ::= 'NOT' factor | predicate | '(' expression ')'
      predicate  ::= field comparison_op 'value'
    """

    def __init__(self, tokens: list[str]):
        self.tokens = tokens
        self.pos = 0

    def _peek(self) -> str:
        return self.tokens[self.pos] if self.pos < len(self.tokens) else ""

    def _consume(self) -> str:
        tok = self._peek()
        self.pos += 1
        return tok

    def _at_end(self) -> bool:
        return self.pos >= len(self.tokens)

    def parse_expression(self) -> Callable[[dict], bool]:
        left = self.parse_term()
        while self._peek() == "OR":
            self._consume()
            right = self.parse_term()
            l, r = left, right
            left = lambda row, l=l, r=r: l(row) or r(row)  # noqa: E731
        return left

    def parse_term(self) -> Callable[[dict], bool]:
        left = self.parse_factor()
        while self._peek() == "AND":
            self._consume()
            right = self.parse_factor()
            l, r = left, right
            left = lambda row, l=l, r=r: l(row) and r(row)  # noqa: E731
        return left

    def parse_factor(self) -> Callable[[dict], bool]:
        # v4.00.68 — Unary NOT: highest precedence, binds to a single factor.
        # Double-negation works because parse_factor recurses on itself.
        if self._peek() == "NOT":
            self._consume()
            inner = self.parse_factor()
            return lambda row, inner=inner: not inner(row)
        if self._peek() == "(":
            self._consume()
            inner = self.parse_expression()
            if self._peek() != ")":
                raise _ParseError("unbalanced_parens")
            self._consume()
            return inner
        return self.parse_predicate()

    def parse_predicate(self) -> Callable[[dict], bool]:
        if self.pos + 2 >= len(self.tokens) + 1:
            raise _ParseError("truncated_predicate")
        field = self._consume()
        if field in ("AND", "OR", "NOT", "(", ")") or field in _COMPARISON_OPS:
            raise _ParseError(f"expected_field_got_{field!r}")
        op = self._consume()
        if op not in _COMPARISON_OPS:
            raise _ParseError(f"expected_comparison_op_got_{op!r}")
        lit_tok = self._consume()
        if not (lit_tok.startswith("'") and lit_tok.endswith("'")):
            raise _ParseError(f"expected_quoted_literal_got_{lit_tok!r}")
        lit = _unquote_literal(lit_tok)
        return _make_pred(field, op, lit)


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

    parser = _Parser(tokens)
    try:
        evaluator = parser.parse_expression()
    except _ParseError as exc:
        logger.debug("oneroster filter: parse failed (%s) for expr=%r", exc, expr)
        return _ALWAYS_TRUE
    except (IndexError, ValueError) as exc:
        logger.debug("oneroster filter: parser raised %s for expr=%r", exc, expr)
        return _ALWAYS_TRUE

    if not parser._at_end():
        logger.debug("oneroster filter: trailing tokens after parse: %r", tokens[parser.pos:])
        return _ALWAYS_TRUE

    return evaluator


def apply_filter(items: Iterable[dict], expr: str) -> list[dict]:
    """Convenience wrapper. Returns the original iterable as a list on
    empty/unparseable expr."""
    pred = parse_filter(expr)
    return [r for r in items if pred(r)]
