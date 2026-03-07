# Marketing homepage assets

Placeholder for marketing landing images:

- `hero-dashboard.png` – hero section dashboard visual (optional; set `MARKETING_HERO_IMAGE_URL` or `hero_dashboard_image_url` in context)
- `product-demo.png` – product demonstration screenshot (optional; set `MARKETING_PRODUCT_DEMO_IMAGE_URL`)
- `migration-studio.png` – migration studio screenshot (optional; set `MARKETING_MIGRATION_STUDIO_IMAGE_URL`)
- Module screenshots for core modules (optional; set `screenshot_url` per module in `core_modules`)

Templates use alt text and fallbacks when URLs are empty.

## Social proof (trust logos and video)

- **Trust logos:** The landing uses `trust_logos` (name + image_url). Replace placeholder entries in `marketing_views.py` with real logo URLs, or drop PNG/SVG files here and reference via `{% static 'images/marketing/partner-logo.png' %}`.
- **Video testimonial:** To add a short testimonial video, set a URL in context (e.g. `marketing_testimonial_video_url`) and add an optional video embed block in `marketing_landing.html` (e.g. `<video>` or third-party embed). No code change required until you add the URL and template block.
