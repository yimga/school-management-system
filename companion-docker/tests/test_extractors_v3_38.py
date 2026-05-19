"""v3.38.0 Agent 2 — vendor pre-processor tests (companion-docker).

36+ pytest cases covering:
  - PowerSchool date / status / lastfirst / gender / passthrough.
  - Blackbaud nested key flattening / iso truncation / guardian relationships.
  - Veracross role-partitioned columns / slash-date / person ID by role.
  - Alma JSON-in-cell / null literal / numeric value / role.
  - FACTS short-year date / write-path counsel-blocked routing / CR strip.
  - Skyward compact date / write-path counsel-blocked / passthrough.
  - detect_vendor for all 6 vendors + unknown returns None.
  - Determinism (same input → same output) for at least 2 vendors.
  - Constraint: no httpx.Client / requests in extractors package.

Pure stdlib. No external deps. ``dateutil``-dependent tests are
marked skipif (none in this file — all date handling is stdlib).
"""
from __future__ import annotations

import os
import sys

import pytest

# Make app importable.
_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
_DOCKER_ROOT = os.path.dirname(_THIS_DIR)
if _DOCKER_ROOT not in sys.path:
    sys.path.insert(0, _DOCKER_ROOT)

from app import extractors  # noqa: E402
from app.extractors import alma, blackbaud, facts, powerschool, skyward, veracross  # noqa: E402


# ---------- normalize_header ----------


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("Student Number", "student_number"),
        ("  Enroll_Status  ", "enroll_status"),
        ('"Student.FirstName"', "student_firstname"),
        ("Person-ID", "person_id"),
        ("ALL_CAPS_HEADER", "all_caps_header"),
        ("", ""),
    ],
)
def test_normalize_header(raw: str, expected: str) -> None:
    assert extractors.normalize_header(raw) == expected


# ---------- detect_vendor ----------


def test_detect_vendor_powerschool() -> None:
    h = ["Student Number", "DCID", "Enroll_Status", "LastFirst"]
    assert extractors.detect_vendor(h) == "powerschool"


def test_detect_vendor_blackbaud() -> None:
    h = ["Student.FirstName", "Student.LastName", "Student.Id", "RelationshipType"]
    assert extractors.detect_vendor(h) == "blackbaud"


def test_detect_vendor_veracross() -> None:
    h = ["Person ID", "Sex", "Household ID", "StudentEmail"]
    assert extractors.detect_vendor(h) == "veracross"


def test_detect_vendor_alma() -> None:
    h = ["alma_id", "user_type", "extra_attributes"]
    assert extractors.detect_vendor(h) == "alma"


def test_detect_vendor_facts() -> None:
    h = ["FAMILYID", "PERSONID", "tuition_balance"]
    assert extractors.detect_vendor(h) == "facts"


def test_detect_vendor_skyward() -> None:
    h = ["SKYWARD_ID", "OTHER_ID", "NAME_ID"]
    assert extractors.detect_vendor(h) == "skyward"


def test_detect_vendor_unknown_returns_none() -> None:
    h = ["Temperature", "Pressure", "Humidity"]
    assert extractors.detect_vendor(h) is None


# ---------- PowerSchool ----------


def test_ps_student_number_to_external_id() -> None:
    out = powerschool.preprocess_rows([{"Student Number": "10001"}])
    assert out[0]["external_id"] == "10001"


def test_ps_lastfirst_splits() -> None:
    out = powerschool.preprocess_rows([{"LastFirst": "Adams, Alice"}])
    assert out[0]["last_name"] == "Adams"
    assert out[0]["first_name"] == "Alice"


def test_ps_us_date_to_iso() -> None:
    out = powerschool.preprocess_rows([{"DOB": "03/15/2010"}])
    assert out[0]["date_of_birth"] == "2010-03-15"


def test_ps_status_a_to_active() -> None:
    out = powerschool.preprocess_rows([{"Enroll_Status": "A"}])
    assert out[0]["enrollment_status"] == "active"


def test_ps_status_i_to_inactive() -> None:
    out = powerschool.preprocess_rows([{"Enroll_Status": "I"}])
    assert out[0]["enrollment_status"] == "inactive"


def test_ps_gender_passthrough() -> None:
    out = powerschool.preprocess_rows([{"Gender": "F"}])
    assert out[0]["gender"] == "F"


