# Embedded Help & Empty State Template (Phase 19)

## Global Help

- **Header:** Portal and backend show a Help icon (question-circle) in the top bar linking to the Knowledge Base (`kb:kb_home`). See `portal_base.html` and any header partial that includes it.
- **Sidebar:** The portal sidebar includes a **Help** link in the footer (Phase 19) so users can reach the Knowledge Base from any page. Teacher and staff sidebars also list "Knowledge Base" under Account / relevant section where `portal_sidebar_items` or static sidebar is used.
- **Use:** Ensure all new templates that extend `portal_base` or `backend_base` inherit this. For page- or section-level help, add an optional link next to the page title, e.g. `<a href="{% url 'kb:kb_home' %}?topic=invoices"><i class="bi bi-question-circle"></i></a>`.

## Empty State Template

The project uses a **reusable empty state component** so lists and dashboards show a consistent, actionable message when there is no data.

### Component

- **Template:** `templates/components/dashboard_empty_state.html`
- **Usage:**
  ```django
  {% include "components/dashboard_empty_state.html" with icon="bi-inbox" title="No items found" message="Get started by creating your first item." action_url="/create/" action_text="Create Item" %}
  ```
- **Variables:**
  - `icon` (optional): Bootstrap Icon class, e.g. `bi-receipt`, `bi-credit-card`.
  - `title`: Heading (default: "No items found").
  - `message` (optional): Short description.
  - `action_url` (optional): URL for the primary action (e.g. "Add student", "Generate fees").
  - `action_text` (optional): Button/link label for `action_url`.

### Copy guideline

- **Title:** "No [X] found" or "No [X] yet" (e.g. "No invoices found", "No payments recorded").
- **Message:** One sentence explaining why it’s empty and what will make data appear, or what the user can do next.
- **Action:** When there is a clear next step, provide a direct link (e.g. "Add your first student", "Generate fees", "View invoices"). Avoid generic "Refresh" unless that’s the only option.

### Where it’s used

- Finance: invoices list, payments list, generate fees (no fee plans), dashboard (no invoices/payments).
- Evals: grade approval list (no requests).
- Use the same pattern for any new list or dashboard that can be empty so the experience is consistent and actionable.

## Placement checklist for new pages

1. **Help:** If the page is under portal/backend, the global Help link in header and sidebar is enough unless you add a topic-specific link.
2. **Empty state:** For any view that renders a list or table that can be empty, use `dashboard_empty_state` with title, message, and (if applicable) action_url/action_text instead of a bare "No data" or empty table only.
