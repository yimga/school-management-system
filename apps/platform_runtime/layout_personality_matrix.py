"""Route-family → visual personality OS (SOVEREIGN-MULTI-PERSONALITY)."""

from __future__ import annotations

# Personality bands from the architectural menu (descriptive, not authorization).
PERSONALITY_SOVEREIGN = "sovereign"
PERSONALITY_CLINICAL = "clinical"
PERSONALITY_FLUID = "fluid"
PERSONALITY_TACTICAL = "tactical"

PERSONALITY_OS_VALUES: frozenset[str] = frozenset(
    {
        PERSONALITY_SOVEREIGN,
        PERSONALITY_CLINICAL,
        PERSONALITY_FLUID,
        PERSONALITY_TACTICAL,
    }
)

_ROUTE_TO_PERSONALITY: dict[str, str] = {
    # Sovereign kernel — admin, governance, studio, lifecycle
    "admin": PERSONALITY_SOVEREIGN,
    "super": PERSONALITY_SOVEREIGN,
    "siteconfig": PERSONALITY_SOVEREIGN,
    "studio": PERSONALITY_SOVEREIGN,
    "setup-studio": PERSONALITY_SOVEREIGN,
    "onboard": PERSONALITY_SOVEREIGN,
    "organization": PERSONALITY_SOVEREIGN,
    # Clinical ledger — money rails
    "billing": PERSONALITY_CLINICAL,
    # Fluid classroom — daily academic surfaces
    "academics": PERSONALITY_FLUID,
    "evals": PERSONALITY_FLUID,
    "communication": PERSONALITY_FLUID,
    "portal": PERSONALITY_FLUID,
    # Tactical terminal — ops, observability, migration, automation
    "marketplace": PERSONALITY_TACTICAL,
    "api-center": PERSONALITY_TACTICAL,
    "metadata": PERSONALITY_TACTICAL,
    "automation": PERSONALITY_TACTICAL,
    "reports": PERSONALITY_TACTICAL,
    "app": PERSONALITY_FLUID,
    "public": PERSONALITY_SOVEREIGN,
}


def resolve_personality_os(route_family: str) -> str:
    fam = (route_family or "app").strip().lower() or "app"
    return _ROUTE_TO_PERSONALITY.get(fam, PERSONALITY_FLUID)
