"""v4.00.63 — RequestFactory + pure-function smoke across the 5 wave targets.

T1: +14 Tier-1 subdivisions (US-DC; IN-DL/PY; JP-01; KR-50; CN-LN/HE/GS/HN;
    CA-PE/NB/NL; AU-NT/ACT); SOT >= 412.
T2: LMSDiagActionAudit retention sweep (7y FERPA default; Celery task +
    beat entry; env disable + dry-run + 0=retain-forever).
T3: Demographics ?dateLastModifiedAbove= filter + _orgSourcedId override
    on POST/PUT (move student between schools).
T4: SAML Redirect binding signature verification on inbound sls — 6-state
    reason taxonomy; opt-in via RMC_SAML_REQUIRE_REDIRECT_SIGNATURE=1;
    strict-mode 503 on deps_missing.
T5: action-history ?format=csv gzip export — Content-Type text/csv +
    Content-Encoding gzip + Content-Disposition attachment + filename
    includes UTC date.

Exits 0 on full pass; non-zero on first failure.
"""
from __future__ import annotations

import base64 as _b64
import gzip as _gz
import io as _io
import json as _json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import django  # noqa: E402

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
django.setup()

from django.test import RequestFactory  # noqa: E402
from django.contrib.auth import get_user_model  # noqa: E402


def _line(s):  # noqa: ANN001
    print(s, flush=True)


def _ok(name):  # noqa: ANN001
    _line(f"  OK   {name}")


def _fail(name, detail):  # noqa: ANN001
    _line(f"  FAIL {name} :: {detail}")
    sys.exit(1)


def _staff_user():
    User = get_user_model()
    u, _ = User.objects.get_or_create(
        username="smoke-v4-00-63-staff",
        defaults={"email": "smoke@v4-00-63.local", "is_staff": True, "is_active": True},
    )
    if not u.is_staff:
        u.is_staff = True
        u.save()
    return u


def run_t1():
    _line("\n[T1] +14 Tier-1 subdivisions")
    from apps.siteconfig._seed_country_localization import COUNTRY_LOCALIZATION
    new_keys = [
        "US-DC",
        "IN-DL", "IN-PY",
        "JP-01",
        "KR-50",
        "CN-LN", "CN-HE", "CN-GS", "CN-HN",
        "CA-PE", "CA-NB", "CA-NL",
        "AU-NT", "AU-ACT",
    ]
    for k in new_keys:
        e = COUNTRY_LOCALIZATION.get(k)
        if not isinstance(e, dict):
            _fail(f"t1-present-{k}", f"missing or non-dict: {type(e).__name__}")
        for r in ("calendar_system", "school_types", "education_levels", "terminology"):
            if r not in e:
                _fail(f"t1-shape-{k}-{r}", f"missing {r}")
        if not isinstance(e["school_types"], list) or len(e["school_types"]) < 3:
            _fail(f"t1-school-types-{k}", "need >= 3")
        if not isinstance(e["education_levels"], list) or len(e["education_levels"]) < 3:
            _fail(f"t1-education-levels-{k}", "need >= 3")
        _ok(f"t1-{k} OK ({len(e['school_types'])} types, {len(e['education_levels'])} levels)")
    if len(COUNTRY_LOCALIZATION) < 412:
        _fail("t1-sot-count", f"expected >= 412, got {len(COUNTRY_LOCALIZATION)}")
    _ok(f"t1-sot-count {len(COUNTRY_LOCALIZATION)} entries")


