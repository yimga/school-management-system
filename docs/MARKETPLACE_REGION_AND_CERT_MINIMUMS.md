# Marketplace certification & region pack minimums (SOT §12 / §0.3)

**Third-party listings:** Each **MarketplaceListing** supports **security_review_status** and **certification_status** (see `apps/marketplace/models.py`). Governance flow: `submit_marketplace_review` in `apps/marketplace/services.py` — listing → security → certification pipeline.

**Minimum bar (enforced in ops, not hard-coded counts):**

| Gate | Minimum |
|------|---------|
| First-party apps in catalog | Per `MARKETPLACE_SEED_TARGETS` / `test_marketplace_catalog_minimums` |
| Third-party with certification | At least one **certification** review type exercised before prod third-party publish |
| Region packs | Per geography wedge (7–13): at least one **RegionConfig** + blueprint seed per active region GTM |

**Clever/ClassLink:** Native roster remains partnership-gated; OneRoster + Bearer is the certified district path until vendor credentials exist.
