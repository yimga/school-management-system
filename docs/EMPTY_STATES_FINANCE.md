# Finance empty states

## Summary

Finance dashboard and list pages use the shared `components/dashboard_empty_state.html` component when there is no data, with clear copy and primary actions.

## Usage

- **Component**: `templates/components/dashboard_empty_state.html`  
  Variables: `icon`, `title`, `message`, `action_url`, `action_text` (all optional except sensible defaults for title).

## Where used

| Location | When empty | Title | Action |
|----------|------------|--------|--------|
| Finance dashboard – Recent Invoices | No invoices | "No invoices yet" | "Generate fees" → `finance:generate_fees` |
| Finance dashboard – Recent Payments | No payments | "No payments yet" | "View invoices" → `finance:invoices` |
| Invoices list (`invoices.html`) | No invoices (and not access-gated) | "No invoices found" | "Generate fees" → `finance:generate_fees` |
| Payments list (`payments.html`) | No payments | "No payments recorded" | "View invoices" → `finance:invoices` |

## Invoices list special case

When the user has no finance access (`finance_access_required` and not `finance_access_granted`), the invoices list shows a table with a single explanatory row instead of the empty-state component, to avoid duplicating the alert and to keep the “request access” flow clear.

## Best practice

- Use `{% url 'app:view_name' as empty_action_url %}` and pass `action_url=empty_action_url` so the component always receives a resolved URL.
- Use consistent icon semantics: `bi-receipt` for invoices, `bi-credit-card` for payments.