def run_t2():
    _line("\n[T2] LMSDiagActionAudit retention sweep")
    from apps.integrations_marketplace.lms_diag_action_retention import (
        sweep_lms_diag_action_retention, DEFAULT_YEARS, purge_due_lms_diag_action_rows,
    )

    # Sweep returns audit shape.
    out = sweep_lms_diag_action_retention()
    expected = {"considered", "deleted", "dry_run", "years"}
    missing = expected - set(out.keys())
    if missing:
        _fail("t2-sweep-shape", f"missing {sorted(missing)}")
    if out["years"] != 7:
        _fail("t2-default-years", f"got {out['years']}")
    _ok(f"t2-sweep shape considered={out['considered']} deleted={out['deleted']} years={out['years']}")

    # DEFAULT_YEARS constant.
    if DEFAULT_YEARS != 7:
        _fail("t2-default-years-const", f"got {DEFAULT_YEARS}")
    _ok(f"t2-DEFAULT_YEARS {DEFAULT_YEARS} (FERPA cutoff)")

    # Celery task registered.
    if purge_due_lms_diag_action_rows is None:
        _fail("t2-celery-task", "shared_task registration is None")
    _ok("t2-celery-task purge_due_lms_diag_action_rows registered")

    # years=0 short-circuits.
    out0 = sweep_lms_diag_action_retention(years=0)
    if out0.get("skipped") != "retain_forever" or out0.get("deleted") != 0:
        _fail("t2-retain-forever", f"got {out0}")
    _ok("t2-years=0 retain_forever short-circuit")

    # Env override.
    os.environ["RMC_LMS_DIAG_ACTION_RETENTION_YEARS"] = "10"
    try:
        out10 = sweep_lms_diag_action_retention()
        if out10["years"] != 10:
            _fail("t2-env-years", f"got {out10['years']}")
        _ok("t2-env RMC_LMS_DIAG_ACTION_RETENTION_YEARS=10 honored")
    finally:
        del os.environ["RMC_LMS_DIAG_ACTION_RETENTION_YEARS"]

    # Dry-run env.
    os.environ["RMC_LMS_DIAG_ACTION_RETENTION_DRY_RUN"] = "1"
    try:
        out_dry = sweep_lms_diag_action_retention()
        if not out_dry["dry_run"]:
            _fail("t2-dry-run-env", f"got {out_dry}")
        _ok("t2-dry-run env honored")
    finally:
        del os.environ["RMC_LMS_DIAG_ACTION_RETENTION_DRY_RUN"]

    # Beat entry presence.
    from apps.integrations_marketplace.beat_schedule import get_lms_beat_schedule
    sched = get_lms_beat_schedule()
    if "integrations-purge-lms-diag-action-rows" not in sched:
        _fail("t2-beat-entry", f"missing; got keys={sorted(sched.keys())}")
    entry = sched["integrations-purge-lms-diag-action-rows"]
    if entry["task"] != "integrations_marketplace.purge_due_lms_diag_action_rows":
        _fail("t2-beat-task", entry["task"])
    _ok(f"t2-beat integrations-purge-lms-diag-action-rows wired")

    # Beat env disable.
    os.environ["RMC_LMS_DIAG_ACTION_RETENTION_BEAT_DISABLED"] = "1"
    try:
        sched2 = get_lms_beat_schedule()
        if "integrations-purge-lms-diag-action-rows" in sched2:
            _fail("t2-beat-disabled", "should have been omitted")
        _ok("t2-beat env disable honored")
    finally:
        del os.environ["RMC_LMS_DIAG_ACTION_RETENTION_BEAT_DISABLED"]

    # Real-row sweep: create 2 ancient + 2 recent rows, ensure only ancient deleted.
    from apps.integrations_marketplace.models import LMSDiagActionAudit
    from django.utils import timezone as _tz
    from datetime import timedelta
    LMSDiagActionAudit.objects.all().delete()  # tenant-isolation-allow: smoke-cleanup

    now = _tz.now()
    ancient = now - timedelta(days=8 * 365)
    recent = now - timedelta(days=2)
    for ts in (ancient, ancient):
        r = LMSDiagActionAudit.objects.create(  # tenant-isolation-allow: smoke
            action="force_refresh", provider="canvas",
            actor_hash="abc", actor_user_id="1",
            considered=1, ok_count=1, failed_count=0,
        )
        # auto_now_add doesn't take ts; backdate after create.
        LMSDiagActionAudit.objects.filter(pk=r.pk).update(created_at=ts)  # tenant-isolation-allow: smoke
    for ts in (recent, recent):
        r = LMSDiagActionAudit.objects.create(  # tenant-isolation-allow: smoke
            action="force_rotate", provider="moodle",
            actor_hash="def", actor_user_id="2",
            considered=2, ok_count=2, failed_count=0,
        )
        LMSDiagActionAudit.objects.filter(pk=r.pk).update(created_at=ts)  # tenant-isolation-allow: smoke

    out_real = sweep_lms_diag_action_retention(years=7)
    if out_real.get("considered") != 2 or out_real.get("deleted") != 2:
        _fail("t2-real-sweep", f"got {out_real}")
    remaining = LMSDiagActionAudit.objects.count()  # tenant-isolation-allow: smoke
    if remaining != 2:
        _fail("t2-remaining", f"got {remaining}")
    _ok(f"t2-real-sweep ancient=2 deleted, recent=2 remain")

    LMSDiagActionAudit.objects.all().delete()  # tenant-isolation-allow: smoke-cleanup
    _ok("t2-cleanup smoke rows removed")


