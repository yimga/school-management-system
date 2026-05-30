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

v4.00.69 — Added ``field IN('a','b','c')`` list operator. This is sugar for
``field='a' OR field='b' OR field='c'`` — practical for ?filter= URLs that
otherwise have to repeat the same field across OR chains. Empty list
``IN()`` is fail-safe (always-False — set membership with no elements
matches nothing).

v4.00.84 — Added SQL-style ``field IS NULL`` and ``field IS NOT NULL``
predicates. Per IMS spec § 4.13 a field is NULL when it is either Python
``None`` OR the empty string ``""`` (absent + cleared are equivalent).
The ``IS`` / ``NULL`` keywords are matched case-insensitively at the
tokenizer (operator-friendly — URLs in the wild lowercase routinely).

v4.00.85 — Added SQL-style ``field LIKE '<pattern>'`` predicate with the
two standard wildcards ``%`` (zero-or-more chars) and ``_`` (single
char). The pattern is compiled to an anchored case-INSENSITIVE regex
per the IMS Roster Service spec § 4.13 contract for LIKE matching.
Regex specials in the user pattern are escaped before the wildcards
are expanded, so ``LIKE '50%'`` matches the literal ``50%`` prefix
without the ``%`` triggering greedy regex semantics.

  expression ::= term ( OR term )*
  term       ::= factor ( AND factor )*
  factor     ::= 'NOT' factor | predicate | '(' expression ')'
  predicate  ::= field comparison_op 'value'
                 | field 'IS' 'NULL'
                 | field 'IS' 'NOT' 'NULL'
                 | field 'IN' '(' 'value' (',' 'value')* ')'
                 | field 'LIKE' 'value'

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
# an AND/OR/NOT/IN keyword (case-sensitive per spec for AND/OR; NOT/IN/IS/NULL
# are also matched case-insensitively below so URL-shaped expressions work in
# the wild), a comparison op, parens (v4.00.67), or a bare ident.
_TOKEN_RE = re.compile(
    r"""
    \s+                                    # whitespace (consumed but skipped)
    | '(?:\\.|[^'\\])*'                    # single-quoted string literal
    | \b(?:AND|OR|NOT|IN|IS|NULL|LIKE|BETWEEN)\b  # boolean keyword + IN (v4.00.69) + IS/NULL (v4.00.84) + LIKE (v4.00.85) + BETWEEN (v4.00.91 W1 Pillar D4)
    | !=|>=|<=|[=<>~]                      # comparison op
    | [(),]                                # parens (v4.00.67) + comma (v4.00.69)
    | [A-Za-z_][A-Za-z0-9_.]*              # identifier (field name)
    """,
    re.VERBOSE,
)

# v4.00.84 — Keywords that are case-insensitive at the parser level. Tokens
# matching one of these (after .upper()) are normalized to the canonical
# uppercase form before parser dispatch. AND/OR remain case-sensitive per
# spec § 4.13 (already-existing behaviour, unchanged).
_CI_KEYWORDS = frozenset({"NOT", "IN", "IS", "NULL", "LIKE", "BETWEEN"})


def _tokenize(expr: str) -> list[str]:
    """Lex into tokens; whitespace dropped, quoted strings preserved with quotes.

    Case-insensitive keywords (NOT/IN/IS/NULL) are normalized to upper-case
    so downstream parser comparisons can use a single canonical form. AND/OR
    are NOT normalized — they're already matched case-sensitively by the
    tokenizer regex per IMS spec § 4.13.
    """
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
        # v4.00.84 — Normalize case-insensitive keywords so the parser can
        # compare against the canonical UPPER form. A bareword that upper-
        # cases to a known keyword (e.g. ``is`` -> ``IS``) is treated as
        # that keyword regardless of input casing.
        if tok.upper() in _CI_KEYWORDS:
            tok = tok.upper()
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


def _compile_like_pattern(pattern: str) -> "re.Pattern[str]":
    """v4.00.85 — Translate a SQL-LIKE pattern to an anchored regex.

    Wildcards:
      - ``%`` -> ``.*`` (zero-or-more chars)
      - ``_`` -> ``.``  (single char)

    All other regex specials are escaped first via ``re.escape`` so a
    literal ``50%`` matches ``50<anything>``; the leading ``50`` is
    literal because ``5`` and ``0`` aren't regex specials. The escaped
    form of ``%`` from ``re.escape`` is ``%`` itself (it's not a regex
    metachar) on Py3.7+ — but to defend against older Python versions
    that escape it as ``\\%`` we tolerate both before doing the swap.

    Returned regex is anchored on BOTH ends and case-INSENSITIVE per
    the IMS Roster Service spec § 4.13 LIKE contract.
    """
    escaped = re.escape(pattern)
    # Older Python ``re.escape`` may emit ``\\%`` / ``\\_``; modern (3.7+)
    # emits ``%`` / ``_`` unchanged. Handle both so we work on all hosts.
    escaped = escaped.replace(r"\%", ".*").replace("%", ".*")
    escaped = escaped.replace(r"\_", ".").replace("_", ".")
    return re.compile(r"\A" + escaped + r"\Z", re.IGNORECASE | re.DOTALL)


