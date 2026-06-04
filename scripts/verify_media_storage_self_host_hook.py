#!/usr/bin/env python3
"""Verify SH-4: env-driven STORAGES hook for S3-compatible self-hosted media."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--write-json",
        action="store_true",
        help="Write docs/generated/open_source_media_storage_hook.json",
    )
    args = parser.parse_args()
    errors: list[str] = []

    settings_py = ROOT / "config" / "settings.py"
    env_example = ROOT / ".env.example"
    req_optional = ROOT / "requirements_optional.txt"

    if not settings_py.is_file():
        errors.append("missing config/settings.py")
    else:
        text = settings_py.read_text(encoding="utf-8")
        needles = (
            "MEDIA_STORAGE_BACKEND",
            "_USE_S3_MEDIA",
            'STORAGES = {\n    "default": _media_storage',
            "storages.backends.s3.S3Storage",
            "django.core.files.storage.FileSystemStorage",
            "AWS_S3_ENDPOINT_URL",
            "AWS_STORAGE_BUCKET_NAME",
        )
        for needle in needles:
            if needle not in text:
                errors.append(f"config/settings.py missing {needle!r}")

    if not env_example.is_file():
        errors.append("missing .env.example")
    elif "MEDIA_STORAGE_BACKEND" not in env_example.read_text(encoding="utf-8"):
        errors.append(".env.example missing MEDIA_STORAGE_BACKEND")

    if not req_optional.is_file():
        errors.append("missing requirements_optional.txt")
    else:
        opt = req_optional.read_text(encoding="utf-8")
        if "django-storages" not in opt:
            errors.append("requirements_optional.txt must document django-storages[s3]")

    if errors:
        for err in errors:
            print(f"FAIL: {err}")
        return 1

    payload = {
        "status": "hook_present",
        "settings_path": "config/settings.py",
        "env_vars": [
            "MEDIA_STORAGE_BACKEND",
            "AWS_S3_ENDPOINT_URL",
            "AWS_STORAGE_BUCKET_NAME",
            "AWS_ACCESS_KEY_ID",
            "AWS_SECRET_ACCESS_KEY",
        ],
        "optional_dependency": "django-storages[s3] (requirements_optional.txt)",
        "default_backend": "django.core.files.storage.FileSystemStorage",
    }
    if args.write_json:
        out = ROOT / "docs" / "generated" / "open_source_media_storage_hook.json"
        out.parent.mkdir(parents=True, exist_ok=True)
        import json

        out.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
        print(f"wrote {out.relative_to(ROOT)}")

    print("MEDIA_STORAGE_SELF_HOST_HOOK_PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
