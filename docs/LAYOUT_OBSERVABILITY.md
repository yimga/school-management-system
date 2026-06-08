# Layout observability

RunMyCampus uses CSS-first responsive behavior. `ResizeObserver` is a bounded
measurement and telemetry mechanism; it is not a layout engine and must never
shrink fonts, apply transforms, or rewrite tenant content.

## Canonical runtime

- `templates/partials/rmc_viewport_engine.html` is the one shell mount.
- `static/js/rmc-viewport-engine.js` publishes visual viewport width/height as
  CSS custom properties and retains the existing A/B/C capability classes.
- `static/js/rmc-layout-observer.js` observes at most 160 explicit or canonical
  operational surfaces. It measures responsive wrappers and opt-in
  `[data-rmc-layout-observe]` nodes.
- `static/js/rum-beacon.js` adds one versioned aggregate snapshot to the
  existing RUM beacon.
- `apps.platform_runtime.layout_observability` is the server-side schema and
  privacy boundary.
- `RMC_LAYOUT_OBSERVABILITY_ENABLED=0` is the deployment kill switch; it
  suppresses the observer while leaving the existing CSS layout untouched.

The observer may set `data-rmc-layout-overflow="inline|block|both"` for
diagnostics. It does not set presentation styles. Existing responsive table,
row-detail drawer, shell scroll, RTL, and design-token contracts remain the
owners of visible behavior.

## Data contract

Schema version `1` accepts only:

- observed and overflow counts;
- maximum inline/block overflow in pixels;
- A/B/C/unknown viewport class;
- `ltr` or `rtl` direction;
- visual viewport width and height.

The browser does not send text, HTML, selectors, element IDs, CSS classes,
tenant identifiers, record identifiers, or component content. The ingest
sanitizer rejects unknown schema versions, unknown keys, negative values,
non-numeric values, and impossible child counts.

## Operational use

The RUM aggregate exposes sample count, overflow-bearing beacon count, total
observed/overflow surfaces, maximum overflow deltas, and viewport-class
distribution. Use those aggregates to identify a route/device family for
reproduction, then fix the canonical CSS or table/drawer grammar. Never add
automatic font compression as a response.

Run:

```text
npm run verify:layout-observability
```

This is repository proof. Real-browser locale, RTL, zoom, virtual-keyboard,
and target-device evidence remains part of deployment/pilot certification.
