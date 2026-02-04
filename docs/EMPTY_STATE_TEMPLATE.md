# Empty State Template (Phase 19)

## Reusable component

Use the shared empty-state component so all list/table/widget empty states are consistent and actionable.

### Include

```django
{% include "components/dashboard_empty_state.html" with icon="bi-inbox" title="No items found" message="Optional short description." action_url="/create/" action_text="Create item" %}
```

### Parameters

| Parameter     | Required | Description |
|---------------|----------|-------------|
| `icon`        | No       | Bootstrap Icon class (e.g. `bi-inbox`, `bi-receipt`). |
| `title`      | No       | Heading (default: "No items found"). Prefer specific: "No fee plans yet", "No grade approval requests". |
| `message`    | No       | One or two sentences explaining why it's empty and what to do. |
| `action_url` | No       | URL for the primary action (e.g. create page, list page). |
| `action_text`| No       | Button label (e.g. "Create a fee plan", "Refresh"). |

### Copy guidelines

- **Title:** "No [X] Found" or "No [X] yet" — be specific (e.g. "No invoices found", "No fee plans yet").
- **Message:** Explain cause and next step. Avoid "No data" alone.
- **Action:** Always provide a direct link to the next step (add, create, change filter, view docs).

### Where used

- Finance: Generate Fee Invoices (no fee plans), Invoices list, Payments list, Finance dashboard.
- Evals: Grade approval list (no requests).
- Other list/table views: use the same component and follow this template.
