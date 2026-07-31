"""DRF authentication for the sovereign edge box's outbound sync POST (Tier 3 Slice 3).

The box presents ``Authorization: Bearer <edge-credential>``. We resolve it to the
bound ``(user, school)`` via the edge machine credential (an ``EDGE_SYNC_SCOPE``-tagged
``OfflineCapabilityToken``), set ``request.user``, and stash the school on the request
so the receiver can scope the apply without a subdomain or session.

Falls through (returns ``None``) whenever the header is absent or the bearer token is
not a valid edge credential, so ordinary Session / JWT authentication still work — a
JWT bearer simply won't match any credential fingerprint and is handed to the next
authenticator.
"""
from __future__ import annotations

from rest_framework import authentication

from apps.sync_engine.edge_outbox import resolve_edge_credential

_SCHEME = "bearer"


class EdgeCredentialAuthentication(authentication.BaseAuthentication):
    """Authenticate an edge box via its machine credential; set request.user + school."""

    def authenticate(self, request):
        header = authentication.get_authorization_header(request).decode("latin1")
        if not header:
            return None
        parts = header.split()
        if len(parts) != 2 or parts[0].lower() != _SCHEME:
            return None

        resolved = resolve_edge_credential(parts[1])
        if resolved is None:
            return None  # not an edge credential — let Session/JWT auth try

        user, school = resolved
        # Scope the request to the credential's school (no subdomain/session needed).
        request.school = school
        return (user, None)

    def authenticate_header(self, request):
        # Prompt a 401 (not 403) when auth is required and missing.
        return "Bearer"


__all__ = ["EdgeCredentialAuthentication"]
