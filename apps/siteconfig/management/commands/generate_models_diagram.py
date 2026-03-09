"""
Generate docs/architecture/models.png (Section 13.2). Required platform deliverable.
Uses django-extensions graph_models when available; otherwise runs scripts/gen_models_png.py.
Usage: python manage.py generate_models_diagram
"""

import os
import subprocess
import sys
from pathlib import Path

from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "Generate docs/architecture/models.png (Section 13.2). Requires django-extensions and graphviz."

    def add_arguments(self, parser):
        parser.add_argument(
            "--output",
            type=str,
            default="",
            help="Output path (default: docs/architecture/models.png)",
        )

    def handle(self, *args, **options):
        root = Path(__file__).resolve().parent.parent.parent.parent
        out = (Path(options["output"]) if options["output"] else root / "docs" / "architecture" / "models.png").resolve()
        out.parent.mkdir(parents=True, exist_ok=True)

        try:
            result = subprocess.run(
                [sys.executable, "manage.py", "graph_models", "-a", "-o", str(out)],
                capture_output=True,
                text=True,
                timeout=120,
                cwd=root,
            )
            if result.returncode == 0:
                self.stdout.write(self.style.SUCCESS(f"Generated {out}"))
                return
            if "graph_models" in (result.stderr or result.stdout or "").lower() or "unknown command" in (result.stderr or "").lower():
                self.stdout.write(
                    self.style.WARNING("Install django-extensions and graphviz: pip install django-extensions pygraphviz")
                )
                self.stdout.write("Alternatively run: python scripts/gen_models_png.py")
                return
            self.stderr.write(result.stderr or result.stdout or "graph_models failed")
        except FileNotFoundError:
            self.stdout.write(self.style.WARNING("manage.py not found; run from repo root"))
        except subprocess.TimeoutExpired:
            self.stderr.write(self.style.ERROR("graph_models timed out"))
        except Exception as e:
            self.stderr.write(self.style.ERROR(f"Failed: {e}"))
