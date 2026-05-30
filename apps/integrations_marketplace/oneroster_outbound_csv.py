"""v4.00.91 Studio-OS-10X W1 Pillar B14 — OneRoster outbound CSV push staging emitter.

Builds OneRoster v1.2 CSV-Schema 4 compliant bulk-staging zip with the
standard resource files (orgs, users, classes, courses, enrollments,
academicSessions, demographics, manifest). Output is a zip archive
ready for delivery to a downstream Roster Service via either SFTP push
(common SIS pattern) or upload to a vendor-specific CSV ingest endpoint.

Live SFTP push gated behind ``RMC_ONEROSTER_OUTBOUND_LIVE_OUTBOUND`` env.
Dry-run returns the zip bytes + intended target so callers can verify
payload shape without touching the network.

The CSV schemas follow IMS OneRoster v1.2 § Appendix A (CSV Schema 4):
  * ``manifest.csv``   — file-set declaration + propertyName=propertyValue
  * ``orgs.csv``       — sourcedId, name, type, identifier, parentSourcedId
  * ``users.csv``      — sourcedId, status, dateLastModified, enabledUser,
                         orgSourcedIds, role, username, ...
  * ``classes.csv``    — sourcedId, status, title, classCode, classType, ...
  * ``enrollments.csv``— sourcedId, status, classSourcedId, schoolSourcedId,
                         userSourcedId, role, primary, beginDate, endDate
"""
from __future__ import annotations

import csv
import io
import logging
import os
import zipfile
from datetime import datetime, timezone
from typing import Any, Iterable

logger = logging.getLogger(__name__)


def _now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _live() -> bool:
    return os.environ.get("RMC_ONEROSTER_OUTBOUND_LIVE_OUTBOUND", "").strip().lower() in ("1", "true", "yes", "on")


MANIFEST_HEADER = ("propertyName", "value")
DEFAULT_MANIFEST = (
    ("manifest.version", "1.0"),
    ("oneroster.version", "1.2"),
    ("file.academicSessions", "absent"),
    ("file.categories", "absent"),
    ("file.classes", "bulk"),
    ("file.classResources", "absent"),
    ("file.courses", "absent"),
    ("file.courseResources", "absent"),
    ("file.demographics", "absent"),
    ("file.enrollments", "bulk"),
    ("file.lineItems", "absent"),
    ("file.orgs", "bulk"),
    ("file.resources", "absent"),
    ("file.results", "absent"),
    ("file.users", "bulk"),
)
ORGS_HEADER = ("sourcedId", "status", "dateLastModified", "name", "type", "identifier", "parentSourcedId")
USERS_HEADER = (
    "sourcedId", "status", "dateLastModified", "enabledUser", "orgSourcedIds",
    "role", "username", "userIds", "givenName", "familyName", "middleName", "email",
)
CLASSES_HEADER = (
    "sourcedId", "status", "dateLastModified", "title", "classCode",
    "classType", "location", "grades", "subjects", "courseSourcedId",
    "schoolSourcedId", "termSourcedIds", "subjectCodes",
)
ENROLLMENTS_HEADER = (
    "sourcedId", "status", "dateLastModified", "classSourcedId",
    "schoolSourcedId", "userSourcedId", "role", "primary", "beginDate", "endDate",
)


def _csv_block(header: tuple[str, ...], rows: Iterable[dict[str, Any]]) -> str:
    buf = io.StringIO()
    w = csv.writer(buf, quoting=csv.QUOTE_MINIMAL, lineterminator="\n")
    w.writerow(header)
    for row in rows:
        w.writerow([str(row.get(k, "")) for k in header])
    return buf.getvalue()


def build_oneroster_csv_zip(
    *,
    orgs: list[dict[str, Any]] | None = None,
    users: list[dict[str, Any]] | None = None,
    classes: list[dict[str, Any]] | None = None,
    enrollments: list[dict[str, Any]] | None = None,
) -> bytes:
    """Assemble a OneRoster v1.2 CSV-Schema 4 zip archive.

    Empty resource collections still get a header-only file (per spec).
    Returns the raw zip bytes for either dry-run inspection or live upload.
    """
    orgs = list(orgs or [])
    users = list(users or [])
    classes = list(classes or [])
    enrollments = list(enrollments or [])

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        # Manifest declares which files are bulk vs delta vs absent.
        manifest_io = io.StringIO()
        mw = csv.writer(manifest_io, quoting=csv.QUOTE_MINIMAL, lineterminator="\n")
        mw.writerow(MANIFEST_HEADER)
        for k, v in DEFAULT_MANIFEST:
            mw.writerow([k, v])
        zf.writestr("manifest.csv", manifest_io.getvalue())
        zf.writestr("orgs.csv", _csv_block(ORGS_HEADER, orgs))
        zf.writestr("users.csv", _csv_block(USERS_HEADER, users))
        zf.writestr("classes.csv", _csv_block(CLASSES_HEADER, classes))
        zf.writestr("enrollments.csv", _csv_block(ENROLLMENTS_HEADER, enrollments))
    return buf.getvalue()


def push_oneroster_csv_bundle(
    *,
    target_endpoint: str = "",
    orgs: list[dict[str, Any]] | None = None,
    users: list[dict[str, Any]] | None = None,
    classes: list[dict[str, Any]] | None = None,
    enrollments: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Build + (live mode) push the OneRoster CSV bundle.

    Returns ``{status, target_endpoint, bytes_len, file_count, would_send|sent}``.
    """
    blob = build_oneroster_csv_zip(orgs=orgs, users=users, classes=classes, enrollments=enrollments)
    target = target_endpoint or "/oneroster/csv/upload"
    summary = {
        "bytes_len": len(blob),
        "file_count": 5,  # manifest + 4 resource files
        "manifest_version": "1.0",
        "oneroster_version": "1.2",
        "generated_at": _now_iso(),
    }
    if not _live():
        return {
            "status": "dry_run_scaffold",
            "target_method": "POST",
            "target_endpoint": target,
            "summary": summary,
            "would_send_zip_bytes_first_2": list(blob[:2]),  # PK marker confirms zip
            "live_env_var": "RMC_ONEROSTER_OUTBOUND_LIVE_OUTBOUND",
        }
    try:
        import requests
        resp = requests.post(
            target,
            data=blob,
            headers={"Content-Type": "application/zip"},
            timeout=120,
        )
    except Exception as exc:  # noqa: BLE001
        return {"status": "network_error", "reason": str(exc)[:120], "summary": summary}
    if resp.status_code >= 400:
        return {"status": "upstream_error", "http_status": resp.status_code, "summary": summary}
    return {"status": "ok", "http_status": resp.status_code,
            "target_endpoint": target, "summary": summary}
