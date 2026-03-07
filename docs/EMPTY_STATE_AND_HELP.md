# Empty State Template & Embedded Help (Phase 19)

## Empty state component

**Template:** `templates/components/dashboard_empty_state.html`

**Usage:**
```django
{% include 'components/dashboard_empty_state.html' with icon='bi-inbox' title='No items' message='Get started by creating your first item.' action_url='/create/' action_text='Create Item' %}
```

**Parameters:**
| Parameter    | Required | Description |
|-------------|----------|-------------|
| `icon`      | No       | Bootstrap Icon class (e.g. `bi-receipt`, `bi-clipboard-data`). |
| `title`     | No       | Heading (default: "No items found"). |
| `message`   | No       | Short explanation and next step. |
| `action_url`| No       | URL for the primary action button. |
| `action_text`| No      | Label for the button (e.g. "Generate fees", "Change filters"). |

**Copy guideline (Phase 19):** Prefer **"No [X] found"** as title and a sentence that tells the user what to do next, with a direct link to the action (e.g. "Click here to add your first student" or "Generate fee invoices to get started.").

**Where it's used:**
- **Finance:** dashboard (invoices/payments), invoices list, payments list, generate fees (no fee plans)
- **Evals:** grade approval list (no requests), evaluation admin (no evaluations match filters)
- **People:** backend student list (no students)
- **Portal:** document library manage (no documents), signature requests manage (no requests)
- **Staff:** contact requests list (no contact requests)

## Global Help link

**Placement:** Portal sidebar footer (all roles) and Knowledge Base in sidebar sections where shown.

**URL:** `{% url 'kb:kb_home' %}` (Help & Knowledge Base).

**Sidebar:** In `templates/partials/portal_sidebar.html`, the footer includes a "Help" link with icon `bi-question-circle` so users can reach the Knowledge Base from any portal page.

## "Was this helpful?" (Phase 13)

**Template:** `templates/components/was_this_helpful.html`

**Usage:** Include after key completion points (e.g. evaluation manager, finance invoices, finance payments).
```django
{% include "components/was_this_helpful.html" with feedback_id="finance-invoices" %}
```

Responses are stored in `localStorage` per `feedback_id` and can be sent to a backend or analytics later. The component shows Yes/No buttons and a "Thanks for your feedback" message; if `showToast` is available, it also shows a toast.

## Error pages (Phase 14.4 – human-readable copy)

- **404:** "We couldn't find that page. It may have been moved or removed, or the link may be wrong."
- **500:** "Something went wrong on our side. Please try again in a moment. If it keeps happening, contact support."
- **403:** "You don't have permission to access this page. If you think you should, ask an admin to check your access."

Custom 403 for admin-forbidden shows a specific message and link to Backend Dashboard.

## Phase 18 – Export and print

- **Export CSV/PDF:** Finance invoices support `?export=csv` and `?export=pdf`; evaluation admin and some reports support CSV/PDF export. One-click export is available on key tables.
- **Print:** `static/css/print.css` provides print styles. Report cards and other reports can use print-friendly media queries; add `@media print` or link `print.css` where needed for "professional when handed to parents" output.
