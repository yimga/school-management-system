# Surface and Productization

Date: 2026-03-08

## Summary

Several product surfaces look broader than the operating system behind them. This is most visible in onboarding, marketplace, and the public-facing product language around installability and migration.

## 1. Onboarding Surface

Observed:

- `templates/schools/onboard_wizard.html:12` explicitly describes itself as a stable shell while provisioning evolves
- country selection is hardcoded to four entries at `templates/schools/onboard_wizard.html:17-23`

Assessment:

- the surface is useful as a placeholder
- it should not be treated as evidence that onboarding is already blueprint-driven or world-engine-ready

## 2. Marketplace Surface

Database snapshot:

| Metric | Count |
|---|---:|
| publishers | 1 |
| apps | 4 |
| listings | 4 |
| approved listings | 4 |
| reviews | 0 |
| installations | 0 |
| blueprint packs | 15 |
| policy bundles | 10 |
| tenant blueprints | 0 |
| workflow packs | 7 |
| dashboard packs | 6 |

Assessment:

- the marketplace has real catalog structure
- it does not yet have a functioning install, review, or tenant activation economy

What this means:

- catalog and governance models exist
- the lived product loop is not active
- the UI should be framed as preview or internal-control-plane unless installations and tenant blueprint activation become real

## 3. Registry Readiness

Registry snapshot:

| Registry | Count |
|---|---:|
| countries | 249 |
| education levels | 3 |
| education system types | 10 |
| currencies | 259 |
| institution types | 0 |
| document types | 9 |
| fee categories | 8 |
| grade scales | 5 |

Assessment:

- country and currency registries are mature enough to support generalized onboarding choices
- `InstitutionTypeRegistry` being empty is a critical gap because blueprint selection, product packaging, and provisioning identity should depend on it

## 4. Frontend Shell Surface

Observed:

- `templates/base.html:80-99` pulls a large fixed CSS stack on the base shell
- `templates/base.html:215-230` still fixes font and global background decisions centrally
- `templates/partials/portal_sidebar.html` still contains major hardcoded UX branches

Assessment:

- the repo has multiple frontend systems layered at once
- that creates the appearance of richness, but also makes theming, performance, and behavior drift harder to control

## 5. Migration Product Surface

Observed:

- migration wizard supports only two import families
- `MigrationRun` exists, but the live database has zero runs and zero rollback-ready runs

Assessment:

- the migration surface is not yet a repeatable product capability
- it is best understood as an operator-assisted import path

## Productization Verdict

The repo has built many of the nouns of a platform: packs, listings, bundles, registries, shells, hubs, and wizards. What is still missing in several areas is the verb layer:

- install
- activate
- apply
- migrate
- review
- rollback
- govern

The next stage should focus on operational loops, not more surface area.
