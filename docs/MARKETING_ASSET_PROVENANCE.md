# Marketing asset provenance (VISUAL-ENGINE-10X)

Loops under `static/marketing/video/loops/` are **illustrative only** — simulated campus labels, no live tenant footage.

| Bucket | Status | Notes |
|--------|--------|-------|
| `sovereign_*` (7 buckets) | Hero-derived regional | `scripts/compress_marketing_loops_from_hero.py` — per-bucket trim + color grade from `hero-home.mp4`; mp4 (H.264) + webm (VP9); each file &lt;800KB; fingerprints must differ (`verify_marketing_loop_buckets_distinct.py`) |
| CI / fresh clone | Committed binaries | `scripts/ensure_marketing_loops.py` uses committed loops when gates pass; no ffmpeg required in CI |
| Operator refresh | Batch ingest | `python scripts/batch_ingest_marketing_loops.py` or per-bucket `python scripts/ingest_marketing_loop.py --bucket sovereign_us --mp4 path/to/loop.mp4` |
| Posters | Generated SVG | `static/marketing/img/posters/*.svg` |

Manifest SOT: `docs/generated/marketing_media_manifest.json` (includes per-bucket `provenance` after regeneration).

Production Playwright: `npm run test:e2e:marketing:visual-engine:production` or GitHub Actions workflow `marketing-visual-engine-production.yml` (`workflow_dispatch`, default `https://runmycampus.com`).
