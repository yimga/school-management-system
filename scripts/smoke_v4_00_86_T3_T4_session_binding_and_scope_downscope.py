"""v4.00.86 Wave 18 Targets 3 & 4 - SAML SessionIndex binding + OAuth scope downscoping smoke.

T3 (SAML SessionIndex registry):
  1. register_saml_session_index w/ valid inputs -> True
  2. lookup_session_key_for_session_index returns the key
  3. unregister_by_session_index returns True; subsequent lookup -> None
  4. Empty inputs return False / None
  5. Eviction at cap: register 10001 distinct indices; first one is gone
  6. saml_session_registry_summary returns counts only - NEVER actual session keys
  7. reset_saml_session_registry clears

T4 (OAuth scope downscoper):
  8. push_grade against ("url:GET|/api/v1/courses", "url:POST|/api/v1/assignments")
     returns tuple containing only the POST (write) scope
  9. read_roster against ("read", "write") returns ("read",)
 10. Unknown operation returns full default scope tuple
 11. Empty default_scopes returns empty tuple
 12. supported_operations returns a non-empty tuple of strings

Run:
    python scripts/smoke_v4_00_86_T3_T4_session_binding_and_scope_downscope.py
"""
from __future__ import annotations

import os
import sys

# Ensure repo root is on sys.path when invoked from anywhere.
_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

# Minimal Django settings hook - apps/api/saml.py imports django.conf.settings
# for env-var lookups, so Django needs to be at least minimally configured.
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
try:
    import django  # noqa: WPS433
    django.setup()
except Exception:  # noqa: BLE001
    pass

from apps.api import saml as S  # noqa: E402
from apps.integrations_marketplace import oauth_scope_downscoper as D  # noqa: E402


_PASS: list[str] = []
_FAIL: list[str] = []


def _check(label: str, ok: bool, detail: str = "") -> None:
    if ok:
        _PASS.append(label)
        print(f"  PASS  {label}")
    else:
        _FAIL.append(f"{label}: {detail}")
        print(f"  FAIL  {label}: {detail}")


# ---------------------------------------------------------------------------
# T3 - SAML SessionIndex registry
# ---------------------------------------------------------------------------

print("\n[T3] SAML SessionIndex <-> django session_key registry")

# Case 1: register w/ valid inputs returns True
S.reset_saml_session_registry()
got = S.register_saml_session_index(session_index="idx1", django_session_key="key1")
_check("T3.1 register returns True", got is True, f"got={got!r}")

# Case 2: lookup returns the key
got = S.lookup_session_key_for_session_index("idx1")
_check("T3.2 lookup returns 'key1'", got == "key1", f"got={got!r}")

# Case 3: unregister returns True + subsequent lookup returns None
got_unreg = S.unregister_by_session_index("idx1")
got_lookup = S.lookup_session_key_for_session_index("idx1")
_check(
    "T3.3 unregister True + subsequent lookup None",
    got_unreg is True and got_lookup is None,
    f"unreg={got_unreg!r} lookup={got_lookup!r}",
)

# Case 4: Empty inputs return False / None
S.reset_saml_session_registry()
case4a = S.register_saml_session_index(session_index="", django_session_key="key2")
case4b = S.register_saml_session_index(session_index="idx2", django_session_key="")
case4c = S.lookup_session_key_for_session_index("")
case4d = S.unregister_by_session_index("")
_check(
    "T3.4 empty inputs -> False/None across all helpers",
    case4a is False and case4b is False and case4c is None and case4d is False,
    f"reg_empty_idx={case4a!r} reg_empty_key={case4b!r} lookup_empty={case4c!r} unreg_empty={case4d!r}",
)

# Case 5: Eviction at cap. Register CAP+1 distinct indices; first should be gone.
S.reset_saml_session_registry()
cap = S._SESSION_INDEX_REGISTRY_CAP
for i in range(cap + 1):
    S.register_saml_session_index(
        session_index=f"idx_{i}",
        django_session_key=f"key_{i}",
    )