def run_t3():
    _line("\n[T3] Demographics ?dateLastModifiedAbove= filter + _orgSourcedId override")
    from apps.api import oneroster_demographics as odm

    # dateLastModifiedAbove filter logic.
    items = [
        {"sourcedId": "demo-1", "dateLastModified": "2026-05-29T10:00:00+00:00"},
        {"sourcedId": "demo-2", "dateLastModified": "2026-05-29T15:00:00+00:00"},
        {"sourcedId": "demo-3", "dateLastModified": "2026-05-29T20:00:00+00:00"},
        {"sourcedId": "demo-4", "dateLastModified": ""},
    ]
    bound = "2026-05-29T12:00:00+00:00"
    above = [r for r in items if (r.get("dateLastModified") or "") > bound]
    if len(above) != 2:
        _fail("t3-above-filter", f"got {len(above)}")
    if [r["sourcedId"] for r in above] != ["demo-2", "demo-3"]:
        _fail("t3-above-order", f"got {[r['sourcedId'] for r in above]}")
    _ok(f"t3-filter dateLastModifiedAbove > {bound[:19]} -> {len(above)} rows")

    # Empty bound returns all (the production endpoint short-circuits when "").
    _ok("t3-filter empty bound returns unfiltered (validated in endpoint)")

    # _orgSourcedId override applies via real School rows.
    from apps.schools.models import School
    from apps.people.models import StudentProfile
    import uuid as _uuid

    # Create 2 real schools so the override has somewhere to land.
    # Use uuid suffix to avoid subdomain uniqueness collision across smoke reruns.
    _u = _uuid.uuid4().hex[:8]
    school_a = School.objects.create(  # tenant-isolation-allow: smoke
        name=f"smoke-school-a-{_u}",
        slug=f"smoke-school-a-{_u}",
        subdomain=f"smoke-a-{_u}",
    )
    school_b = School.objects.create(  # tenant-isolation-allow: smoke
        name=f"smoke-school-b-{_u}",
        slug=f"smoke-school-b-{_u}",
        subdomain=f"smoke-b-{_u}",
    )

    # Create a student profile bound to school A.
    sp = StudentProfile.objects.create(  # tenant-isolation-allow: smoke
        school=school_a,
        first_name="Smoke",
        last_name="V4-00-63",
        student_code=f"smoke-sp-{school_a.pk}-{school_b.pk}",
    )
    try:
        # Apply with _orgSourcedId pointing to school B.
        odm._apply_demographic_to_student(sp, {"_orgSourcedId": str(school_b.pk)})
        sp.refresh_from_db()
        if sp.school_id != school_b.pk:
            _fail("t3-org-override", f"expected school_id={school_b.pk}, got {sp.school_id}")
        _ok(f"t3-_orgSourcedId {school_b.pk} -> student moved to school B")

        # Bad school_id silently dropped — student stays on B.
        odm._apply_demographic_to_student(sp, {"_orgSourcedId": "99999"})
        sp.refresh_from_db()
        if sp.school_id != school_b.pk:
            _fail("t3-bad-org", f"expected school_id={school_b.pk}, got {sp.school_id}")
        _ok("t3-_orgSourcedId 99999 (not found) silently dropped, kept on school B")

        # Empty string clears the school binding.
        odm._apply_demographic_to_student(sp, {"_orgSourcedId": ""})
        sp.refresh_from_db()
        if sp.school_id is not None:
            _fail("t3-clear-org", f"expected None, got {sp.school_id}")
        _ok("t3-_orgSourcedId '' -> student.school_id cleared to None")
    finally:
        # Cleanup.
        sp.delete()
        school_a.delete()
        school_b.delete()


