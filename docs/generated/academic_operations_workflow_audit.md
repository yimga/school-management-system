# Academic operations workflow audit

**Generated:** 2026-05-20T03:15:50.248666+00:00
**OK:** True

## Apps

- people: installed=True routes=True services=True
- academics: installed=True routes=True services=True
- evals: installed=True routes=True services=True
- school_events: installed=True routes=True services=True
- schoolops: installed=True routes=True services=False
- student360: installed=True routes=True services=True
- reports: installed=True routes=True services=True
- emis: installed=True routes=True services=True
- requests: installed=True routes=True services=True
- communication: installed=True routes=True services=True

## Query hotspots (select_related counts)

- academics_select_related: 33
- emis_select_related: 8
- evals_select_related: 33
- people_select_related: 13
- reports_select_related: 21

## Workflow loop (P4)

- domain_event_bridge_maps_conflict: True
- offline_action_conflict_in_catalog: True
- offline_queue_emits_conflict_event: True
- playbook_offline_conflict: True

## EMIS

- emis_export_service: True
- emis_field_mapping_model: True
- emis_tests: True
