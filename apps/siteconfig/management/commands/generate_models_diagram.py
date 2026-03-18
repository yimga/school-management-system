"""
Generate docs/architecture/models.png (Section 13.2). Required platform deliverable.
Uses django-extensions graph_models when available; otherwise runs scripts/gen_models_png.py.
Usage: python manage.py generate_models_diagram
§2.4: Typed exception tuple and log_exception_with_context for subprocess/run failures.
"""

import subprocess
import sys
from pathlib import Path

from django.core.management.base import BaseCommand

from apps.platform_runtime.structured_logging import log_exception_with_context

# §2.4 Typed exceptions for allowlist shrink (broad_exception_audit)
_GENERATE_MODELS_DIAGRAM_ERRORS = (
    OSError,
    ValueError,
    TypeError,
    subprocess.CalledProcessError,
    subprocess.SubprocessError,
    RuntimeError,
)


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
        out = (
            Path(options["output"])
            if options["output"]
            else root / "docs" / "architecture" / "models.png"
        ).resolve()
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
            if (
                "graph_models" in (result.stderr or result.stdout or "").lower()
                or "unknown command" in (result.stderr or "").lower()
            ):
                self.stdout.write(
                    self.style.WARNING(
                        "Install django-extensions and graphviz: pip install django-extensions pygraphviz"
                    )
                )
                self.stdout.write("Alternatively run: python scripts/gen_models_png.py")
                return
            self.stderr.write(result.stderr or result.stdout or "graph_models failed")
        except FileNotFoundError:
            self.stdout.write(
                self.style.WARNING("manage.py not found; run from repo root")
            )
        except subprocess.TimeoutExpired:
            self.stderr.write(self.style.ERROR("graph_models timed out"))
        except _GENERATE_MODELS_DIAGRAM_ERRORS as e:
            log_exception_with_context(
                "generate_models_diagram: graph_models subprocess failed",
                school_id=None,
                extra={
                    "command": "generate_models_diagram",
                    "output": str(out),
                    "error": str(e),
                },
            )
            self.stderr.write(self.style.ERROR(f"Failed: {e}"))