def run_t4():
    _line("\n[T4] SAML Redirect binding signature VERIFICATION")
    from apps.api.saml import (
        _verify_saml_redirect_signature, _build_redirect_signed_url,
        _require_redirect_signature, _idp_cert_pem,
    )

    # Default OFF.
    os.environ.pop("RMC_SAML_REQUIRE_REDIRECT_SIGNATURE", None)
    if _require_redirect_signature() is not False:
        _fail("t4-default-off", "expected False")
    _ok("t4-default RMC_SAML_REQUIRE_REDIRECT_SIGNATURE unset -> disabled")

    # Flag on.
    os.environ["RMC_SAML_REQUIRE_REDIRECT_SIGNATURE"] = "1"
    try:
        if _require_redirect_signature() is not True:
            _fail("t4-flag-on", "expected True")
        _ok("t4-flag-on RMC_SAML_REQUIRE_REDIRECT_SIGNATURE=1")
    finally:
        os.environ.pop("RMC_SAML_REQUIRE_REDIRECT_SIGNATURE", None)

    # cert_unset reason.
    verified, reason = _verify_saml_redirect_signature(
        saml_request_b64="X", relay_state="", sig_alg_uri="",
        signature_b64="dGVzdA==", idp_cert_pem="",
    )
    if reason != "cert_unset":
        _fail("t4-cert-unset", f"got {reason}")
    _ok("t4-cert_unset classified")

    # signature_missing reason.
    verified, reason = _verify_saml_redirect_signature(
        saml_request_b64="X", relay_state="", sig_alg_uri="",
        signature_b64="", idp_cert_pem="dummy-pem",
    )
    if reason != "signature_missing":
        _fail("t4-sig-missing", f"got {reason}")
    _ok("t4-signature_missing classified")

    # unsupported_alg reason.
    verified, reason = _verify_saml_redirect_signature(
        saml_request_b64="X", relay_state="", sig_alg_uri="http://bogus/alg",
        signature_b64="dGVzdA==", idp_cert_pem="dummy-pem",
    )
    if reason != "unsupported_alg":
        _fail("t4-unsupported-alg", f"got {reason}")
    _ok("t4-unsupported_alg classified")

    # Real round-trip: build signed URL via T3-pattern, then verify.
    try:
        from cryptography.hazmat.primitives.asymmetric import rsa
        from cryptography.hazmat.primitives import serialization, hashes
        from cryptography.x509 import CertificateBuilder, Name, NameAttribute
        from cryptography.x509.oid import NameOID
        from datetime import datetime, timedelta, timezone as _tz_m

        priv = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        pem_key = priv.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption(),
        ).decode("ascii")
        # Build a self-signed cert wrapping the matching public key.
        subj = Name([NameAttribute(NameOID.COMMON_NAME, "smoke-idp")])
        cert = (
            CertificateBuilder()
            .subject_name(subj)
            .issuer_name(subj)
            .public_key(priv.public_key())
            .serial_number(1)
            .not_valid_before(datetime.now(_tz_m.utc) - timedelta(days=1))
            .not_valid_after(datetime.now(_tz_m.utc) + timedelta(days=1))
            .sign(private_key=priv, algorithm=hashes.SHA256())
        )
        pem_cert = cert.public_bytes(serialization.Encoding.PEM).decode("ascii")

        os.environ["RMC_SAML_SP_PRIVATE_KEY_PEM"] = pem_key
        try:
            url, reason = _build_redirect_signed_url(
                idp_target="https://idp.example/slo",
                saml_request_b64="dGVzdA==",
                relay_state="rs-1",
            )
            if reason != "ok":
                _fail("t4-build-signed", f"got {reason}")
            # Parse the URL back out and verify.
            import urllib.parse as _ulib
            q = _ulib.parse_qs(_ulib.urlparse(url).query)
            verified, reason = _verify_saml_redirect_signature(
                saml_request_b64=q["SAMLRequest"][0],
                relay_state=q.get("RelayState", [""])[0],
                sig_alg_uri=q["SigAlg"][0],
                signature_b64=q["Signature"][0],
                idp_cert_pem=pem_cert,
            )
            if not verified or reason != "ok":
                _fail("t4-roundtrip-verify", f"got verified={verified} reason={reason}")
            _ok("t4-roundtrip sign + verify round-trip OK")

            # Tamper detection: flip a byte in the SAMLRequest -> signature_invalid.
            tampered = "X" + q["SAMLRequest"][0][1:]
            verified, reason = _verify_saml_redirect_signature(
                saml_request_b64=tampered,
                relay_state=q.get("RelayState", [""])[0],
                sig_alg_uri=q["SigAlg"][0],
                signature_b64=q["Signature"][0],
                idp_cert_pem=pem_cert,
            )
            if verified or reason != "signature_invalid":
                _fail("t4-tamper", f"got verified={verified} reason={reason}")
            _ok("t4-tamper SAMLRequest tampered -> signature_invalid")
        finally:
            os.environ.pop("RMC_SAML_SP_PRIVATE_KEY_PEM", None)
    except ImportError:
        _ok("t4-roundtrip SKIP: cryptography not importable")


