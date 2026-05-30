"""v4.00.88 Wave 20 (FINAL) Targets 2 + 3 smoke.

T2 — Demographics complete v1.2 field set
  * englishLearnerStatus            (enum: yes/no/exited)
  * economicallyDisadvantagedStatus (enum: yes/no/declined-to-state)
  * familySituation                  (free text, 256 cap, control-char reject)

T3 — OneRoster Result Service full-coverage hardening
  Wire ?fields= mask + ?sort=/?orderBy= into the three Wave 11/12/13
  Result-Service list endpoints (categories_list_v1p2_roster,
  results_list_v1p2_roster, score_scales_list_v1p2_roster), reusing the
  v4.00.64 _apply_fields_mask + v4.00.65 _apply_sort helpers shipped in
  oneroster_demographics.
"""
import os
import sys

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

# Make this script runnable from anywhere (path of project root).
_HERE = os.path.dirname(os.path.abspath(__file__))
_PROJECT_ROOT = os.path.dirname(_HERE)
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

import django  # noqa: E402

django.setup()

import json  # noqa: E402

from django.http import JsonResponse  # noqa: E402
from django.test import RequestFactory  # noqa: E402

from apps.api import oneroster_demographics, oneroster_results  # noqa: E402


_RESULTS: list[tuple[str, bool, str]] = []


def _check(name: str, ok: bool, note: str = "") -> None:
    _RESULTS.append((name, ok, note))
    flag = "PASS" if ok else "FAIL"
    print(f"  [{flag}] {name}{(' - ' + note) if note else ''}")


def _bearer(req):
    req.META["HTTP_AUTHORIZATION"] = "Bearer smoke-bearer"
    req._dont_enforce_csrf_checks = True
    return req


# =============================================================================
# T2 — Demographics v1.2 field-set completion
# =============================================================================

print("=== v4.00.88 T2 — demographics v1.2 completion ===")

# Case 1: englishLearnerStatus="yes" -> None (accept).
r = oneroster_demographics._validate_english_learner_status({"englishLearnerStatus": "yes"})
_check("01 englishLearnerStatus=yes accepts", r is None, f"r={r!r}")

# Case 1b: bonus — "no" + "exited" also accept (full vocab smoke).
r_no = oneroster_demographics._validate_english_learner_status({"englishLearnerStatus": "no"})
r_ex = oneroster_demographics._validate_english_learner_status({"englishLearnerStatus": "exited"})
_check("01b englishLearnerStatus full vocab accepts",
       r_no is None and r_ex is None,
       f"no={r_no!r} exited={r_ex!r}")

# Case 2: englishLearnerStatus invalid -> 400 value_not_in_vocab.
r = oneroster_demographics._validate_english_learner_status({"englishLearnerStatus": "maybe"})
ok2 = isinstance(r, JsonResponse) and r.status_code == 400
body = json.loads(r.content) if isinstance(r, JsonResponse) else {}
ok2 = ok2 and body.get("error") == "bad_english_learner_status" and body.get("reason") == "value_not_in_vocab"
_check("02 englishLearnerStatus invalid -> 400 value_not_in_vocab",
       ok2, f"status={r.status_code if isinstance(r, JsonResponse) else None} body={body!r}")

# Case 3: economicallyDisadvantagedStatus="declined-to-state" -> None.
r = oneroster_demographics._validate_economically_disadvantaged_status(
    {"economicallyDisadvantagedStatus": "declined-to-state"})
_check("03 economicallyDisadvantaged=declined-to-state accepts", r is None, f"r={r!r}")

# Case 3b: invalid economically disadvantaged -> 400.
r = oneroster_demographics._validate_economically_disadvantaged_status(
    {"economicallyDisadvantagedStatus": "rich"})
ok3b = isinstance(r, JsonResponse) and r.status_code == 400
body = json.loads(r.content) if isinstance(r, JsonResponse) else {}
ok3b = ok3b and body.get("error") == "bad_economically_disadvantaged_status"
_check("03b economicallyDisadvantaged invalid -> 400",
       ok3b, f"body={body!r}")

# Case 4: familySituation exactly 256 chars -> None (boundary).
r = oneroster_demographics._validate_family_situation({"familySituation": "X" * 256})
_check("04 familySituation 256 chars accepts", r is None, f"r={r!r}")

# Case 5: familySituation 257 chars -> 400 too_long.
r = oneroster_demographics._validate_family_situation({"familySituation": "X" * 257})
ok5 = isinstance(r, JsonResponse) and r.status_code == 400
body = json.loads(r.content) if isinstance(r, JsonResponse) else {}
ok5 = ok5 and body.get("error") == "bad_family_situation" and body.get("reason") == "too_long"
_check("05 familySituation 257 chars -> 400 too_long",
       ok5, f"body={body!r}")

