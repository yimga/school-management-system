# Design System Audit

**OK:** True

## Governed CSS files

- `static/css/design-tokens-luxury.css`
- `static/css/design-system-unified.css`
- `static/css/platform-high-end.css`
- `static/css/design-system-phase2-enforcement.css`

## Raw literal counts (current)

- `static/css/design-tokens-luxury.css`: spacing=0, radius=0, shadow=0, 600ms=0
- `static/css/design-system-unified.css`: spacing=6, radius=0, shadow=2, 600ms=0
- `static/css/platform-high-end.css`: spacing=14, radius=1, shadow=1, 600ms=0
- `static/css/design-system-phase2-enforcement.css`: spacing=0, radius=0, shadow=0, 600ms=0

## Token conflicts found

- **spacing**: --token-space-* / --spacing-*, --luxury-gap*, --lux-space-*
- **typography**: --font-size-* / --type-*, --luxury-font-*, --lux-type-*
- **radius**: --radius-*, --platform-premium-radius*, --luxury-btn-radius / --lux-radius-*
- **shadow**: --shadow-*, --platform-premium-shadow*, --luxury-shadow-* / --lux-shadow-*
- **color**: --color-*, --luxury-*, --lux-color-*
- **motion**: --transition-* / --motion-*, --luxury-motion-*, --lux-motion-*
