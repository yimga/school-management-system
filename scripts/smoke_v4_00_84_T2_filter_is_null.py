"""v4.00.84 Wave 16 Target 2 — OneRoster ?filter= ``IS NULL`` / ``IS NOT NULL`` smoke.

Surface under test (apps/api/oneroster_filter.py):

  predicate ::= field comparison_op literal
              | field 'IS' 'NULL'
              | field 'IS' 'NOT' 'NULL'
              | field 'IN' '(' literal_list ')'

Per IMS Roster Service spec § 4.13, a field is NULL when it is either
Python ``None`` OR the empty string ``""`` (absent + cleared are
equivalent). Keywords IS/NULL/NOT are matched case-insensitively at the
tokenizer (parser dispatches on the canonical UPPER form).

Fail-safe contract is preserved: bad shapes (``field IS`` /
``field IS NOT``) fall back to the always-True callable rather than
raising.

Cases covered (10):
  1. ``middleName IS NULL`` matches None / "" / missing key, rejects "Marie"
  2. ``middleName IS NOT NULL`` is the strict complement
  3. AND-combine: ``country = 'US' AND middleName IS NULL``
  4. OR-combine:  ``country = 'US' OR middleName IS NOT NULL``
  5. NOT-wrap:    ``NOT (middleName IS NULL)`` == ``IS NOT NULL``
  6. Paren-wrap:  ``(role = 'student' AND middleName IS NULL)``
  7. Bad shape:   ``middleName IS`` -> always-True (fail-safe)
  8. Bad shape:   ``middleName IS NOT`` -> always-True (fail-safe)
  9. Back-compat: v4.00.66+ expressions still parse (``role = 'student'``,
     ``gradeLevels IN ('09','10')``, NOT, AND, OR)
 10. Case-insensitive: ``middleName is null`` parses identically
"""
import os
import sys

# Make this script runnable from anywhere (path of project root).
_HERE = os.path.dirname(os.path.abspath(__file__))
_PROJECT_ROOT = os.path.dirname(_HERE)
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from apps.api.oneroster_filter import parse_filter  # noqa: E402


_passed = 0
_failed = 0


def _check(label: str, ok: bool, detail: str = "") -> None:
    global _passed, _failed
    if ok:
        _passed += 1
        print(f"OK   {label}")
    else:
        _failed += 1
        print(f"FAIL {label} :: {detail}")


# ----------------------------------------------------------------------
# Case 1 — `middleName IS NULL` matches None / "" / missing key, rejects value.
# ----------------------------------------------------------------------
p1 = parse_filter("middleName IS NULL")
_check("1a IS NULL matches {'middleName': None}", p1({"middleName": None}) is True)
_check("1b IS NULL matches {'middleName': ''}",  p1({"middleName": ""}) is True)
_check("1c IS NULL matches {} (missing key)",    p1({}) is True)
_check("1d IS NULL rejects {'middleName': 'Marie'}",
       p1({"middleName": "Marie"}) is False)

# ----------------------------------------------------------------------
# Case 2 — `middleName IS NOT NULL` is the complement.
# ----------------------------------------------------------------------
p2 = parse_filter("middleName IS NOT NULL")
_check("2a IS NOT NULL rejects {'middleName': None}",
       p2({"middleName": None}) is False)
_check("2b IS NOT NULL rejects {'middleName': ''}",
       p2({"middleName": ""}) is False)
_check("2c IS NOT NULL rejects {} (missing key)",
       p2({}) is False)
_check("2d IS NOT NULL matches {'middleName': 'Marie'}",
       p2({"middleName": "Marie"}) is True)

# ----------------------------------------------------------------------
# Case 3 — AND-combined: `country = 'US' AND middleName IS NULL`.
# ----------------------------------------------------------------------
p3 = parse_filter("country = 'US' AND middleName IS NULL")
_check("3a both-conds-met",
       p3({"country": "US", "middleName": None}) is True)
_check("3b country-mismatch",
       p3({"country": "DE", "middleName": None}) is False)
_check("3c middleName-set",
       p3({"country": "US", "middleName": "Marie"}) is False)
_check("3d both-fail",
       p3({"country": "DE", "middleName": "Marie"}) is False)

# ----------------------------------------------------------------------
# Case 4 — OR-combined: `country = 'US' OR middleName IS NOT NULL`.
# ----------------------------------------------------------------------
p4 = parse_filter("country = 'US' OR middleName IS NOT NULL")
_check("4a country-match-only",
       p4({"country": "US", "middleName": None}) is True)
_check("4b middlename-match-only",
       p4({"country": "DE", "middleName": "Marie"}) is True)
_check("4c neither",
       p4({"country": "DE", "middleName": None}) is False)
_check("4d both",
       p4({"country": "US", "middleName": "Marie"}) is True)

