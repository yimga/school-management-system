# Feedback Loop UX Audit

The feedback system is implemented as a low-friction product operations surface, not a standalone contact form.

## Tenant Experience

School users can submit feedback, report issues, request features, view school requests, inspect visible roadmap items, and review released improvements through You Said / We Did.

Teacher, parent, and student routes use narrower category sets. Student feedback is private to the school and moderation-required by default. Parent and student users see only their own submissions.

## Contextual Feedback

Authenticated tenant and control-plane shells include a floating contextual feedback widget. It captures the current route, page title, module namespace, role, tenant, browser metadata, and timestamp server-side.

## Operator Experience

The Voice of Customer dashboard groups inbox feedback, feature requests, roadmap candidates, top pain points, role sentiment, and churn risk signals. Operators can triage, convert feedback to feature requests, and add feature requests to roadmap.

## Accessibility and Safety

- Forms are CSRF-protected.
- Form fields render labels through Django form helpers.
- Buttons have concrete actions.
- No public posting exists for student feedback.
- Roadmap visibility is explicit and private by default.

## Remaining UX Work

The first implementation uses default Django form rendering to stay compact and reliable. A future refinement should hand-layout forms with progressive disclosure, inline privacy copy, and richer mobile field grouping.
