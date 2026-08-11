# Tenant Configuration Autopilot v4

## Purpose and safety boundary

Autopilot converts a small progressive signup profile into an explainable, versioned tenant-configuration recommendation. It removes routine setup decisions while keeping every paid, governed or irreversible step review-gated. A recommendation never grants an entitlement, installs a blueprint or activates a migration by itself.

## Architecture

1. `templates/schools/signup_school.html` collects four required operating signals and keeps nuance under optional progressive disclosure.
2. `static/js/rmc-signup-balanced-v3.js` provides a resilient, non-binding browser preview. Failure does not lose form data and the server remains authoritative.
3. `apps/schools/signup_views.py` owns HTTP parsing, country/cycle validation, response handling and persistence orchestration.
4. `apps/schools/onboarding_profile.py` is the typed trust boundary. It validates choices, bounded integers and list values, returns structured issues, and supports strict new-signup or forgiving legacy-repair modes.
5. `apps/schools/onboarding_recommendations.py` is a pure deterministic policy engine. It resolves real versioned blueprint catalog contracts and composes modules, compliance, identity, continuity, migration and the smallest justified plan.
6. `ensure_school_recommendations()` persists only an unconfirmed recommendation. If a confirmed or operator-locked manifest receives changed inputs, the current decision is preserved and a `recommendation_candidate` is created for review.

## Progressive input contract

The first interaction asks only:

- campus structure: one campus, network or delegated district;
- operating model: day, boarding or mixed;
- connectivity: reliable, intermittent, offline-first or mixed by campus;
- learner scale: under 1,000, 1,000–4,999 or 5,000+.

Optional nuance includes exact capacity/campus/staff counts, funding, LMS, transport/boarding/meals/clinic/athletics, payment and aid complexity, assessment model, identity federation, data residency, accessibility, migration complexity, automation preference and go-live timing. Country, education cycles, languages, current SIS and imported data domains are preserved from the wider signup flow.

## Validation and failure behavior

- Explicit unsupported choices, invalid integers, out-of-range values and unknown list items are errors during signup and prevent tenant creation.
- Invalid stored legacy values are repaired to conservative defaults and retained as structured warnings for review.
- Capacity is bounded to 1,000,000 learners, staff to 1,000,000 and campuses to 10,000.
- Network/district profiles without a count infer two campuses. A selected learner band without an exact capacity receives a conservative documented capacity estimate.
- Duplicate list entries are removed without changing first-seen order.
- Empty profiles resolve to safe single-school, balanced-automation, no-migration defaults and never auto-entitle a plan.
- Browser-preview errors display a recoverable message; server-side validation and recommendation still run on submit.

Each manifest contains an input fingerprint, engine/version, normalized profile, validation issues, confidence score, missing-input reasons, rule IDs, alternatives, blueprint contract versions, recommendation flags, review state and subscription upgrade boundary.

## Extension rules

Add a new signal only when it changes a blueprint, module, compliance profile, migration path or plan. Update the `InstitutionProfile` type, allowed choices/defaults, HTML control, browser preview, deterministic rule, documentation and tests together. Do not read unvalidated request or JSON values directly inside recommendation rules.

## Tests

The focused contract lives in:

- `apps/schools/tests/test_onboarding_profile.py`
- `apps/schools/tests/test_onboarding_recommendations.py`
- `apps/schools/tests/test_backfill_onboarding_recommendations.py`

Tests cover malformed inputs, range limits, empty defaults, legacy repair, inference, nuanced module composition, real blueprint resolution, signup persistence, no-creation on invalid input, manifest backfill and confirmed-decision preservation.
