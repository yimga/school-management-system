"""v3.32.0 — merge migration: converge the parallel-agent branches.

The v3.32.0 5-agent fan-out left two parallel 0007 branches:

  * ``0007_companion_keypair``                      (Agent 1)
  * ``0007_token_rotation_and_webhook_deferred``    (Agent 3, this PR)
      └→ ``0008_wrap_webhook_secret``               (Agent 5, depends on
                                                     Agent 3's 0007 name)

This empty merge migration brings both leaves under one parent so
``makemigrations --check`` is clean and ``migrate`` runs deterministically.
Depends only on the two branch tips: ``0007_companion_keypair`` and
``0008_wrap_webhook_secret`` (which already chains through Agent 3's
``0007_token_rotation_and_webhook_deferred``).
No schema operations — pure dependency graph plumbing.
"""

from __future__ import annotations

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("migration_cloud", "0007_companion_keypair"),
        ("migration_cloud", "0008_wrap_webhook_secret"),
    ]

    operations = []
