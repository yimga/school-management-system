# Theme Consolidation Implementation Plan

## Phase 1: Fix Child Menu Visibility (Critical)
- Update CSS variables in admin_sidebar_enhanced.css for better contrast
- Fix template defaults in base_site.html
- Add text-shadow for readability

## Phase 2: Remove Finance Inbox Block
- Remove finance inbox block from admin_dashboard.html

## Phase 3: Theme System Unification
- Create Bootstrap compatibility bridge CSS
- Update portal_base.html to sync data-theme and data-bs-theme
- Update backend_base.html to add data-theme attribute
- Update phase7-theme.js to sync both attributes

## Phase 4: CSS Selector Updates
- Update portal-theme-modes.css to support both attributes