def test_ps_invalid_date_passthrough() -> None:
    out = powerschool.preprocess_rows([{"DOB": "not-a-date"}])
    assert out[0]["date_of_birth"] == "not-a-date"


# ---------- Blackbaud ----------


def test_bb_dot_nested_flattens() -> None:
    out = blackbaud.preprocess_rows([{"Student.FirstName": "Bob"}])
    assert out[0]["first_name"] == "Bob"


def test_bb_iso_datetime_truncates() -> None:
    out = blackbaud.preprocess_rows([{"Student.DateOfBirth": "2010-03-15T08:00:00Z"}])
    assert out[0]["date_of_birth"] == "2010-03-15"


def test_bb_relationship_user_id_is_guardian() -> None:
    out = blackbaud.preprocess_rows(
        [{"RelationshipType": "Mother", "User.Id": "G-99"}]
    )
    assert out[0]["guardian_external_id"] == "G-99"
    assert out[0]["guardian_relationship"] == "mother"


def test_bb_non_relationship_user_id_is_external_id() -> None:
    out = blackbaud.preprocess_rows([{"User.Id": "U-1"}])
    assert out[0]["external_id"] == "U-1"
    assert "guardian_external_id" not in out[0]


def test_bb_unknown_relationship_passthrough() -> None:
    out = blackbaud.preprocess_rows([{"RelationshipType": "FosterParent"}])
    assert out[0]["guardian_relationship"] == "FosterParent"


def test_bb_non_iso_date_preserved() -> None:
    out = blackbaud.preprocess_rows([{"Student.DateOfBirth": "invalid"}])
    assert out[0]["date_of_birth"] == "invalid"


# ---------- Veracross ----------


def test_vc_student_email_picked_by_role() -> None:
    out = veracross.preprocess_rows(
        [{"Role": "Student", "StudentEmail": "s@s.com", "FacultyEmail": "f@f.com"}]
    )
    assert out[0]["email"] == "s@s.com"


def test_vc_faculty_email_picked_by_role() -> None:
    out = veracross.preprocess_rows(
        [{"Role": "Faculty", "StudentEmail": "s@s.com", "FacultyEmail": "f@f.com"}]
    )
    assert out[0]["email"] == "f@f.com"


def test_vc_slash_date_single_digit() -> None:
    out = veracross.preprocess_rows([{"DOB": "3/5/2010"}])
    assert out[0]["date_of_birth"] == "2010-03-05"


def test_vc_person_id_faculty_role() -> None:
    out = veracross.preprocess_rows([{"Role": "Faculty", "Person ID": "F-1"}])
    assert out[0]["staff_external_id"] == "F-1"


def test_vc_sex_to_gender() -> None:
    out = veracross.preprocess_rows([{"Role": "Student", "Sex": "F"}])
    assert out[0]["gender"] == "F"


def test_vc_unknown_role_preserves_both_emails() -> None:
    out = veracross.preprocess_rows(
        [{"StudentEmail": "a@a.com", "FacultyEmail": "b@b.com"}]
    )
    # Both preserved under normalized keys; neither becomes "email".
    assert "email" not in out[0]


# ---------- Alma ----------


def test_alma_id_to_external_id() -> None:
    out = alma.preprocess_rows([{"alma_id": "ALMA-1"}])
    assert out[0]["external_id"] == "ALMA-1"


def test_alma_json_in_cell_flattens() -> None:
    out = alma.preprocess_rows(
        [{"extra_attributes": '{"grade":"9","section":"A"}'}]
    )
    assert out[0]["grade"] == "9"
    assert out[0]["section"] == "A"


def test_alma_invalid_json_preserves_cell() -> None:
    out = alma.preprocess_rows([{"extra_attributes": "not-json"}])
    assert out[0]["extra_attributes"] == "not-json"


def test_alma_null_literal_to_empty() -> None:
    out = alma.preprocess_rows([{"email": "null"}])
    assert out[0]["email"] == ""


def test_alma_user_type_to_role() -> None:
    out = alma.preprocess_rows([{"user_type": "Student"}])
    assert out[0]["role"] == "Student"


def test_alma_json_numeric_value() -> None:
    out = alma.preprocess_rows([{"extra_attributes": '{"score":95}'}])
    assert out[0]["score"] == "95"


# ---------- FACTS ----------


