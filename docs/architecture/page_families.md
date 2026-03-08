# Page families

Shared patterns for dashboard, list, detail, wizard, settings, queue, report, and incident pages. Use these partials so layouts stay consistent and visual debt stays low.

## Partials

All live under `templates/partials/page_families/`:

| Partial | Use |
|--------|-----|
| **title_block.html** | Page title, optional subtitle, optional back link, optional primary/secondary action button. Variables: `title`, `subtitle`, `back_url`, `back_label`, `action_url`, `action_label`, `action_primary`. |
| **action_bar.html** | Row for primary actions (block `action_bar_content`). |
| **filter_row.html** | Wrapper for list filters (block `filter_form`). Add class `page-family-filter-row` to your filter form. |
| **content_card.html** | Card wrapping table or body (block `content_card_body`). Or use class `page-family-content-card` on any card. |
| **empty_state.html** | No items / no data. Variables: `message`, `icon` (Bootstrap Icon class). Block `empty_state_actions` for optional CTA. |
| **loading_state.html** | Spinner + “Loading…” for async content or HTMX placeholders. Use as swap target or inside a placeholder div. |

## Loading state

Use `partials/page_families/loading_state.html` whenever content is loaded asynchronously (e.g. HTMX `hx-swap`). Example:

```html
<div id="my-content" class="min-height-200">
  {% include "partials/page_families/loading_state.html" %}
</div>
```

Then swap `#my-content` with the real content when loaded. For initial page load, show the partial until data is ready, or use a skeleton that matches the final layout.

## Table and status

- Use `.table-family` and `.table-density-comfortable` (or compact/spacious) on list tables.
- Use `.table-status-chip` with modifiers `--success`, `--warning`, `--danger`, `--info`, `--muted` instead of ad-hoc `badge bg-*` for status in tables.

## Reference pages

- **List:** `schools/super_tenant_health.html`, `people/backend_student_list.html`, `schools/super_usage.html`
- **Title + card:** `schools/super_migration_cloud.html`
- **Chart (chart-rules.css):** `schools/super_analytics_overview.html`
