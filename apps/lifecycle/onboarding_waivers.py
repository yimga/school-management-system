"""Per-aspect waivers for the Edge Onboarding Runbook.

Not every campus has the same infrastructure: some have no SIS files, no LAN DNS,
no reliable uplink, no USB disk, no logo yet. A checklist that can only FAIL those
sites is a checklist nobody finishes. Each row here is one capability that an
operator may waive with a written reason (≥12 characters). The reason is the
record; a blank skip is not.

Data that is NOT infrastructure (an owner login, a SECRET_KEY) is not in this
catalog and cannot be waived from the console.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class WaivableAspect:
    """One capability an operator may waive.

    ``key`` is the POST ``skip_aspect`` value. ``form_on_step`` is the runbook step
    that shows the form (defaults to ``key``). ``run_kind`` is the
    ``EdgeOnboardingRun.kind`` written when the skip is recorded.
    """

    key: str
    settings_key: str
    label: str
    hint: str
    run_kind: str = "skip_aspect"
    form_on_step: str = ""

    def form_step(self) -> str:
        return self.form_on_step or self.key


WAIVABLE_ASPECTS: "tuple[WaivableAspect, ...]" = (
    WaivableAspect(
        key="migration_cloud_apply",
        settings_key="migration_cloud_skip_reason",
        label="Migration Cloud",
        hint="No SIS files, already loaded, or this is an empty shell.",
        run_kind="skip_mc",
    ),
    WaivableAspect(
        key="media_branding",
        settings_key="branding_skip_reason",
        label="Logo / branding",
        hint="No logo yet; the platform fallback mark is enough for this campus.",
    ),
    WaivableAspect(
        key="seed_operational_data",
        settings_key="roster_skip_reason",
        label="Operational roster",
        hint="Empty lab or a new campus that has no students yet.",
    ),
    WaivableAspect(
        key="conversion_first_action",
        settings_key="conversion_skip_reason",
        label="Conversion first action",
        hint="Lab box; nobody will save a real attendance, mark, or payment yet.",
    ),
    WaivableAspect(
        key="configure_lan_hostname",
        settings_key="lan_hostname_skip_reason",
        label="LAN hostname / DNS",
        hint="This site reaches the box by IP or a hosts file; there is no school.lan DNS.",
    ),
    WaivableAspect(
        key="enable_configure_sync",
        settings_key="sync_enable_skip_reason",
        label="Cloud pairing / sync",
        hint="Sovereign-only: no reliable uplink, so this box will not pair with the cloud.",
    ),
    WaivableAspect(
        key="verify_and_sync_gate",
        settings_key="sync_gate_skip_reason",
        label="Pre-offline sync gate",
        hint="No uplink; this box will not probe the cloud before going dark.",
    ),
    WaivableAspect(
        key="live_sync_proof",
        settings_key="live_sync_skip_reason",
        label="Live Class-A sync proof",
        hint="No uplink; this campus will not use cloud sync.",
    ),
    WaivableAspect(
        key="box_backup_verified",
        settings_key="box_backup_skip_reason",
        label="Verified box backup",
        hint="Lab box, or a dump already taken by hand onto USB.",
        run_kind="skip_backup",
    ),
    WaivableAspect(
        key="offbox_copy",
        settings_key="offbox_skip_reason",
        label="Off-box backup copy (USB/NAS)",
        hint="No USB disk or NAS at this site; the on-box dump is the only copy.",
        form_on_step="box_backup_verified",
    ),
)

WAIVE_BY_KEY: "dict[str, WaivableAspect]" = {row.key: row for row in WAIVABLE_ASPECTS}


def aspects_shown_on_step(step_key: str) -> "tuple[WaivableAspect, ...]":
    return tuple(row for row in WAIVABLE_ASPECTS if row.form_step() == step_key)
