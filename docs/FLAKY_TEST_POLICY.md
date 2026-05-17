# Flaky Test Policy

**Date opened:** 2026-05-17
**Owner:** Platform engineering
**Marker:** `@pytest.mark.flaky` (declared in `pytest.ini`)
**SOT batch:** 1260 (12-pillar audit P12 follow-up)

## Why

Flaky tests are the most expensive class of CI signal: they erode trust ("if 1 in 5 PRs has a red CI, why look at the red one?") and waste reviewer attention. The platform has historically tolerated flakes silently — this document closes that gap with an explicit quarantine + investigation protocol.

## Definition

A test is **flaky** when:

* It has failed at least **3 times** in **20 consecutive main-branch CI runs**, AND
* The failures are not deterministically reproducible locally with the same SHA + DB state.

A single transient failure is **not** flaky; investigate the root cause first. Most "flakes" are real bugs (timing-sensitive assertions, missing await, shared state) — diagnose before quarantining.

## Workflow

1. **Detection.** Operator notices the test bouncing in CI history. Confirm against the 3-failures-in-20-runs definition.

2. **Quarantine.** Add the `@pytest.mark.flaky` decorator with a short reason:

```python
@pytest.mark.flaky
def test_something_that_bounces():
    """Bounces ~5% on CI — likely race between Celery task pickup
    and assertion. Investigate via ENG-1234."""
    ...
```

3. **CI exclusion.** The default CI matrix runs with `pytest -m "not flaky"`. Quarantined tests still execute under the `RUN_FLAKY_TESTS=1` opt-in nightly job (operator-scheduled) so we keep evidence of whether the flake has gotten better or worse.

4. **Investigation ticket.** Open a tracking issue. The flake stays quarantined for **at most 30 days**. After that:
   * If the root cause is identified + fixed → remove the marker.
   * If the test is genuinely flaky-by-design (e.g. external integration) → either delete or replace with a deterministic fixture.
   * If 30 days pass with no action → the test is deleted. Quarantine is not a graveyard.

5. **Re-run-on-failure.** Operators **MAY** add `pytest-rerunfailures` `--reruns 2` to specific jobs (e.g. browser-driven Playwright) where one transient is acceptable. This is **not** a substitute for quarantine — re-runs hide flakes, they don't fix them.

## Honest carve-outs

- Browser-driving E2E tests (`tests/e2e/*.spec.js`) have higher transient rates than Python unit tests; the platform's Playwright workflows use `retries: 1` by default in `playwright.config.js`. That's a re-run, not a quarantine.
- AI inference tests (`ai_live_ollama`) flake when the Ollama service container is slow to boot; the workflow gates them behind a health-check loop rather than quarantining them.

## CI matrix wire-up

```bash
# Fast PR matrix (default):
pytest -m "not flaky"

# Nightly quarantine check:
RUN_FLAKY_TESTS=1 pytest -m flaky --reruns 0
```

## Current quarantine list

(none — this document opens the protocol; existing tests are not retroactively quarantined.)

## Related artifacts

- [`pytest.ini`](../pytest.ini) — marker declaration
- [`.coveragerc`](../.coveragerc) — coverage thresholds
- [`scripts/restore_drill.py`](../scripts/restore_drill.py) — quarterly DR drill (separate P12 deliverable)