# Case 6: familySituation w/ control char -> 400 control_chars.
r = oneroster_demographics._validate_family_situation({"familySituation": "a\x07b"})
ok6 = isinstance(r, JsonResponse) and r.status_code == 400
body = json.loads(r.content) if isinstance(r, JsonResponse) else {}
ok6 = ok6 and body.get("error") == "bad_family_situation" and body.get("reason") == "control_chars"
_check("06 familySituation control-char -> 400 control_chars",
       ok6, f"body={body!r}")

# Case 6b: empty familySituation -> None (explicit clear).
r = oneroster_demographics._validate_family_situation({"familySituation": ""})
_check("06b familySituation empty (explicit clear) accepts", r is None, f"r={r!r}")

# Case 7: override-ring routing — all 3 fields registered in _DEMOGRAPHIC_OVERRIDE_FIELDS.
or_fields = oneroster_demographics._DEMOGRAPHIC_OVERRIDE_FIELDS
ok7 = (
    "englishLearnerStatus" in or_fields
    and "economicallyDisadvantagedStatus" in or_fields
    and "familySituation" in or_fields
)
_check("07 all 3 fields in _DEMOGRAPHIC_OVERRIDE_FIELDS",
       ok7,
       f"els={'englishLearnerStatus' in or_fields} "
       f"eds={'economicallyDisadvantagedStatus' in or_fields} "
       f"fs={'familySituation' in or_fields}")

# Case 7b: chain integration via _parse_demographic_payload — JSON body with all
# three fields valid round-trips through the chain (no 400).
body_bytes = json.dumps({"demographic": {
    "englishLearnerStatus": "yes",
    "economicallyDisadvantagedStatus": "no",
    "familySituation": "Lives with both parents.",
}}).encode("utf-8")
inner, err = oneroster_demographics._parse_demographic_payload(body_bytes)
_check("07b chain integration — happy path returns inner + err=None",
       inner is not None and err is None,
       f"inner_keys={sorted(inner.keys()) if inner else None} err={err!r}")

# Case 7c: chain integration — bad englishLearnerStatus surfaces 400 at chain level.
body_bytes = json.dumps({"demographic": {"englishLearnerStatus": "bogus"}}).encode("utf-8")
inner, err = oneroster_demographics._parse_demographic_payload(body_bytes)
ok7c = inner is None and isinstance(err, JsonResponse) and err.status_code == 400
body = json.loads(err.content) if isinstance(err, JsonResponse) else {}
ok7c = ok7c and body.get("error") == "bad_english_learner_status"
_check("07c chain integration — bad englishLearnerStatus -> 400 at chain",
       ok7c, f"body={body!r}")


# =============================================================================
# T3 — OneRoster Result Service fields-mask + sort wiring
# =============================================================================

print("\n=== v4.00.88 T3 — Result Service ?fields= + ?sort= + ?orderBy= ===")

rf = RequestFactory()


def _get(path: str, view):
    req = _bearer(rf.get(path))
    resp = view(req)
    return resp, json.loads(resp.content) if resp.status_code == 200 else {}


# Case 8: /categories/?sort=title&orderBy=desc -> 200 + reverse-sorted.
resp, body = _get(
    "/api/roster/v1p2/categories/?sort=title&orderBy=desc",
    oneroster_results.categories_list_v1p2_roster,
)
titles = [c.get("title") or "" for c in body.get("categories") or []]
ok8 = (
    resp.status_code == 200
    and len(titles) >= 2
    and titles == sorted(titles, reverse=True)
)
_check("08 /categories/?sort=title&orderBy=desc reverse-sorted",
       ok8,
       f"status={resp.status_code} count={len(titles)} first3={titles[:3]} expected_first3={sorted(titles, reverse=True)[:3]}")

# Case 9: /categories/?fields=sourcedId,title -> 200 + each row has ONLY
# sourcedId+title.
resp, body = _get(
    "/api/roster/v1p2/categories/?fields=sourcedId,title",
    oneroster_results.categories_list_v1p2_roster,
)
rows = body.get("categories") or []
ok9 = (
    resp.status_code == 200
    and len(rows) >= 1
    and all(set(r.keys()) == {"sourcedId", "title"} for r in rows)
)
sample_keys = sorted(rows[0].keys()) if rows else []
_check("09 /categories/?fields=sourcedId,title each result has ONLY sourcedId+title",
       ok9,
       f"status={resp.status_code} count={len(rows)} sample_keys={sample_keys}")

# Case 10: combined ?sort=title&orderBy=asc&fields=sourcedId&limit=2 -> 200 +
# sorted + masked + 2 entries.
resp, body = _get(
    "/api/roster/v1p2/categories/?sort=title&orderBy=asc&fields=sourcedId&limit=2",
    oneroster_results.categories_list_v1p2_roster,
)
rows = body.get("categories") or []
ok10 = (
    resp.status_code == 200
    and len(rows) == 2
    and all(set(r.keys()) == {"sourcedId"} for r in rows)
)
# We can't verify sort over a 2-row sample, but X-Total-Count should reflect
# the pre-mask, pre-limit count (>= 2).
total_str = resp.headers.get("X-Total-Count", "0")
ok10 = ok10 and total_str.isdigit() and int(total_str) >= 2
_check("10 /categories/?sort=title&orderBy=asc&fields=sourcedId&limit=2",
       ok10,
       f"status={resp.status_code} rows={len(rows)} sample_keys={sorted(rows[0].keys()) if rows else []} X-Total-Count={total_str}")

