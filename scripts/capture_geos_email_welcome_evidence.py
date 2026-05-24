#!/usr/bin/env python3
"""Capture provision welcome email as .eml evidence (console backend, no secrets)."""

from __future__ import annotations

import os
import sys
from email import message_from_bytes
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

import django

django.setup()

from django.conf import settings  # noqa: E402
from django.core import mail  # noqa: E402
from django.core.mail import EmailMultiAlternatives  # noqa: E402

EVIDENCE_DIR = ROOT / "var" / "evidence" / "geos-99" / "render"


def main() -> int:
    EVIDENCE_DIR.mkdir(parents=True, exist_ok=True)
    out_path = EVIDENCE_DIR / "provision_welcome_sample.eml"

    msg = EmailMultiAlternatives(
        subject="[GEOS evidence] Welcome to RunMyCampus",
        body="Sample provision welcome (evidence capture; no PII).",
        from_email=getattr(settings, "DEFAULT_FROM_EMAIL", "noreply@runmycampus.com"),
        to=["evidence-capture@example.com"],
    )
    msg.attach_alternative(
        "<p>Sample provision welcome HTML (GEOS Lane 2 evidence).</p>",
        "text/html",
    )

    connection = mail.get_connection()
    connection.send_messages([msg])

    outbox = getattr(settings, "EMAIL_FILE_PATH", None) or str(
        ROOT / "sent_emails"
    )
    latest = None
    outbox_path = Path(outbox)
    if outbox_path.is_dir():
        candidates = sorted(
            outbox_path.glob("*.eml"), key=lambda p: p.stat().st_mtime, reverse=True
        )
        if candidates:
            latest = candidates[0]

    if latest and latest.is_file():
        out_path.write_bytes(latest.read_bytes())
    else:
        raw = msg.message().as_bytes()
        out_path.write_bytes(raw)

    if not out_path.is_file() or out_path.stat().st_size < 20:
        print("capture_geos_email_welcome_evidence: FAIL — empty .eml", file=sys.stderr)
        return 1

    message_from_bytes(out_path.read_bytes())
    print(f"capture_geos_email_welcome_evidence: OK -> {out_path.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
