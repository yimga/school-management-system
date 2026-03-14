from __future__ import annotations

import re
from pathlib import Path

from django.core.management.base import BaseCommand


HEX_COLOR_RE = re.compile(r"#[0-9a-fA-F]{3,8}\b")
FORBIDDEN_LABEL_RE = re.compile(r">\s*(Student|Teacher|Parent|Principal)\s*<")


class Command(BaseCommand):
    help = "Check Branding Law: no hardcoded hex colors or hardcoded core role labels in tenant-facing templates."

    def add_arguments(self, parser):
        parser.add_argument(
            "--paths",
            nargs="*",
            default=[
                "templates/schools",
                "templates/auth",
                "templates/base.html",
                "templates/backend_base.html",
            ],
            help="Files or folders to scan.",
        )

    def handle(self, *args, **options):
        targets = options.get("paths") or []
        root = Path.cwd()
        files: list[Path] = []

        for entry in targets:
            path = (root / entry).resolve()
            if path.is_dir():
                files.extend(sorted(p for p in path.rglob("*.html") if p.is_file()))
            elif path.is_file():
                files.append(path)

        violations: list[str] = []
        for file_path in files:
            try:
                text = file_path.read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError):
                continue
            for match in HEX_COLOR_RE.finditer(text):
                # Allow CSS variable syntax and template placeholders.
                value = match.group(0)
                if value.lower() in {"#fff", "#ffffff", "#000", "#000000"}:
                    # Keep strict rule simple: even common neutral colors are violations.
                    pass
                line = text.count("\n", 0, match.start()) + 1
                violations.append(f"{file_path}:{line} hardcoded color {value}")
            for match in FORBIDDEN_LABEL_RE.finditer(text):
                line = text.count("\n", 0, match.start()) + 1
                violations.append(f"{file_path}:{line} hardcoded label {match.group(1)}")

        if violations:
            self.stdout.write(self.style.ERROR("Branding Law violations found:"))
            for item in violations:
                self.stdout.write(f" - {item}")
            raise SystemExit(2)

        self.stdout.write(self.style.SUCCESS("Branding Law check passed."))