# Case 11a: /results/?sort=dateLastModified&orderBy=desc -> 200.
resp, body = _get(
    "/api/roster/v1p2/results/?sort=dateLastModified&orderBy=desc",
    oneroster_results.results_list_v1p2_roster,
)
ok11a = resp.status_code == 200 and "results" in body
_check("11a /results/?sort=dateLastModified&orderBy=desc -> 200",
       ok11a, f"status={resp.status_code} keys={sorted(body.keys()) if body else []}")

# Case 11b: /results/?fields=sourcedId -> 200, rows have ONLY sourcedId
# (empty rows if no Evaluation seed; we just check shape applies when present).
resp, body = _get(
    "/api/roster/v1p2/results/?fields=sourcedId",
    oneroster_results.results_list_v1p2_roster,
)
rows = body.get("results") or []
ok11b = (
    resp.status_code == 200
    and (len(rows) == 0 or all(set(r.keys()) == {"sourcedId"} for r in rows))
)
sample_keys = sorted(rows[0].keys()) if rows else []
_check("11b /results/?fields=sourcedId rows have only sourcedId (or empty)",
       ok11b,
       f"status={resp.status_code} count={len(rows)} sample_keys={sample_keys}")

# Case 11c: /scoreScales/?sort=title&orderBy=desc -> 200 + reverse-sorted.
resp, body = _get(
    "/api/roster/v1p2/scoreScales/?sort=title&orderBy=desc",
    oneroster_results.score_scales_list_v1p2_roster,
)
titles = [s.get("title") or "" for s in body.get("scoreScales") or []]
ok11c = (
    resp.status_code == 200
    and len(titles) >= 2
    and titles == sorted(titles, reverse=True)
)
_check("11c /scoreScales/?sort=title&orderBy=desc reverse-sorted",
       ok11c,
       f"status={resp.status_code} count={len(titles)} first3={titles[:3]} expected_first3={sorted(titles, reverse=True)[:3]}")

# Case 11d: /scoreScales/?fields=sourcedId,title rows ONLY have sourcedId+title.
resp, body = _get(
    "/api/roster/v1p2/scoreScales/?fields=sourcedId,title",
    oneroster_results.score_scales_list_v1p2_roster,
)
rows = body.get("scoreScales") or []
ok11d = (
    resp.status_code == 200
    and len(rows) >= 1
    and all(set(r.keys()) == {"sourcedId", "title"} for r in rows)
)
sample_keys = sorted(rows[0].keys()) if rows else []
_check("11d /scoreScales/?fields=sourcedId,title rows have only sourcedId+title",
       ok11d,
       f"status={resp.status_code} count={len(rows)} sample_keys={sample_keys}")

# Case 11e: /scoreScales/?sort=title&orderBy=asc&fields=sourcedId&limit=2.
resp, body = _get(
    "/api/roster/v1p2/scoreScales/?sort=title&orderBy=asc&fields=sourcedId&limit=2",
    oneroster_results.score_scales_list_v1p2_roster,
)
rows = body.get("scoreScales") or []
ok11e = (
    resp.status_code == 200
    and len(rows) == 2
    and all(set(r.keys()) == {"sourcedId"} for r in rows)
)
total_str = resp.headers.get("X-Total-Count", "0")
ok11e = ok11e and total_str.isdigit() and int(total_str) >= 2
_check("11e /scoreScales/ combined sort+orderBy+fields+limit=2",
       ok11e,
       f"status={resp.status_code} rows={len(rows)} sample_keys={sorted(rows[0].keys()) if rows else []} X-Total-Count={total_str}")

# Case 11f: regression — no params still returns full records on /scoreScales/.
resp, body = _get(
    "/api/roster/v1p2/scoreScales/",
    oneroster_results.score_scales_list_v1p2_roster,
)
rows = body.get("scoreScales") or []
ok11f = (
    resp.status_code == 200
    and len(rows) >= 4
    and all({"sourcedId", "title", "type", "scoreValues"}.issubset(set(r.keys())) for r in rows)
)
_check("11f /scoreScales/ no params returns full records (regression)",
       ok11f,
       f"status={resp.status_code} count={len(rows)} first_keys={sorted(rows[0].keys()) if rows else []}")


# =============================================================================
# Tally.
# =============================================================================

passed = sum(1 for _, ok, _ in _RESULTS if ok)
total = len(_RESULTS)
print()
print(f"=== RESULT: {passed}/{total} cases green ===")
sys.exit(0 if passed == total else 1)