def _make_like_pred(field: str, pattern: str) -> Callable[[dict], bool]:
    """v4.00.85 — Build a closure that matches the row value against the
    LIKE pattern. NULL/missing field values are treated as the empty
    string (consistent with v4.00.84 IS NULL semantics)."""
    compiled = _compile_like_pattern(pattern)
    def pred(row: dict, field=field, compiled=compiled) -> bool:
        v = row.get(field)
        return bool(compiled.match("" if v is None else str(v)))
    return pred


_ALWAYS_TRUE: Callable[[dict], bool] = lambda _row: True  # noqa: E731


class _ParseError(Exception):
    """Internal — surfaced to the caller as always-True (fail-safe)."""


class _Parser:
    """v4.00.67 — Recursive-descent parser with paren support.
    v4.00.68 — Added NOT unary operator (tighter precedence than AND/OR).
    v4.00.69 — Added ``field IN(...)`` list-membership predicate.
    v4.00.84 — Added ``field IS NULL`` and ``field IS NOT NULL`` predicates.
    v4.00.85 — Added ``field LIKE '<pattern>'`` predicate with ``%`` / ``_``
    wildcards (case-INSENSITIVE per spec).

    Grammar:
      expression ::= term ( OR term )*
      term       ::= factor ( AND factor )*
      factor     ::= 'NOT' factor | predicate | '(' expression ')'
      predicate  ::= field comparison_op 'value'
                   | field 'IS' 'NULL'
                   | field 'IS' 'NOT' 'NULL'
                   | field 'IN' '(' 'value' (',' 'value')* ')'
                   | field 'LIKE' 'value'
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
        if field in ("AND", "OR", "NOT", "IN", "IS", "NULL", "LIKE", "BETWEEN", "(", ")", ",") or field in _COMPARISON_OPS:
            raise _ParseError(f"expected_field_got_{field!r}")
        op = self._consume()
        # v4.00.69 — Special-case IN(list-of-literals).
        if op == "IN":
            return self._parse_in_list(field)
        # v4.00.84 — Special-case ``IS NULL`` / ``IS NOT NULL``.
        if op == "IS":
            return self._parse_is_null(field)
        # v4.00.85 — Special-case ``LIKE 'pattern'``.
        if op == "LIKE":
            return self._parse_like(field)
        # v4.00.91 W1 Pillar D4 — Special-case ``BETWEEN 'lo' AND 'hi'``.
        if op == "BETWEEN":
            return self._parse_between(field)
        if op not in _COMPARISON_OPS:
            raise _ParseError(f"expected_comparison_op_got_{op!r}")
        # v4.00.91 W1 Pillar D5 — Mixed-context NULL shorthand. Operators
        # using SQL-style ``field=NULL`` / ``field!=NULL`` (bareword NULL,
        # not the quoted literal ``'NULL'``) get rewritten to the canonical
        # IS NULL / IS NOT NULL predicate. This matches both `None` rows
        # AND empty-string rows (same semantics as v4.00.84 IS NULL).
        # The string literal ``'NULL'`` (quoted) keeps its old behavior:
        # it matches a row whose value is the literal text "NULL".
        if self._peek() == "NULL" and op in ("=", "!="):
            self._consume()
            if op == "=":
                def is_null_eq(row: dict, field=field) -> bool:
                    v = row.get(field)
                    return v is None or v == ""
                return is_null_eq
            def is_not_null_neq(row: dict, field=field) -> bool:
                v = row.get(field)
                return not (v is None or v == "")
            return is_not_null_neq
        lit_tok = self._consume()
        if not (lit_tok.startswith("'") and lit_tok.endswith("'")):
            raise _ParseError(f"expected_quoted_literal_got_{lit_tok!r}")
        lit = _unquote_literal(lit_tok)
        return _make_pred(field, op, lit)

    def _parse_like(self, field: str) -> Callable[[dict], bool]:
        """v4.00.85 — Parse ``LIKE 'pattern'`` after the field token.

        Tokens already consumed: field, 'LIKE'. Now expect a single-
        quoted literal containing the LIKE pattern. An unquoted /
        missing literal raises so the outer ``parse_filter`` falls back
        to the always-True callable (fail-safe).
        """
        if self._at_end():
            raise _ParseError("expected_quoted_literal_after_LIKE")
        lit_tok = self._consume()
        if not (lit_tok.startswith("'") and lit_tok.endswith("'")):
            raise _ParseError(
                f"expected_quoted_literal_after_LIKE_got_{lit_tok!r}"
            )
        pattern = _unquote_literal(lit_tok)
        return _make_like_pred(field, pattern)

    def _parse_between(self, field: str) -> Callable[[dict], bool]:
        """v4.00.91 W1 Pillar D4 — Parse ``BETWEEN 'lo' AND 'hi'`` after the field.

        Tokens already consumed: field, 'BETWEEN'. Now expect:
          quoted-literal 'AND' quoted-literal

        Range is inclusive on both ends (matches SQL semantics). Numeric
        comparison is tried first (so ``score BETWEEN '70' AND '90'`` works
        on int score columns); falls back to string comparison if either
        bound is non-numeric. NULL/empty field values are excluded from
        the range (consistent with v4.00.84 IS NULL semantics — NULL is
        neither in any range nor out of any range, defaults to "excluded").
        """
        if self._at_end():
            raise _ParseError("expected_quoted_literal_after_BETWEEN")
        lo_tok = self._consume()
        if not (lo_tok.startswith("'") and lo_tok.endswith("'")):
            raise _ParseError(f"expected_quoted_literal_after_BETWEEN_got_{lo_tok!r}")
        if self._peek() != "AND":
            raise _ParseError(f"expected_AND_after_BETWEEN_lo_got_{self._peek()!r}")
        self._consume()
        if self._at_end():
            raise _ParseError("expected_quoted_literal_after_BETWEEN_AND")
        hi_tok = self._consume()
        if not (hi_tok.startswith("'") and hi_tok.endswith("'")):
            raise _ParseError(f"expected_quoted_literal_after_BETWEEN_AND_got_{hi_tok!r}")
        lo = _unquote_literal(lo_tok)
        hi = _unquote_literal(hi_tok)
        def between(row: dict, field=field, lo=lo, hi=hi) -> bool:
            v = row.get(field)
            if v is None or v == "":
                return False
            ok_row, num_row = _try_float(v)
            ok_lo, num_lo = _try_float(lo)
            ok_hi, num_hi = _try_float(hi)
            if ok_row and ok_lo and ok_hi:
                return num_lo <= num_row <= num_hi
            sv = str(v)
            return lo <= sv <= hi
        return between

    def _parse_is_null(self, field: str) -> Callable[[dict], bool]:
        """v4.00.84 — Parse ``IS NULL`` or ``IS NOT NULL`` after the field token.

        Per IMS Roster Service spec § 4.13, NULL is equivalent to both
        Python ``None`` AND the empty string ``""`` — absent and explicitly
        cleared values are treated identically.

        Tokens already consumed: field, 'IS'. Now expect either:
          - 'NULL'                  -> truthy when row is null/empty
          - 'NOT' 'NULL'            -> complement
        """
        nxt = self._peek()
        if nxt == "NULL":
            self._consume()
            def is_null(row: dict, field=field) -> bool:
                v = row.get(field)
                return v is None or v == ""
            return is_null
        if nxt == "NOT":
            self._consume()
            if self._peek() != "NULL":
                raise _ParseError(
                    f"expected_NULL_after_IS_NOT_got_{self._peek()!r}"
                )
            self._consume()
            def is_not_null(row: dict, field=field) -> bool:
                v = row.get(field)
                return not (v is None or v == "")
            return is_not_null
        raise _ParseError(f"expected_NULL_or_NOT_after_IS_got_{nxt!r}")

    def _parse_in_list(self, field: str) -> Callable[[dict], bool]:
        """v4.00.69 — Parse `IN('a','b','c')` -> set-membership predicate.

        Empty list `IN()` is allowed and always-False (set with no members).
        Tokens consumed: '(' literal (',' literal)* ')'.
        """
        if self._peek() != "(":
            raise _ParseError(f"expected_open_paren_after_IN_got_{self._peek()!r}")
        self._consume()  # eat '('
        lits: list[str] = []
        # Handle empty `IN()` shortcut.
        if self._peek() == ")":
            self._consume()
            return lambda _row: False
        while True:
            tok = self._consume()
            if not (tok.startswith("'") and tok.endswith("'")):
                raise _ParseError(f"expected_quoted_literal_in_IN_list_got_{tok!r}")
            lits.append(_unquote_literal(tok))
            nxt = self._peek()
            if nxt == ",":
                self._consume()
                continue
            if nxt == ")":
                self._consume()
                break
            raise _ParseError(f"expected_comma_or_close_paren_got_{nxt!r}")
        lit_set = frozenset(lits)
        def pred(row: dict, field=field, lit_set=lit_set) -> bool:
            return str(row.get(field) or "") in lit_set
        return pred


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
