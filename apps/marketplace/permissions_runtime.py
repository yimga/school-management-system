"""Runtime scope resolution for tenant API keys bound to marketplace installations."""

from __future__ import annotations

from apps.apicenter.models import APIKey, OAuthTokenPair
from apps.marketplace.models import ScopeGrant


def effective_scopes_for_api_key(key: APIKey) -> frozenset[str]:
    scopes = {str(s).strip() for s in (key.scopes or []) if str(s).strip()}
    if key.marketplace_installation_id:
        qs = ScopeGrant.objects.filter(
            installation_id=key.marketplace_installation_id,
            status=ScopeGrant.GrantStatus.GRANTED,
        ).select_related("scope")
        for g in qs:
            scopes.add(g.scope.scope_code)
    return frozenset(scopes)


def effective_scopes_for_oauth_pair(pair: OAuthTokenPair, installation) -> frozenset[str]:
    """
    Effective scopes for an OAuth access token at a tenant installation.

    Merges token ``scope`` (space-separated) with granted ``ScopeGrant`` rows — same
    union rule as ``effective_scopes_for_api_key`` but keyed off OAuthTokenPair.
    """
    scopes = {s.strip() for s in (pair.scope or "").split() if s.strip()}
    qs = ScopeGrant.objects.filter(
        installation_id=installation.pk,
        status=ScopeGrant.GrantStatus.GRANTED,
    ).select_related("scope")
    for g in qs:
        scopes.add(g.scope.scope_code)
    return frozenset(scopes)


def app_has_scopes(granted: frozenset[str], *required: str) -> bool:
    return set(required).issubset(set(granted))
