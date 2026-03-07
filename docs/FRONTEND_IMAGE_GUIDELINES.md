# Frontend image guidelines

Short rules so every image stays fast and stable (CLS, LCP, accessibility). Apply to all new and updated templates.

---

## 1. Always set dimensions

- **Every `<img>` must have `width` and `height`** (in pixels). This reserves space and keeps CLS &lt; 0.1.
- Use the **intrinsic size** of the asset when known (e.g. logo 34×34, avatar 48×48). For user uploads, pick a sensible default (e.g. 120×120 for profile photos).
- You can still scale with CSS (`max-width: 100%`, `object-fit`, etc.); the attributes only fix aspect ratio and layout.

**Example**

```html
<img src="{{ SITE_LOGO_URL }}" alt="Logo" width="34" height="34" decoding="async" ...>
```

---

## 2. Loading and decoding

- **Above-the-fold / LCP** (e.g. header logo, hero image):  
  `loading="eager"` (or omit; default is eager) and `fetchpriority="high"` where it’s the main visual.
- **Below-the-fold**:  
  `loading="lazy"` and `decoding="async"`.
- Prefer `decoding="async"` on all images so decoding doesn’t block painting.

---

## 3. Alt text

- **Decorative** (e.g. sidebar icon with no meaning): `alt=""`.
- **Content** (logo, profile, report graphic): short, accurate `alt` (e.g. `alt="Logo"`, `alt="{{ request.user.get_full_name }}"`).

---

## 4. Checklist for new/updated templates

- [ ] Every `<img>` has `width` and `height`.
- [ ] LCP image has `fetchpriority="high"` or `loading="eager"`; others use `loading="lazy"`.
- [ ] All use `decoding="async"` where supported.
- [ ] Alt text is present and correct (or `alt=""` for decorative).

Optional: run `npm run check:images` (or `python scripts/check_image_dimensions.py`) to catch missing dimensions before commit.