first_gone = S.lookup_session_key_for_session_index("idx_0") is None
last_present = S.lookup_session_key_for_session_index(f"idx_{cap}") == f"key_{cap}"
size_at_cap = S.saml_session_registry_summary()["registered_sessions"] == cap
_check(
    "T3.5 LRU eviction at cap: oldest evicted, newest retained, size == cap",
    first_gone and last_present and size_at_cap,
    f"first_gone={first_gone} last_present={last_present} size_at_cap={size_at_cap}",
)

# Case 6: Summary returns counts only - NEVER actual session keys.
# Re-seed with a recognisable key and check the summary dict + its repr.
S.reset_saml_session_registry()
S.register_saml_session_index(
    session_index="idx_secret",
    django_session_key="REDACTED_BEARER_LIKE_KEY_xyz_42",
)
summary = S.saml_session_registry_summary()
summary_repr = repr(summary)
has_counts = (
    summary.get("registered_sessions") == 1
    and summary.get("cap") == S._SESSION_INDEX_REGISTRY_CAP
)
no_key_leaked = (
    "REDACTED_BEARER_LIKE_KEY_xyz_42" not in summary_repr
    and "idx_secret" not in summary_repr
)
_check(
    "T3.6 summary returns counts only, never bearer-equivalent keys",
    has_counts and no_key_leaked,
    f"summary={summary_repr}",
)

# Case 7: reset clears.
S.reset_saml_session_registry()
post_reset = S.saml_session_registry_summary()
_check(
    "T3.7 reset_saml_session_registry empties the map",
    post_reset["registered_sessions"] == 0,
    f"post_reset={post_reset!r}",
)


# ---------------------------------------------------------------------------
# T4 - OAuth scope downscoper
# ---------------------------------------------------------------------------

print("\n[T4] OAuth scope downscoping per session")

# Case 8: push_grade against canvas-shaped scopes -> only POST (write) scope.
canvas_scopes = ("url:GET|/api/v1/courses", "url:POST|/api/v1/assignments")
got = D.downscope_for_operation(
    provider="canvas",
    operation="push_grade",
    default_scopes=canvas_scopes,
)
ok8 = (
    isinstance(got, tuple)
    and len(got) == 1
    and "POST" in got[0]
    and "GET" not in got[0]
)
_check("T4.8 push_grade keeps POST write scope, drops GET read scope", ok8, f"got={got!r}")

# Case 9: read_roster against ("read", "write") -> ("read",)
got = D.downscope_for_operation(
    provider="generic",
    operation="read_roster",
    default_scopes=("read", "write"),
)
_check("T4.9 read_roster against ('read','write') -> ('read',)", got == ("read",), f"got={got!r}")

# Case 10: Unknown operation -> full default scopes.
defaults = ("read", "write", "admin")
got = D.downscope_for_operation(
    provider="generic",
    operation="something_unknown",
    default_scopes=defaults,
)
_check("T4.10 unknown operation -> full default scopes", got == defaults, f"got={got!r}")

# Case 11: Empty default_scopes -> empty tuple.
got = D.downscope_for_operation(
    provider="generic",
    operation="push_grade",
    default_scopes=tuple(),
)
_check("T4.11 empty default_scopes -> empty tuple", got == tuple(), f"got={got!r}")

# Case 12: supported_operations() returns a non-empty tuple of strings.
ops = D.supported_operations()
ok12 = (
    isinstance(ops, tuple)
    and len(ops) > 0
    and all(isinstance(o, str) and o for o in ops)
)
_check("T4.12 supported_operations() -> non-empty tuple of strings", ok12, f"ops={ops!r}")


# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------
print()
print("=" * 60)
print(f"PASS: {len(_PASS)}    FAIL: {len(_FAIL)}")
if _FAIL:
    print("\nFailed cases:")
    for line in _FAIL:
        print(f"  - {line}")
    sys.exit(1)
print("All cases green.")
sys.exit(0)
