# RunMyCampus Architecture Map Pack (Blueprint E)

This folder contains the architecture artifacts requested by the RunMyCampus blueprint.

| File | Description |
|------|-------------|
| [apps.txt](apps.txt) | List of Django apps (from INSTALLED_APPS) |
| [urls.txt](urls.txt) | URL map (tenant and public roots) |
| [migrations.txt](migrations.txt) | Output of `python manage.py showmigrations` |
| [tenancy.md](tenancy.md) | Where tenant is set, schema switching, shared vs tenant tables, multi-DB routing |
| [policy_injection.md](policy_injection.md) | Where Policy Registry / tenant context is injected |
| [cache_keys.md](cache_keys.md) | Tenant-scoped cache keys (World Engine §8); audit table and intentional globals |
| [platform_north_star.md](platform_north_star.md) | North Star layers: Control plane, Tenant plane, Marketplace, Workflow, Metadata, Observability, Edge, Data plane, Compliance |
| [audit_branching_and_isolation.md](audit_branching_and_isolation.md) | C2/C3: Tenant branching audit and media/cache/tasks/search isolation |
| [dominance_sweep_checklist.md](dominance_sweep_checklist.md) | A3, A5, A6, A7 checklist and references |

See also: [../architecture_map.md](../architecture_map.md) (single map + Mermaid).

To regenerate artifacts (migrations, apps list, URLs) run from repo root:

```bash
bash scripts/regen_architecture_docs.sh
```

Or manually: `python manage.py showmigrations > docs/architecture/migrations.txt`

Optional: model graph with django-extensions + graphviz:  
`python manage.py graph_models -a -o docs/architecture/models.png`