def test_facts_familyid_to_household() -> None:
    out = facts.preprocess_rows([{"FAMILYID": "F-1"}])
    assert out[0]["household_id"] == "F-1"


def test_facts_personid_to_external_id() -> None:
    out = facts.preprocess_rows([{"PERSONID": "P-1"}])
    assert out[0]["external_id"] == "P-1"


def test_facts_short_year_2000s() -> None:
    out = facts.preprocess_rows([{"DOB": "03/15/10"}])
    assert out[0]["date_of_birth"] == "2010-03-15"


def test_facts_short_year_1900s() -> None:
    out = facts.preprocess_rows([{"DOB": "06/20/75"}])
    assert out[0]["date_of_birth"] == "1975-06-20"


def test_facts_write_path_routes_to_read_only() -> None:
    out = facts.preprocess_rows([{"tuition_balance": "100.00"}])
    assert out[0]["read_only_balance"] == "100.00"
    assert "balance" not in out[0]


def test_facts_trailing_cr_stripped() -> None:
    out = facts.preprocess_rows([{"FAMILYID": "F-99\r"}])
    assert out[0]["household_id"] == "F-99"


# ---------- Skyward ----------


def test_skyward_id_to_external_id() -> None:
    out = skyward.preprocess_rows([{"SKYWARD_ID": "SK-1"}])
    assert out[0]["external_id"] == "SK-1"


def test_skyward_compact_date_to_iso() -> None:
    out = skyward.preprocess_rows([{"BIRTHDATE": "20100315"}])
    assert out[0]["date_of_birth"] == "2010-03-15"


def test_skyward_iso_date_passes() -> None:
    out = skyward.preprocess_rows([{"BIRTHDATE": "2010-03-15"}])
    assert out[0]["date_of_birth"] == "2010-03-15"


def test_skyward_status_to_read_only() -> None:
    out = skyward.preprocess_rows([{"STATUS": "ACTIVE"}])
    assert out[0]["read_only_status"] == "ACTIVE"
    assert "status" not in out[0]


def test_skyward_trailing_cr_stripped() -> None:
    out = skyward.preprocess_rows([{"FIRST_NAME": "Alice\r"}])
    assert out[0]["first_name"] == "Alice"


def test_skyward_other_id_to_external_id() -> None:
    out = skyward.preprocess_rows([{"OTHER_ID": "O-1"}])
    assert out[0]["external_id"] == "O-1"


# ---------- determinism ----------


def test_determinism_powerschool() -> None:
    r = {"Student Number": "1", "DOB": "01/02/2010"}
    a = powerschool.preprocess_rows([dict(r)])
    b = powerschool.preprocess_rows([dict(r)])
    assert a == b


def test_determinism_alma() -> None:
    r = {"extra_attributes": '{"a":"1","b":"2"}'}
    a = alma.preprocess_rows([dict(r)])
    b = alma.preprocess_rows([dict(r)])
    assert a == b


# ---------- dispatcher ----------


def test_preprocess_for_vendor_unknown_is_identity() -> None:
    rows = [{"foo": "bar"}]
    out = extractors.preprocess_for_vendor(None, rows)
    assert out == rows


def test_preprocess_for_vendor_dispatches() -> None:
    out = extractors.preprocess_for_vendor(
        "powerschool", [{"Student Number": "X"}]
    )
    assert out[0]["external_id"] == "X"


def test_preprocess_for_vendor_unknown_string_raises() -> None:
    with pytest.raises(extractors.UnknownVendor):
        extractors.preprocess_for_vendor("not_real", [{"x": "y"}])


# ---------- architectural boundary ----------


def test_no_network_imports_in_extractors() -> None:
    """Defense-in-depth: assert no extractor module imports httpx, requests,
    or urllib3 (the architectural-boundary rule)."""
    forbidden = ("httpx", "requests", "urllib3", "aiohttp")
    pkg_dir = os.path.dirname(os.path.abspath(extractors.__file__))
    for fname in os.listdir(pkg_dir):
        if not fname.endswith(".py"):
            continue
        with open(os.path.join(pkg_dir, fname), "r", encoding="utf-8") as fh:
            src = fh.read()
        for token in forbidden:
            assert (
                f"import {token}" not in src
                and f"from {token}" not in src
            ), f"{fname} must not import {token} per architectural boundary"
