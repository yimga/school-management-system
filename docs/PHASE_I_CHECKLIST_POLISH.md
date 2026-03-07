# Phase I Plan Checklist (optional / polish)

**Phase I — Scale:** Already implemented. Optional: full migration to schema-per-tenant when ready (see docs/PHASE_I_SCALE_GAP_ANALYSIS.md, `phase_i_gap_analysis`, `migrate_schools_to_tenants`).

## Done

- **DB health check:** `python manage.py db_health_check` (SELECT 1); exits 0 on success, 1 on failure. Command: `apps.observability.management.commands.db_health_check`.
- **run_health_check.sh:** `scripts/release/run_health_check.sh` invokes the command. Used in `scripts/release/render_predeploy.sh` after migrations and before service start (Render/Gunicorn).
- **Docker entrypoint example:** `scripts/release/docker_entrypoint_phase_i.sh.example` — when `USE_DJANGO_TENANTS=1`, runs migrate_schemas (shared + tenant), then `db_health_check`, then Gunicorn. Copy to `docker_entrypoint.sh` and use as ENTRYPOINT in Dockerfile.
- **Docs:** `docs/PHASE_I_MULTI_REGION_AND_DEPLOY.md` documents deploy health check and optional Docker entrypoint.

## Wiring

- **Render:** Predeploy runs migrate, seeds, integration_preflight, then `scripts/release/run_health_check.sh`, then Gunicorn. No extra wiring needed.
- **Docker:** Add to Dockerfile: `COPY scripts/release/docker_entrypoint_phase_i.sh.example /app/docker_entrypoint.sh`, `RUN chmod +x /app/docker_entrypoint.sh`, `ENTRYPOINT ["/app/docker_entrypoint.sh"]` (or use the example content in your existing entrypoint).
