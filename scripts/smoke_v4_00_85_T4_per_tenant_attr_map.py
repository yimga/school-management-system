"""v4.00.85 Wave 17 Target 4 — Per-tenant SAML attribute mapping override smoke.

Validates ``apps/api/saml.py`` per-tenant override layer:

  1. Env unset -> resolve_saml_attr_map_for_tenant("acme") matches global
  2. Env set w/ override for "acme" -> first_name keys prepend custom claim
  3. Other tenant "bravo" w/ no override -> defaults unchanged
  4. per_tenant_saml_attr_overrides_summary() leaks no raw claim names
  5. Bad JSON env -> defaults preserved, no exception
  6. Override with empty list for a field -> defaults still preserved
  7. Dedupe: override duplicates a default -> output dedupes preserving prepend
  8. _extract_saml_attr walks priority correctly via the merged map

Run:
    python scripts/smoke_v4_00_85_T4_per_tenant_attr_map.py
"""
from __future__ import annotations

import json
import os
import sys

# Ensure repo root is on sys.path when invoked from anywhere.
_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
try:
    import django  # noqa: WPS433
    django.setup()
except Exception:  # noqa: BLE001
    pass

from apps.api import saml as S  # noqa: E402

PASS = 0
FAIL = 0


def _check(label: str, ok: bool, detail: str = "") -> None:
    global PASS, FAIL
    if ok:
        PASS += 1
        print(f"  OK  {label}")
    else:
        FAIL += 1
        print(f"  FAIL {label} {detail}")


def _clear_env() -> None:
    for key in (
        "RMC_SAML_TENANT_ATTR_MAP_OVERRIDES",
        "RMC_SAML_ATTR_FIRST_NAME",
        "RMC_SAML_ATTR_LAST_NAME",
        "RMC_SAML_ATTR_EMAIL",
    ):
        os.environ.pop(key, None)


def case_1_env_unset_matches_global() -> None:
    print("[1] env unset -> resolve_for_tenant matches global")
    _clear_env()
    base = S._resolve_saml_attr_map()
    for_acme = S.resolve_saml_attr_map_for_tenant("acme")
    # tuples vs lists possible; compare element lists
    same = all(
        list(base[f]) == list(for_acme[f]) for f in ("first_name", "last_name", "email")
    )
    _check(
        "acme map equals global when no overrides",
        same,
        detail=f"base={base} for_acme={for_acme}",
    )


def case_2_override_prepends_for_acme() -> None:
    print("[2] override for acme -> first_name prepends custom claim")
    _clear_env()
    os.environ["RMC_SAML_TENANT_ATTR_MAP_OVERRIDES"] = json.dumps({
        "acme": {
            "first_name": ["custom.GivenName", "user.firstName"],
            "email": ["custom.PrimaryEmail"],
        },
    })
    base = S._resolve_saml_attr_map()
    merged = S.resolve_saml_attr_map_for_tenant("acme")
    fn = list(merged["first_name"])
    em = list(merged["email"])
    _check(
        "first_name[0]==custom.GivenName",
        fn[:2] == ["custom.GivenName", "user.firstName"],
        detail=f"got={fn[:4]}",
    )
    # Defaults still appended after overrides
    default_fn = list(base["first_name"])
    _check(
        "defaults appended after overrides for first_name",
        all(d in fn for d in default_fn),
        detail=f"fn={fn} default_fn={default_fn}",
    )
    _check(
        "email[0]==custom.PrimaryEmail",
        em and em[0] == "custom.PrimaryEmail",
        detail=f"em={em[:3]}",
    )
    # last_name untouched (no override) -> equals base
    _check(
        "last_name untouched (no override key)",
        list(merged["last_name"]) == list(base["last_name"]),
        detail=f"merged={merged['last_name']} base={base['last_name']}",
    )


def case_3_other_tenant_no_override() -> None:
    print("[3] other tenant bravo -> defaults unchanged")
    # leave env from case 2 in place — bravo has no override entry
    base = S._resolve_saml_attr_map()
    merged = S.resolve_saml_attr_map_for_tenant("bravo")
    for f in ("first_name", "last_name", "email"):
        _check(
            f"bravo.{f} equals base",
            list(merged[f]) == list(base[f]),
            detail=f"merged={merged[f]} base={base[f]}",
        )


def case_4_summary_leak_safe() -> None:
    print("[4] summary leaks no raw claim names")
    # env still set from case 2 (acme override present)
    s = S.per_tenant_saml_attr_overrides_summary()
    _check("summary.configured==True", s.get("configured") is True, detail=f"summary={s}")
    _check("summary.tenant_count==1", s.get("tenant_count") == 1, detail=f"summary={s}")
    _check("summary.tenants_sample==['acme']", s.get("tenants_sample") == ["acme"],
           detail=f"summary={s}")
    # Sanity — no raw claim names anywhere in the summary dict
    flat = json.dumps(s)
    leaked = any(
        token in flat
        for token in ("custom.GivenName", "custom.PrimaryEmail", "user.firstName")
    )
    _check("no raw claim names in summary JSON", not leaked, detail=f"flat={flat}")


