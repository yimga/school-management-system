# Luxury UI Surface Audit

**Generated:** 2026-06-15T21:10:14.158628+00:00
**Score:** 14/15
**Verdict:** ULTRA-LUXURY

## Summary

- High-impact templates scanned: 254
- Inline style hits: 56 (violations: 1)
- Unwrapped tables: 8 (violations: 0)
- Missing table-family: 7 (violations: 0)
- Missing ds-btn usage: 120 (violations: 0)
- Shell consistency failures: 0
- Overflow-prone CSS files: 5
- Non-token literals (spacing/radius/shadow): {'spacing': 3, 'radius': 0, 'shadow': 26}
- Duplicate component-system conflicts: 0
- Unsafe direct brand text color hits: 0
- RTL violations: 0
- Debug-surface hits: 0
- Zero-click major surfaces failing inheritance/exempt: 0
- Shell viewport OK: True
- Luxury gate (min 13): PASS
- State completeness matrix: 19 major templates

## Dimension scores (/15 total)

- **action_clarity:** 3/3
- **click_depth:** 2/2
- **component_consistency:** 1/2
- **layout_consistency:** 2/2
- **mobile_ux:** 2/2
- **overflow_safety:** 2/2
- **state_handling:** 2/2

## Notes

- This is a static audit focused on integration risk signals.
- It is intended to complement verifier/test gates, not replace runtime visual QA.