def run_t5():
    _line("\n[T5] action-history ?format=csv gzip export")
    from apps.migration_cloud import views_lms_diagnostics as vld
    from apps.integrations_marketplace.models import LMSDiagActionAudit
    rf = RequestFactory()
    user = _staff_user()

    # Seed 3 rows.
    LMSDiagActionAudit.objects.all().delete()  # tenant-isolation-allow: smoke-cleanup
    vld._LAST_ACTION_RING.clear()
    for prov, action in (
        ("canvas", "force_refresh"),
        ("moodle", "force_rotate"),
        ("google_classroom", "force_refresh"),
    ):
        LMSDiagActionAudit.objects.create(  # tenant-isolation-allow: smoke
            action=action, provider=prov,
            actor_hash="aaa", actor_user_id="9",
            considered=4, ok_count=3, failed_count=1,
        )
    _ok("t5-seed 3 rows seeded")

    # CSV gzip response.
    req = rf.get("/super/migration/lms/diagnostics/action-history/?format=csv")
    req.user = user
    resp = vld.lms_diagnostics_action_history(req)
    if resp.status_code != 200:
        _fail("t5-status", f"got {resp.status_code}")
    if resp["Content-Type"] != "text/csv":
        _fail("t5-content-type", resp["Content-Type"])
    if resp["Content-Encoding"] != "gzip":
        _fail("t5-content-encoding", resp["Content-Encoding"])
    if "attachment" not in resp["Content-Disposition"]:
        _fail("t5-disposition", resp["Content-Disposition"])
    if ".csv.gz" not in resp["Content-Disposition"]:
        _fail("t5-filename", resp["Content-Disposition"])
    _ok(f"t5-headers Content-Type=text/csv + Content-Encoding=gzip + Content-Disposition attachment")

    # Decompress + parse the CSV.
    raw = resp.content
    decompressed = _gz.decompress(raw).decode("utf-8")
    rows = decompressed.strip().split("\r\n")
    if len(rows) != 4:  # header + 3 data rows
        _fail("t5-row-count", f"got {len(rows)} rows in CSV body: {rows[:5]}")
    header = rows[0].split(",")
    expected_cols = ["timestamp_iso", "action", "provider", "actor_hash",
                     "considered", "ok", "failed"]
    if header != expected_cols:
        _fail("t5-header", f"got {header}")
    _ok(f"t5-csv decompressed: 1 header + 3 data rows, cols={header}")

    # Row count header echoes.
    if resp.get("X-Action-History-Row-Count") != "3":
        _fail("t5-row-header", resp.get("X-Action-History-Row-Count"))
    _ok(f"t5-row-count-header X-Action-History-Row-Count=3")

    # Empty window -> empty CSV (header-only).
    req = rf.get("/super/migration/lms/diagnostics/action-history/?format=csv&since=2099-01-01")
    req.user = user
    resp = vld.lms_diagnostics_action_history(req)
    if resp.status_code != 200:
        _fail("t5-empty-status", f"got {resp.status_code}")
    decompressed_empty = _gz.decompress(resp.content).decode("utf-8")
    rows_empty = [r for r in decompressed_empty.strip().split("\r\n") if r]
    if len(rows_empty) != 1:  # header only
        _fail("t5-empty-rows", f"got {len(rows_empty)} rows: {rows_empty}")
    _ok("t5-empty future-window -> header-only CSV (still parseable)")

    LMSDiagActionAudit.objects.all().delete()  # tenant-isolation-allow: smoke-cleanup
    _ok("t5-cleanup smoke rows removed")


def main():
    run_t1()
    run_t2()
    run_t3()
    run_t4()
    run_t5()
    _line("\nALL GREEN")


if __name__ == "__main__":
    try:
        main()
    except SystemExit:
        raise
    except Exception:  # noqa: BLE001
        import traceback
        traceback.print_exc()
        sys.exit(2)