# ----------------------------------------------------------------------
# Case 5 — NOT wrap: `NOT (middleName IS NULL)` == `IS NOT NULL`.
# ----------------------------------------------------------------------
p5 = parse_filter("NOT (middleName IS NULL)")
_check("5a NOT(IS NULL) rejects None", p5({"middleName": None}) is False)
_check("5b NOT(IS NULL) rejects ''",   p5({"middleName": ""}) is False)
_check("5c NOT(IS NULL) accepts 'Marie'",
       p5({"middleName": "Marie"}) is True)

# ----------------------------------------------------------------------
# Case 6 — Paren: `(role = 'student' AND middleName IS NULL)`.
# ----------------------------------------------------------------------
p6 = parse_filter("(role = 'student' AND middleName IS NULL)")
_check("6a student+nullmid",
       p6({"role": "student", "middleName": None}) is True)
_check("6b student+set-mid",
       p6({"role": "student", "middleName": "Marie"}) is False)
_check("6c teacher+nullmid",
       p6({"role": "teacher", "middleName": None}) is False)

# ----------------------------------------------------------------------
# Case 7 — Bad shape: `middleName IS` (no following NULL/NOT).
# Fail-safe -> always-True callable.
# ----------------------------------------------------------------------
p7 = parse_filter("middleName IS")
_check("7a bad-shape 'IS' -> always-True for set-val",
       p7({"middleName": "Marie"}) is True)
_check("7b bad-shape 'IS' -> always-True for null-val",
       p7({"middleName": None}) is True)
_check("7c bad-shape 'IS' -> always-True for empty-row",
       p7({}) is True)

# ----------------------------------------------------------------------
# Case 8 — Bad shape: `middleName IS NOT` (no following NULL).
# ----------------------------------------------------------------------
p8 = parse_filter("middleName IS NOT")
_check("8a bad-shape 'IS NOT' -> always-True for set-val",
       p8({"middleName": "Marie"}) is True)
_check("8b bad-shape 'IS NOT' -> always-True for null-val",
       p8({"middleName": None}) is True)

# ----------------------------------------------------------------------
# Case 9 — Back-compat: existing v4.00.66+ expressions must still parse.
# ----------------------------------------------------------------------
p9a = parse_filter("role = 'student'")
_check("9a v4.00.66 = op",
       p9a({"role": "student"}) is True and p9a({"role": "teacher"}) is False)

p9b = parse_filter("gradeLevels IN ('09','10')")
_check("9b v4.00.69 IN op",
       p9b({"gradeLevels": "09"}) is True
       and p9b({"gradeLevels": "10"}) is True
       and p9b({"gradeLevels": "11"}) is False)

p9c = parse_filter("NOT role = 'teacher'")
_check("9c v4.00.68 NOT op",
       p9c({"role": "student"}) is True and p9c({"role": "teacher"}) is False)

p9d = parse_filter("role = 'student' AND grade = '09'")
_check("9d AND op",
       p9d({"role": "student", "grade": "09"}) is True
       and p9d({"role": "student", "grade": "10"}) is False)

p9e = parse_filter("role = 'student' OR role = 'teacher'")
_check("9e OR op",
       p9e({"role": "student"}) is True
       and p9e({"role": "teacher"}) is True
       and p9e({"role": "admin"}) is False)

p9f = parse_filter("(role = 'student' OR role = 'teacher') AND grade = '09'")
_check("9f paren nesting (v4.00.67)",
       p9f({"role": "student", "grade": "09"}) is True
       and p9f({"role": "admin", "grade": "09"}) is False
       and p9f({"role": "student", "grade": "10"}) is False)

# ----------------------------------------------------------------------
# Case 10 — Case-insensitive: `middleName is null`.
# ----------------------------------------------------------------------
p10a = parse_filter("middleName is null")
_check("10a lowercase 'is null' matches None",
       p10a({"middleName": None}) is True)
_check("10b lowercase 'is null' matches ''",
       p10a({"middleName": ""}) is True)
_check("10c lowercase 'is null' rejects 'Marie'",
       p10a({"middleName": "Marie"}) is False)

p10b = parse_filter("middleName is not null")
_check("10d lowercase 'is not null' rejects None",
       p10b({"middleName": None}) is False)
_check("10e lowercase 'is not null' matches 'Marie'",
       p10b({"middleName": "Marie"}) is True)

p10c = parse_filter("middleName Is Null")
_check("10f mixed-case 'Is Null' matches None",
       p10c({"middleName": None}) is True)

# ----------------------------------------------------------------------
# Tally.
# ----------------------------------------------------------------------
print()
print(f"=== v4.00.84 T2 filter IS NULL smoke: {_passed} passed, {_failed} failed ===")
sys.exit(0 if _failed == 0 else 1)
