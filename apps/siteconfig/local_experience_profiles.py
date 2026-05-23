"""LocalExperienceProfile registry.

Bundles country / region / language / academic-system / grading / calendar /
communication-style / payment-rails into a single key so ExperienceTemplate
entries can reference one profile by key (``local_profile_ref``) instead of
re-declaring the local-first bundle inline.

This registry is COMPLEMENTARY to the existing CountryRegistry +
country_localization_service. It does NOT replace them. CountryRegistry holds
the marketing_voice cockpit overrides (Wave 12/13); this module holds the
operational-layout overlay that templates consume.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable


@dataclass(frozen=True)
class LocalExperienceProfile:
    key: str
    country: str  # ISO-2
    region: str  # state/province code or ""
    languages: tuple[str, ...]
    academic_system: str
    grading_system: str
    calendar_system: str
    communication_style: str
    palette_family: str
    typography_family: str
    cultural_accent_policy: str
    parent_engagement_default: str
    low_connectivity_default: bool
    currency_default: str
    payment_rails_default: tuple[str, ...]
    notes: str = ""

    def as_dict(self) -> dict:
        return {
            "key": self.key,
            "country": self.country,
            "region": self.region,
            "languages": list(self.languages),
            "academic_system": self.academic_system,
            "grading_system": self.grading_system,
            "calendar_system": self.calendar_system,
            "communication_style": self.communication_style,
            "palette_family": self.palette_family,
            "typography_family": self.typography_family,
            "cultural_accent_policy": self.cultural_accent_policy,
            "parent_engagement_default": self.parent_engagement_default,
            "low_connectivity_default": self.low_connectivity_default,
            "currency_default": self.currency_default,
            "payment_rails_default": list(self.payment_rails_default),
            "notes": self.notes,
        }


def _p(
    key: str,
    country: str,
    languages: tuple[str, ...],
    *,
    academic: str,
    grading: str,
    calendar: str,
    palette: str,
    typography: str,
    currency: str,
    rails: tuple[str, ...],
    region: str = "",
    style: str = "warm-formal",
    accent: str = "geometric-warm",
    parent_engage: str = "weekly-summary",
    low_connect: bool = False,
    notes: str = "",
) -> LocalExperienceProfile:
    return LocalExperienceProfile(
        key=key,
        country=country,
        region=region,
        languages=languages,
        academic_system=academic,
        grading_system=grading,
        calendar_system=calendar,
        communication_style=style,
        palette_family=palette,
        typography_family=typography,
        cultural_accent_policy=accent,
        parent_engagement_default=parent_engage,
        low_connectivity_default=low_connect,
        currency_default=currency,
        payment_rails_default=rails,
        notes=notes,
    )


PROFILES: tuple[LocalExperienceProfile, ...] = (
    # Africa anglophone
    _p("cm-anglophone-gce", "CM", ("en", "fr"), academic="gce-anglophone", grading="letter", calendar="gregorian-sep-jul", palette="warm-terracotta", typography="stack-bilingual-mixed", currency="XAF", rails=("bank-transfer", "mobile-money", "cash-collection"), style="warm-formal", accent="geometric-warm"),
    _p("ng-private-secondary", "NG", ("en",), academic="waec-anglophone", grading="numeric-0-100", calendar="gregorian-sep-jul", palette="warm-terracotta", typography="stack-system-sans", currency="NGN", rails=("bank-transfer", "card-online", "cash-collection"), parent_engage="event-driven"),
    _p("gh-private-school", "GH", ("en",), academic="ges-wassce", grading="letter", calendar="gregorian-sep-jul", palette="warm-terracotta", typography="stack-system-sans", currency="GHS", rails=("bank-transfer", "mobile-money", "cash-collection")),
    _p("ke-cbc-primary-secondary", "KE", ("en", "sw"), academic="cbc-kenya", grading="numeric-0-100", calendar="gregorian-jan-nov", palette="savanna-ochre", typography="stack-bilingual-mixed", currency="KES", rails=("mobile-money", "bank-transfer"), accent="community-organic", parent_engage="mobile-sms-first"),
    _p("za-provincial-grades", "ZA", ("en", "af", "zu"), academic="dbe-matric", grading="numeric-0-100", calendar="gregorian-jan-dec", palette="savanna-ochre", typography="stack-system-sans", currency="ZAR", rails=("bank-transfer", "card-online"), accent="geometric-cool"),
    # Africa francophone
    _p("cm-francophone-bac", "CM", ("fr", "en"), academic="bac-francophone", grading="numeric-0-20", calendar="gregorian-sep-jul", palette="warm-terracotta", typography="stack-bilingual-mixed", currency="XAF", rails=("bank-transfer", "mobile-money", "cash-collection"), style="formal", accent="editorial-neutral"),
    _p("ci-bac-francophone", "CI", ("fr",), academic="bac-francophone", grading="numeric-0-20", calendar="gregorian-sep-jul", palette="warm-terracotta", typography="stack-system-sans", currency="XOF", rails=("bank-transfer", "mobile-money", "cash-collection"), style="formal"),
    _p("sn-bac-francophone", "SN", ("fr", "wo"), academic="bac-francophone", grading="numeric-0-20", calendar="gregorian-oct-jul", palette="warm-terracotta", typography="stack-bilingual-mixed", currency="XOF", rails=("bank-transfer", "mobile-money"), style="formal"),
    _p("ma-bac-bilingual", "MA", ("ar", "fr"), academic="bac-marocain", grading="numeric-0-20", calendar="gregorian-sep-jun", palette="desert-amber", typography="stack-bilingual-mixed", currency="MAD", rails=("bank-transfer", "card-online", "cash-collection"), style="formal", accent="geometric-warm"),
    # South Asia
    _p("in-cbse-hindi-medium", "IN", ("hi", "en"), academic="cbse", grading="cgpa-10", calendar="gregorian-apr-mar", palette="monsoon-teal", typography="stack-bilingual-mixed", currency="INR", rails=("bank-transfer", "card-online", "upi"), style="warm-formal", accent="geometric-warm"),
    _p("in-ka-state-board", "IN", ("kn", "en"), academic="ka-state-board", grading="numeric-0-100", calendar="gregorian-jun-may", palette="monsoon-teal", typography="stack-bilingual-mixed", currency="INR", rails=("bank-transfer", "card-online", "upi"), region="KA", style="warm-formal"),
    _p("pk-fbise-urdu-medium", "PK", ("ur", "en"), academic="fbise", grading="numeric-0-100", calendar="gregorian-aug-may", palette="desert-amber", typography="stack-bilingual-mixed", currency="PKR", rails=("bank-transfer", "card-online", "cash-collection"), style="formal"),
    _p("bd-sec-edu-bengali", "BD", ("bn", "en"), academic="nse-bangladesh", grading="cgpa-5", calendar="gregorian-jan-dec", palette="monsoon-teal", typography="stack-bilingual-mixed", currency="BDT", rails=("bank-transfer", "mobile-money", "cash-collection")),
    # East Asia
    _p("jp-mext-bilingual", "JP", ("ja", "en"), academic="mext-japan", grading="numeric-0-100", calendar="gregorian-apr-mar", palette="sakura-blush", typography="stack-bilingual-mixed", currency="JPY", rails=("bank-transfer", "card-online"), style="formal", accent="editorial-neutral"),
    _p("kr-international-bilingual", "KR", ("ko", "en"), academic="kr-international", grading="numeric-0-100", calendar="gregorian-mar-feb", palette="sakura-blush", typography="stack-bilingual-mixed", currency="KRW", rails=("bank-transfer", "card-online"), style="formal"),
    _p("cn-bilingual-private", "CN", ("zh-Hans", "en"), academic="cn-bilingual", grading="numeric-0-100", calendar="gregorian-sep-jul", palette="sakura-blush", typography="stack-bilingual-mixed", currency="CNY", rails=("bank-transfer", "wechat-pay", "alipay"), style="formal"),
    # Southeast Asia
    _p("ph-deped-k12", "PH", ("en", "tl"), academic="deped-k12", grading="numeric-0-100", calendar="gregorian-aug-may", palette="warm-terracotta", typography="stack-bilingual-mixed", currency="PHP", rails=("bank-transfer", "mobile-money", "card-online"), style="warm-formal"),
    _p("my-igcse-bilingual", "MY", ("en", "ms"), academic="igcse-malaysia", grading="letter", calendar="gregorian-jan-nov", palette="monsoon-teal", typography="stack-bilingual-mixed", currency="MYR", rails=("bank-transfer", "card-online")),
    _p("id-private-bilingual", "ID", ("id", "en"), academic="id-private-bilingual", grading="numeric-0-100", calendar="gregorian-jul-jun", palette="monsoon-teal", typography="stack-bilingual-mixed", currency="IDR", rails=("bank-transfer", "card-online", "cash-collection"), style="warm-formal"),
    # Western
    _p("us-charter-state", "US", ("en", "es"), academic="us-charter-state", grading="letter", calendar="gregorian-aug-may", palette="cool-indigo", typography="stack-system-sans", currency="USD", rails=("card-online", "bank-transfer"), parent_engage="daily-digest", accent="geometric-cool"),
    _p("gb-igcse-a-level", "GB", ("en",), academic="igcse-a-level", grading="gcse-9-1", calendar="gregorian-sep-jul", palette="editorial-cream", typography="stack-editorial-serif", currency="GBP", rails=("card-online", "bank-transfer"), style="formal", accent="editorial-neutral"),
    _p("au-state-curriculum", "AU", ("en",), academic="au-state-curriculum", grading="letter", calendar="gregorian-jan-dec", palette="cool-indigo", typography="stack-system-sans", currency="AUD", rails=("card-online", "bank-transfer")),
    # Gulf + Latin America
    _p("ae-cbse-or-british", "AE", ("ar", "en"), academic="ae-international", grading="numeric-0-100", calendar="gregorian-sep-jun", palette="desert-amber", typography="stack-bilingual-mixed", currency="AED", rails=("card-online", "bank-transfer"), style="formal", accent="geometric-warm"),
    _p("mx-sep-bilingual", "MX", ("es", "en"), academic="sep-mexico", grading="numeric-0-100", calendar="gregorian-aug-jul", palette="andes-clay", typography="stack-bilingual-mixed", currency="MXN", rails=("bank-transfer", "card-online", "cash-collection"), style="warm-formal", accent="community-organic"),
    _p("br-mec-bilingual", "BR", ("pt", "en"), academic="mec-brazil", grading="numeric-0-10", calendar="gregorian-feb-dec", palette="andes-clay", typography="stack-bilingual-mixed", currency="BRL", rails=("bank-transfer", "card-online", "pix"), style="warm-formal", accent="community-organic"),
)


_PROFILE_INDEX: dict[str, LocalExperienceProfile] = {p.key: p for p in PROFILES}


def get_profile(key: str) -> LocalExperienceProfile | None:
    return _PROFILE_INDEX.get(key)


def list_profiles(*, country: str | None = None) -> list[dict]:
    rows = list(PROFILES)
    if country:
        cc = country.strip().upper()
        rows = [r for r in rows if r.country == cc]
    return [r.as_dict() for r in rows]


def profile_keys() -> Iterable[str]:
    return _PROFILE_INDEX.keys()


def assert_registry_invariants() -> None:
    """Raise AssertionError if registry shape regresses. Run from verifier."""
    if len(PROFILES) != 25:
        raise AssertionError(f"Expected exactly 25 LocalExperienceProfile entries, got {len(PROFILES)}")
    keys = [p.key for p in PROFILES]
    if len(set(keys)) != len(keys):
        raise AssertionError("Duplicate LocalExperienceProfile keys detected.")
    for p in PROFILES:
        if len(p.country) != 2 or not p.country.isupper():
            raise AssertionError(f"Profile {p.key}: country '{p.country}' must be ISO-2 uppercase")
        if not p.languages:
            raise AssertionError(f"Profile {p.key}: languages must be non-empty")
        if not p.currency_default or len(p.currency_default) != 3:
            raise AssertionError(f"Profile {p.key}: currency_default must be ISO-4217")
