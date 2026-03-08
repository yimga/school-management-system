# Marketing premium bar ($1B company feel)

RunMyCampus public marketing (runmycampus.com) should feel like a **$1 billion company front**: premium, trustworthy, polished, editorial, confident, conversion-smart.

## Quality bar

- **Premium:** Typography and spacing from design tokens; no ad-hoc font sizes or margins.
- **Trustworthy:** Trust band, credibility line, and security/compliance section prominent; no clutter.
- **Polished:** Navbar with subtle elevation and clear CTA; hero and sections with consistent rhythm.
- **Editorial:** Clear hierarchy (hero > section heading > lead > body); one primary CTA per block.
- **Conversion-smart:** Primary CTA obvious (Start Free Trial / Book demo); sticky CTA bar on scroll; SEO and canonical in place.

## What we use

- **Surface:** `body.marketing-surface` (set in `schools/marketing_base.html` and `schools/marketing_page.html`) so `surface-themes.css` Marketing theme applies.
- **Tokens:** `--type-hero`, `--type-section`, `--type-body`, `--type-micro`, `--mkt-spacing-section` from design-tokens and surface-themes.
- **Templates:** `marketing_base.html` (navbar, chrome), `marketing_landing.html` (homepage), `marketing_page.html` (product, pricing, security, etc.).
- **CSS:** `marketing-home.css` (scoped under `.marketing-home` on landing); same file loaded on inner pages for token consistency.

## Checklist for new marketing pages

1. Extend `marketing_base.html` (for nav) or `base.html` with `{% block body_class %}marketing-surface{% endblock %}`.
2. Include `marketing-home.css` in extrastyle if the page uses section/heading/lead patterns.
3. Use semantic headings (h1 for page title, h2 for sections); prefer token-driven classes (e.g. section-heading, section-lead).
4. One primary CTA per section; secondary actions styled as outline.
5. Keep canonical, meta description, and structured data (SEO) in extrahead.
6. No one-off cards or sections that ignore the shared section/card styles.

## Where it’s applied

- Homepage: `marketing_landing.html` (hero, trust band, sections, final CTA).
- Inner pages: `marketing_page.html` (product, pricing, security-compliance, trust-center, blog, etc.) with same surface and typography tokens.