def case_5_bad_json_env() -> None:
    print("[5] bad JSON env -> defaults preserved, no exception")
    _clear_env()
    os.environ["RMC_SAML_TENANT_ATTR_MAP_OVERRIDES"] = "{not valid json"
    try:
        ov = S._resolve_per_tenant_attr_overrides()
        merged = S.resolve_saml_attr_map_for_tenant("acme")
        base = S._resolve_saml_attr_map()
        _check("bad JSON -> overrides={}", ov == {}, detail=f"ov={ov}")
        _check(
            "bad JSON -> merged equals base",
            all(list(merged[f]) == list(base[f]) for f in ("first_name", "last_name", "email")),
            detail=f"merged={merged} base={base}",
        )
    except Exception as exc:  # noqa: BLE001
        _check("no exception on bad JSON", False, detail=f"raised={exc!r}")


def case_6_empty_list_keeps_defaults() -> None:
    print("[6] override w/ empty list for a field -> defaults still preserved")
    _clear_env()
    os.environ["RMC_SAML_TENANT_ATTR_MAP_OVERRIDES"] = json.dumps({
        "acme": {
            "first_name": [],  # explicitly empty
            "email": ["custom.PrimaryEmail"],
        },
    })
    base = S._resolve_saml_attr_map()
    merged = S.resolve_saml_attr_map_for_tenant("acme")
    _check(
        "empty override first_name -> equals base",
        list(merged["first_name"]) == list(base["first_name"]),
        detail=f"merged={merged['first_name']} base={base['first_name']}",
    )
    _check(
        "email override still applied",
        list(merged["email"])[0] == "custom.PrimaryEmail",
        detail=f"merged.email={merged['email']}",
    )


def case_7_dedupe_preserves_prepend() -> None:
    print("[7] dedupe — override duplicates a default -> prepend preserved")
    _clear_env()
    # 'email' is in defaults — pre-pending it should NOT duplicate, AND its
    # prepended position should win (the default 'email' entry vanishes from
    # its original spot since the prepended one already covers it).
    os.environ["RMC_SAML_TENANT_ATTR_MAP_OVERRIDES"] = json.dumps({
        "acme": {
            "email": ["email", "custom.PrimaryEmail"],
        },
    })
    base = S._resolve_saml_attr_map()
    merged = S.resolve_saml_attr_map_for_tenant("acme")
    em = list(merged["email"])
    _check("email[0]=='email' (prepended copy)", em[0] == "email", detail=f"em={em}")
    _check("email[1]=='custom.PrimaryEmail'", em[1] == "custom.PrimaryEmail", detail=f"em={em}")
    _check("dedupe — 'email' appears exactly once", em.count("email") == 1, detail=f"em={em}")
    # length = len(base.email) + 1 (the new custom.PrimaryEmail, default 'email' deduped)
    _check(
        "merged length = default_len + 1 new entry",
        len(em) == len(list(base["email"])) + 1,
        detail=f"em_len={len(em)} base_len={len(list(base['email']))}",
    )


def case_8_extract_walks_priority_via_merged() -> None:
    print("[8] _extract_saml_attr walks priority via merged map")
    _clear_env()
    os.environ["RMC_SAML_TENANT_ATTR_MAP_OVERRIDES"] = json.dumps({
        "acme": {
            "first_name": ["custom.GivenName"],
        },
    })
    merged = S.resolve_saml_attr_map_for_tenant("acme")
    # Case a: only override key present -> wins
    attrs_only_override = {"custom.GivenName": "Alice"}
    got = S._extract_saml_attr(attrs_only_override, merged["first_name"])
    _check("override key alone resolves", got == "Alice", detail=f"got={got!r}")

    # Case b: BOTH override + default present -> override wins (priority)
    attrs_both = {"custom.GivenName": "Alice", "givenName": "Bob"}
    got = S._extract_saml_attr(attrs_both, merged["first_name"])
    _check("override wins when both present", got == "Alice", detail=f"got={got!r}")

    # Case c: only default key present -> default still resolves (fallback works)
    attrs_only_default = {"givenName": "Bob"}
    got = S._extract_saml_attr(attrs_only_default, merged["first_name"])
    _check("default fallback resolves", got == "Bob", detail=f"got={got!r}")

    # Case d: neither present -> empty
    got = S._extract_saml_attr({}, merged["first_name"])
    _check("absent -> empty string", got == "", detail=f"got={got!r}")


def main() -> int:
    case_1_env_unset_matches_global()
    case_2_override_prepends_for_acme()
    case_3_other_tenant_no_override()
    case_4_summary_leak_safe()
    case_5_bad_json_env()
    case_6_empty_list_keeps_defaults()
    case_7_dedupe_preserves_prepend()
    case_8_extract_walks_priority_via_merged()
    _clear_env()
    print()
    print(f"PASS={PASS} FAIL={FAIL}")
    return 0 if FAIL == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
