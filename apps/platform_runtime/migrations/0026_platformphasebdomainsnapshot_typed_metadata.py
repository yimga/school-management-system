# Phase B P2: typed snapshot index (key count + canonical checksum) for diff UI + audits.

import hashlib
import json

from django.db import migrations, models


def _payload_meta(payload):
    if not isinstance(payload, dict):
        payload = {}
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    return len(payload), digest


def backfill_phase_b_metadata(apps, schema_editor):
    Snapshot = apps.get_model("platform_runtime", "PlatformPhaseBDomainSnapshot")
    for row in Snapshot.objects.all():
        k, h = _payload_meta(row.payload)
        row.payload_key_count = k
        row.payload_checksum = h
        row.save(update_fields=["payload_key_count", "payload_checksum"])


class Migration(migrations.Migration):

    dependencies = [
        ("platform_runtime", "0025_runtimedefaults_policy_maps_and_compliance_batch"),
    ]

    operations = [
        migrations.AddField(
            model_name="platformphasebdomainsnapshot",
            name="payload_checksum",
            field=models.CharField(
                blank=True,
                help_text="sha256(hex) of canonical JSON — compare to live owned_payload fingerprint.",
                max_length=64,
            ),
        ),
        migrations.AddField(
            model_name="platformphasebdomainsnapshot",
            name="payload_key_count",
            field=models.PositiveIntegerField(
                default=0,
                help_text="Top-level keys in payload (typed index for operator dashboards).",
            ),
        ),
        migrations.RunPython(backfill_phase_b_metadata, migrations.RunPython.noop),
    ]
