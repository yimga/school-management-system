# RunMyCampus World-Class Experience Standard

Status: UI/UX WORLD-CLASS TRANSFORMATION - ACTIVE  
Scope: public marketing, platform command center, configuration, governed installation, tenant school setup, migration, app catalog, billing, money, and role workspaces.

## Core Feel

RunMyCampus should feel calm, premium, visual, guided, trustworthy, fast, spacious but not empty, role-specific, low-click, and accessible. The product should communicate operational confidence without hiding complexity or pretending external readiness exists.

## Layout Model

Every important page must have one clear purpose, one primary action, a strong page header, a visual summary strip, progressive disclosure for secondary detail, grouped secondary actions, a risk/action rail, clear empty states, and clear status language.

Above the fold must answer:

- What is this page for?
- Who is it for?
- What is the primary action?
- What is the top risk or blocker?
- What should the user do next?

## Visual System

Use the premium shell, existing design tokens, and shared world-class components before adding one-off markup. Pages should use card hierarchy, metric hierarchy, visual icons, role-based color tokens, clear status chips, timelines, progress meters, guided checklists, and product moments that show the operating system rather than a wall of controls.

Required components:

- Page Hero Header: title, subtitle, user role, primary action, secondary action, status pill, and breadcrumb where relevant.
- Product Moment Card: visual, outcome, status, and action.
- Command Summary Strip: three to five metrics including risk, readiness, and blockers.
- Action Rail: primary action, next best action, support action, and documentation link where available.
- Readiness Meter: setup, implementation, payment, migration, blueprint, and pack readiness.
- Timeline: audit trail, change request, workflow run, migration run, and install history.
- Empty State: explanation, primary action, safe secondary action, and no dead ends.
- Risk / Blocker Card: severity, owner, why blocked, next step, and external vs repository distinction.
- Visual Section Header: icon, short purpose, and action.
- Guided Stepper: Preview -> Simulate -> Impact -> Request Approval -> Schedule -> Apply -> Monitor -> Rollback.

## Accessibility

Accessibility is required. Each page must preserve semantic headings, keyboard focus, color contrast, visible focus states, aria labels where needed, non-empty link and button names, table captions for data tables, skip link behavior, mobile and zoom support, and reduced-motion safety. Icon-only actions must include a label or accessible name.

## Interaction Rules

Do not create dummy actions. Critical actions cannot be hidden. Destructive actions require confirmation. External blockers must be shown plainly. Tenant and platform boundaries must be visible. Users must always know what next step is safe.

## Dashboard Rules

Above the fold:

- Page title
- Status summary
- Top risks
- Primary action
- Recent activity or readiness signal

Below the fold:

- Detail tables
- Secondary modules
- Advanced configuration
- Raw fallback links where appropriate

## Table Rules

Avoid giant raw tables. Summarize first, then provide filters/search, intentional pagination or scrolling, clear status/action columns, captions, and empty states that explain what happens next.

## Mobile Rules

Mobile layouts must stack cleanly, avoid horizontal overflow, preserve large tap targets, group forms into steps, and only use sticky primary actions when they materially reduce effort.

## Proof Standard

Labels must stay honest:

- UI/UX WORLD-CLASS TRANSFORMATION - ACTIVE: implementation is underway.
- WORLD-CLASS UX PARTIAL: static and targeted tests pass but browser/live proof is incomplete.
- WORLD-CLASS UX READY - LOCAL: local browser QA and accessibility proof pass.
- WORLD-CLASS UX READY - RENDER: live Render parity is explicitly tested and passes.

Do not claim full-market category-defining, live PSP readiness, SOC 2/ISO/PCI certification, settlement proof, or Render parity from repository-only evidence.
