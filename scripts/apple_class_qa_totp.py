"""Print the current 6-digit TOTP for an Apple-class QA user (local Playwright only)."""
from __future__ import annotations

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import django

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
django.setup()

from django.contrib.auth import get_user_model
from django_otp.oath import totp
from django_otp.plugins.otp_totp.models import TOTPDevice

User = get_user_model()
DEVICE_NAME = "apple-class-qa"


def main() -> None:
    username = sys.argv[1] if len(sys.argv) > 1 else os.environ.get("APPLE_QA_USERNAME", "")
    if not username:
        raise SystemExit("usage: apple_class_qa_totp.py <username>")
    user = User.objects.filter(username=username).first()
    if user is None:
        raise SystemExit(f"user not found: {username}")
    device = TOTPDevice.objects.filter(user=user, name=DEVICE_NAME, confirmed=True).first()
    if device is None:
        device = (
            TOTPDevice.objects.filter(user=user, confirmed=True)
            .order_by("id")
            .first()
        )
    if device is None:
        raise SystemExit(
            f"no confirmed TOTP for {username}; run: python scripts/seed_apple_class_qa.py"
        )
    print(str(totp(device.bin_key)).zfill(6))


if __name__ == "__main__":
    main()
