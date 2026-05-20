# Help center locale corpus runbook (fr / es / pt / ar)

Operator workflow for KB translation families after batch **1356**.

## Surfaces

| Surface | Route | Purpose |
| --- | --- | --- |
| Translation families | `manager.runmycampus.com/help-center/locale-families/` | Group variants, seed drafts, publish all |
| KB admin | Django admin `KBArticle` | Fine-grained editorial control |
| Parent/student policy | `docs/HELP_CENTER_PARENT_STUDENT_POLICY.md` | Audience rules |

## Create a translation family

1. Pick the **canonical** article (usually `en` or locale blank).
2. Open **KB translation families** and set **Canonical** on the source row (writes `translation_of` for siblings).
3. Use **Seed fr/es/pt/ar** to create draft variants sharing `locale_group_id`, or **Add variant** for one locale.

## Publish all locales from one UI

1. Confirm copy in each draft variant (admin or KB article editor).
2. On the family card header, click **Publish all in group** (`publish_group` action).
3. Reindex embeddings if search quality drops: `python manage.py reindex_kb_help_embeddings`.

## Editorial checklist per locale

| Locale | Review focus |
| --- | --- |
| `fr` | Formal school admin tone; CFA/CEMAC fee terms where relevant |
| `es` | Latin American vs Spain glossary — pick one register per article family |
| `pt` | Brazilian vs European Portuguese — align with tenant `LANGUAGE_CODE` |
| `ar` | RTL sanity in HTML body; short titles for mobile |

## Auto-archive stale articles

Monthly Celery beat `portal-archive-stale-kb-articles-monthly` archives published articles with sustained negative helpfulness. Dry-run locally:

```bash
python manage.py archive_stale_kb_articles
python manage.py archive_stale_kb_articles --apply
```

## North-star weekly email

Configure distro (comma-separated):

```bash
export HELP_NORTH_STAR_WEEKLY_EMAIL="ops@example.com,product@example.com"
```

Beat: `portal-help-north-star-weekly-email` (Mondays 06:00 UTC). Manual:

```bash
python manage.py shell -c "from apps.portal.tasks import help_north_star_weekly_email; print(help_north_star_weekly_email())"
```

Attachments: CSV always; PDF when WeasyPrint system libs are installed.

## Lane 2 (hosting)

| Item | Command / note |
| --- | --- |
| Postgres pgvector | `python manage.py migrate_kb_embeddings_to_pgvector` on operator DB |
| Ollama reindex at scale | `portal-reindex-kb-embeddings-weekly` + `reindex_kb_help_embeddings` |
| Playwright | `npm run test:e2e:help-center` with Django + `/etc/hosts` for manager + tenant |
| Marketing KB corpus | Set `MARKETING_KB_TENANT_SLUG` (defaults to `TENANT_EXAMPLE_SLUG`) — global published articles in that tenant schema power `/resources/help-center/search/` |
| Community forums | Enable `portal_features.forums` in site settings; grant `portal.forums` to roles; sidebar **Community** → `/portal/forums/` |
| Unified hub (batch **1359**) | Tenant `/help-center/` includes community lane; marketing `mkt_help_hub` on resources pages; hybrid search falls back to semantic when text empty (needs embeddings + pgvector on operator DB) |
| Forum reply email (batch **1360**) | Celery `portal.notify_forum_reply` on new reply; respects `PortalPreferences.notification_email` |
| Marketing KB categories (batch **1360**) | `/resources/help-center/category/<slug>/` — browse hub links land here, not search-only |
| Forum compose AI (batch **1360**) | KB assistant panel on new topic + reply forms (`forum_compose_ai_assistant`) |

## Verifiers

```bash
python scripts/verify_help_center_tiers.py
python scripts/verify_kb_embedding_coverage.py
python scripts/generate_orchestrator_journey_manifest.py
```
