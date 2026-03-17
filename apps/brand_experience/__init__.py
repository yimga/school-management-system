# Bounded-context: themes, logos, colors, portal look/feel (GAP.12 / IV.2–IV.3).
# Theme/experience ownership: models (ThemePack, BrandProfile, BrandSettings) live here;
# resolution flows via siteconfig.branding.resolve_brand_profile (uses these models).
# Runtime step 7 (branding) consumes that resolution so portal and dashboard share a single
# token/layout design system (BrandingContext).
# For unified theme tokens use: from apps.brand_experience.resolvers import get_unified_theme_tokens
