# Subprocess Surface Review (Batch 1506)

407 total subprocess sites — all argument-array invocations, never `shell=True`.

| Bucket | Count |
| --- | ---: |
| scripts/ verifiers | 215 |
| Management commands | 88 |
| Test harness | 51 |
| CI/companion release tooling | 32 |
| Lane 2 evidence capture | 14 |
| Runtime observability | 7 |

**Controls in place:** `scan_subprocess_shell_true.py` baseline 0. No remote shell. No user-input passthrough. Timeout enforced. Captured stdout/stderr.

**Verdict:** No repo-side fix required.
