# Marketing analytics and conversion events

**Purpose:** Define conversion events for the public marketing surface so analytics (e.g. GTM) can track funnel: visit → discovery → signup → activation.

## Data layer (template attributes)

All primary CTAs use consistent attributes for tracking:

- **`data-cta`**: `primary` | `demo` | `secondary`
- **`data-page`**: page context (e.g. `home`, `footer`, `pricing`, `case-studies`, `header`, or the active nav slug such as `product`, `10-reasons`)

These are present on:

- Homepage: hero CTAs, sticky CTA bar, get-started step CTA, final CTA
- Footer: Start Free Trial, Book demo
- Header: Start Free Trial
- Marketing subpages: detail hero CTAs and footer CTAs
- Compare, marketplace, role, topic, migrate pages

When the marketing analytics script is enabled (`marketing_analytics_script_url`), it reads these attributes to push events.

## Conversion events (defined)

| Event | When | Suggested GTM trigger / use |
|-------|------|-----------------------------|
| **visit** | Page view on any public marketing page | Default page view; segment by path or `data-page` |
| **discovery** | User engages with discovery (role, challenge, segment, compare, resources) | Click on "For your role", "Solve by challenge", Compare, Resources, 10 Reasons |
| **signup** | User starts free trial (click "Start Free Trial" / "Start free") | Click on element with `data-cta="primary"` to signup URL |
| **activation** | User completes signup/onboarding or first login | Backend/tenant event; fire from app after verification or first login |

## Implementation notes

- **Marketing script (required when analytics enabled):** Set `MARKETING_ANALYTICS_SCRIPT_URL` and `MARKETING_ANALYTICS_PRECONNECT_ORIGIN` in settings to load the third-party script; preconnect is output in landing `extrahead`.
- **No PII in data-cta/data-page:** Only CTA type and page slug; no user data.
- **Activation:** Tracked outside marketing (e.g. in tenant app or post-signup redirect); not in marketing templates.

## Conversion dashboard

Staff can view funnel metrics (visit, discovery, signup, activation) and channel breakdown at:

- **URL:** `/funnel-dashboard/` (name: `marketing_funnel_dashboard`)
- **Access:** Staff only (`@staff_member_required`). Log in to the manager or public site as staff, then open the URL on the same host.

Use this dashboard to verify events are being recorded and to analyze UTM performance.

## Checklist

- [x] Conversion events defined (visit, discovery, signup, activation).
- [x] CTAs tagged with `data-cta` and `data-page` across homepage, footer, nav, and key landings.
- [x] Funnel dashboard available at `/funnel-dashboard/` for staff.
- [ ] GTM (or equivalent) configured to fire events from these attributes (client responsibility).
