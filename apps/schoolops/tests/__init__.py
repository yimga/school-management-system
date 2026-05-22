"""Test package for apps.schoolops.

This file makes the ``tests`` directory an importable Python package so
that ``manage.py test apps.schoolops`` (Django test discovery) and
``pytest apps/schoolops/tests/`` (pytest discovery) both find the
test modules. Without it, Django's ``DiscoverRunner`` walks past the
directory and reports "Found 0 test(s)" (Wave 9 Agent P, v3.58.x).
"""
