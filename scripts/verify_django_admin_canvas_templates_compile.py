from __future__ import annotations

import os
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")


def main() -> int:
    import django
    from django.template.loader import get_template

    django.setup()

    templates = (
        "admin/base.html",
        "admin/base_site.html",
        "admin/change_form.html",
        "admin/change_list.html",
        "admin/submit_line.html",
        "admin/includes/admin_change_form_rail.html",
    )
    errors: list[str] = []
    for name in templates:
        try:
            get_template(name)
        except Exception as exc:  # pragma: no cover - verifier script
            errors.append(f"{name}: {type(exc).__name__}: {exc}")

    if errors:
        print("DJANGO_ADMIN_CANVAS_TEMPLATE_COMPILE_FAIL")
        for error in errors:
            print(f"  - {error}")
        return 1

    print("DJANGO_ADMIN_CANVAS_TEMPLATE_COMPILE_PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
