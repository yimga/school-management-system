"""
Pytest bootstrap: configure Django so tests can use settings, URLs, and static().

CI and local runs use `pytest` without requiring pytest-django.
"""

from __future__ import annotations

import os


def pytest_configure() -> None:
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
    import django
    from django.apps import apps

    # Avoid double setup if another plugin or test module initialized Django first.
    if apps.ready:
        return
    django.setup()
