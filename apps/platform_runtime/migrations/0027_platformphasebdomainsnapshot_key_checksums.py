# Phase B: per top-level key fingerprints on snapshot rows (operator diff / queries).

import hashlib
import json

from django.db import migrations, models


def _key_checksums(payload):
    if not isinstance(payload, dict):
        return {}
    out = {}
    for key in sorted(payload.keys()):
        canonical = json.dumps(
            payload[key], sort_keys=True, separators=(",", ":"), default=str
        )
        out[key] = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    return out


def backfill_key_checksums(apps, schema_editor):
    Snapshot = apps.get_model("platform_runtime", "PlatformPhaseBDomainSnapshot")
    for row in Snapshot.objects.all():
        payload = row.payload if isinstance(row.payload, dict) else {}
        row.payload_key_checksums = _key_checksums(payload)
        row.save(update_fields=["payload_key_checksums"])


class Migration(migrations.Migration):

    dependencies = [
        ("platform_runtime", "0026_platformphasebdomainsnapshot_typed_metadata"),
    ]

    operations = [
        migrations.AddField(
            model_name="platformphasebdomainsnapshot",
            name="payload_key_checksums",
            field=models.JSONField(
                blank=True,
                default=dict,
                help_text="Map top-level payload key → sha256(hex) of that key's canonical JSON value.",
            ),
        ),
        migrations.RunPython(backfill_key_checksums, migrations.RunPython.noop),
    ]
