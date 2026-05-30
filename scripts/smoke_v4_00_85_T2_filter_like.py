"""v4.00.85 Wave 17 Target 2 — OneRoster ?filter= ``LIKE 'pattern'`` smoke.

Surface under test (apps/api/oneroster_filter.py):

  predicate ::= field comparison_op literal
              | field 'IS' 'NULL'
              | field 'IS' 'NOT' 'NULL'
              | field 'IN' '(' literal_list ')'
              | field 'LIKE' literal           <-- v4.00.85

Per IMS Roster Service spec § 4.13, ``LIKE`` is a case-INSENSITIVE
pattern match. The pattern supports two wildcards:

  - ``%`` zero-or-more chars
  - ``_`` single char

Other characters are matched literally (regex specials escaped at
compile time). The compiled regex is anchored on BOTH ends so partial
matches fall through (use ``%`` explicitly to allow surrounding chars).

Fail-safe contract is preserved: bad shapes (``LIKE`` with no literal,
``LIKE 123`` unquoted) fall back to the always-True callable.

Cases covered (10):
  1. ``email LIKE '%@school.edu'`` matches "alice@school.edu" but not gmail
  2. ``email LIKE 'alice_@school.edu'`` matches "alice1@school.edu" (1 char)
     but rejects "alice@school.edu" (missing char) + "alicemarie@..."
  3. Case-insensitive: ``LIKE '%@SCHOOL.EDU'`` matches "alice@school.edu"
  4. Combined: ``role = 'student' AND email LIKE '%@school.edu'``
  5. NOT wrap: ``NOT (email LIKE '%@gmail.com')``
  6. Combined w/ IS NULL: ``email LIKE '%@school.edu' OR email IS NULL``
  7. Bad shape: ``email LIKE`` -> always-True (fail-safe)
  8. Bad shape: ``email LIKE 123`` (unquoted) -> always-True (fail-safe)
  9. Literal % inside pattern: ``discount LIKE '%50%'`` matches "50% off"
 10. Pre-existing IN()/IS NULL/=/!= still work (back-compat)
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
# Case 1 — ``email LIKE '%@school.edu'`` suffix-match.
# ----------------------------------------------------------------------
p1 = parse_filter("email LIKE '%@school.edu'")
_check("1a LIKE %@school.edu matches alice@school.edu",
       p1({"email": "alice@school.edu"}) is True)
_check("1b LIKE %@school.edu matches bob.smith@school.edu",
       p1({"email": "bob.smith@school.edu"}) is True)
_check("1c LIKE %@school.edu rejects alice@gmail.com",
       p1({"email": "alice@gmail.com"}) is False)
_check("1d LIKE %@school.edu rejects empty email",
       p1({"email": ""}) is False)

# ----------------------------------------------------------------------
# Case 2 — ``LIKE 'alice_@school.edu'`` single-char wildcard.
# ----------------------------------------------------------------------
p2 = parse_filter("email LIKE 'alice_@school.edu'")
_check("2a single-_ matches alice1@school.edu",
       p2({"email": "alice1@school.edu"}) is True)
_check("2b single-_ matches aliceX@school.edu",
       p2({"email": "aliceX@school.edu"}) is True)
_check("2c single-_ rejects alice@school.edu (1 char missing)",
       p2({"email": "alice@school.edu"}) is False)
_check("2d single-_ rejects alicemarie@school.edu (too many)",
       p2({"email": "alicemarie@school.edu"}) is False)

# ----------------------------------------------------------------------
# Case 3 — Case-insensitive matching.
# ----------------------------------------------------------------------
p3 = parse_filter("email LIKE '%@SCHOOL.EDU'")
_check("3a ci LIKE matches alice@school.edu",
       p3({"email": "alice@school.edu"}) is True)
_check("3b ci LIKE matches ALICE@SCHOOL.EDU",
       p3({"email": "ALICE@SCHOOL.EDU"}) is True)
_check("3c ci LIKE rejects alice@gmail.com",
       p3({"email": "alice@gmail.com"}) is False)

# ----------------------------------------------------------------------
# Case 4 — Combined: ``role = 'student' AND email LIKE '%@school.edu'``.
# ----------------------------------------------------------------------
p4 = parse_filter("role = 'student' AND email LIKE '%@school.edu'")
_check("4a student+school-email -> True",
       p4({"role": "student", "email": "alice@school.edu"}) is True)
_check("4b teacher+school-email -> False",
       p4({"role": "teacher", "email": "alice@school.edu"}) is False)
_check("4c student+gmail -> False",
       p4({"role": "student", "email": "alice@gmail.com"}) is False)

# ----------------------------------------------------------------------
# Case 5 — NOT wrap: ``NOT (email LIKE '%@gmail.com')``.
# ----------------------------------------------------------------------
p5 = parse_filter("NOT (email LIKE '%@gmail.com')")
_check("5a NOT(LIKE gmail) rejects alice@gmail.com",
       p5({"email": "alice@gmail.com"}) is False)
_check("5b NOT(LIKE gmail) accepts alice@school.edu",
       p5({"email": "alice@school.edu"}) is True)
_check("5c NOT(LIKE gmail) accepts empty email",
       p5({"email": ""}) is True)

# ----------------------------------------------------------------------
# Case 6 — Combined with IS NULL: ``email LIKE '%@school.edu' OR email IS NULL``.
# ----------------------------------------------------------------------
p6 = parse_filter("email LIKE '%@school.edu' OR email IS NULL")
_check("6a LIKE-match arm",
       p6({"email": "alice@school.edu"}) is True)
_check("6b IS-NULL arm (None)",
       p6({"email": None}) is True)
_check("6c IS-NULL arm (empty str)",
       p6({"email": ""}) is True)
_check("6d neither arm: gmail",
       p6({"email": "alice@gmail.com"}) is False)

# ----------------------------------------------------------------------
# Case 7 — Bad shape: ``email LIKE`` (no literal). Fail-safe -> always-True.
# ----------------------------------------------------------------------
p7 = parse_filter("email LIKE")
_check("7a bad-shape 'LIKE' -> always-True for set-val",
       p7({"email": "alice@school.edu"}) is True)
_check("7b bad-shape 'LIKE' -> always-True for None",
       p7({"email": None}) is True)
_check("7c bad-shape 'LIKE' -> always-True for empty row",
       p7({}) is True)

# ----------------------------------------------------------------------
# Case 8 — Bad shape: ``email LIKE 123`` (unquoted literal).
# ----------------------------------------------------------------------
p8 = parse_filter("email LIKE 123")
_check("8a unquoted-literal 'LIKE 123' -> always-True for set-val",
       p8({"email": "alice@school.edu"}) is True)
_check("8b unquoted-literal 'LIKE 123' -> always-True for None",
       p8({"email": None}) is True)

# ----------------------------------------------------------------------
# Case 9 — Literal '%' inside pattern: ``discount LIKE '%50%'`` matches "50% off".
# The leading '%' is wildcard (zero-or-more), so anything containing "50"
# followed by anything matches — including the literal "50% off".
# ----------------------------------------------------------------------
p9 = parse_filter("discount LIKE '%50%'")
_check("9a '%50%' matches '50% off' (contains 50)",
       p9({"discount": "50% off"}) is True)
_check("9b '%50%' matches 'now 50 percent'",
       p9({"discount": "now 50 percent"}) is True)
_check("9c '%50%' matches bare '50'",
       p9({"discount": "50"}) is True)
_check("9d '%50%' rejects '25 only'",
       p9({"discount": "25 only"}) is False)

# Verify that regex specials in the LIKE pattern are escaped: a '.' in
# the pattern matches a literal dot, NOT any char.
p9e = parse_filter("host LIKE 'a.b'")
_check("9e LIKE 'a.b' matches literal 'a.b'",
       p9e({"host": "a.b"}) is True)
_check("9f LIKE 'a.b' rejects 'aXb' (dot is literal)",
       p9e({"host": "aXb"}) is False)

# ----------------------------------------------------------------------
# Case 10 — Pre-existing ops still work (back-compat).
# ----------------------------------------------------------------------
p10a = parse_filter("role = 'student'")
_check("10a = op still works",
       p10a({"role": "student"}) is True and p10a({"role": "teacher"}) is False)

p10b = parse_filter("role != 'student'")
_check("10b != op still works",
       p10b({"role": "teacher"}) is True and p10b({"role": "student"}) is False)

p10c = parse_filter("gradeLevels IN ('09','10')")
_check("10c IN() still works",
       p10c({"gradeLevels": "09"}) is True
       and p10c({"gradeLevels": "11"}) is False)

p10d = parse_filter("gradeLevels IN ()")
_check("10d empty IN() still fail-safe always-False",
       p10d({"gradeLevels": "09"}) is False)

p10e = parse_filter("middleName IS NULL")
_check("10e IS NULL still works",
       p10e({"middleName": None}) is True
       and p10e({"middleName": "Marie"}) is False)

p10f = parse_filter("middleName IS NOT NULL")
_check("10f IS NOT NULL still works",
       p10f({"middleName": "Marie"}) is True
       and p10f({"middleName": None}) is False)

p10g = parse_filter("NOT role = 'teacher'")
_check("10g NOT still works",
       p10g({"role": "student"}) is True and p10g({"role": "teacher"}) is False)

p10h = parse_filter("role = 'student' AND grade = '09'")
_check("10h AND still works",
       p10h({"role": "student", "grade": "09"}) is True
       and p10h({"role": "student", "grade": "10"}) is False)

p10i = parse_filter("role = 'student' OR role = 'teacher'")
_check("10i OR still works",
       p10i({"role": "student"}) is True
       and p10i({"role": "teacher"}) is True
       and p10i({"role": "admin"}) is False)

p10j = parse_filter("(role = 'student' OR role = 'teacher') AND grade = '09'")
_check("10j paren nesting still works",
       p10j({"role": "student", "grade": "09"}) is True
       and p10j({"role": "admin", "grade": "09"}) is False)

# ----------------------------------------------------------------------
# Tally.
# ----------------------------------------------------------------------
print()
print(f"=== v4.00.85 T2 filter LIKE smoke: {_passed} passed, {_failed} failed ===")
sys.exit(0 if _failed == 0 else 1)
