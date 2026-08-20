"""The BOX's pairing screen. It displays a code and accepts nothing.

Read that sentence as the security model, not a description. This page is reachable
without logging in while the box is unpaired, on a school LAN that the edge profile
serves over plain HTTP by design. Anything it ACCEPTED would be an unauthenticated
write surface on a cleartext network. It accepts nothing: no form, no code entry, no
credential field. The only state it can change is "open a pairing request", which
creates a row in the cloud's review queue and returns a code that does nothing until
an authenticated admin of the named school approves it.

CLAIM ON FIRST BOOT, THEN SEAL. ``edge_binding.is_sealed()`` goes True the moment a
pairing completes (and is already True for a box configured the old way, via env
vars). After that this page requires a logged-in admin. So the anonymous window is
exactly once, at first boot, before the box holds any data worth taking — and
re-pairing afterwards needs either an authenticated session or shell access on the
host, both of which prove more than being on the LAN does.
"""
from __future__ import annotations

import logging

from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.shortcuts import render
from django.views.decorators.http import require_http_methods

logger = logging.getLogger(__name__)


def _sealed_requires_login(view):
    """Anonymous only while unpaired; an admin session once the box is sealed."""

    def wrapper(request, *args, **kwargs):
        from apps.sync_engine.edge_binding import is_sealed

        if is_sealed():
            return login_required(view)(request, *args, **kwargs)
        return view(request, *args, **kwargs)

    wrapper.__name__ = getattr(view, "__name__", "wrapper")
    wrapper.__doc__ = view.__doc__
    return wrapper


@require_http_methods(["GET"])
@_sealed_requires_login
def pair_this_box(request):  # rbac-allow: display-only-screen-anonymous-only-while-the-box-is-unpaired
    """Show this box's pairing code, or its current binding."""
    from apps.sync_engine import pairing_client
    from apps.sync_engine.edge_binding import binding_summary

    summary = binding_summary()
    pending = pairing_client.current_request()
    return render(
        request,
        "sync_engine/pair_this_box.html",
        {
            "binding": summary,
            "pending": pending,
            "page_title": "Pair this box",
        },
    )


@require_http_methods(["POST"])
@_sealed_requires_login
def pair_this_box_start(request):  # rbac-allow: opens-a-request-that-grants-nothing-until-a-cloud-admin-approves
    """Ask the cloud for a pairing code.

    A POST rather than a GET because it creates a request upstream, but note what it
    does NOT do: it accepts no user input at all. Everything sent to the cloud is read
    from this box's own configuration and hostname.
    """
    from apps.sync_engine import pairing_client

    result = pairing_client.start()
    return JsonResponse(result, status=200 if result.get("ok") else 400)


@require_http_methods(["POST"])
@_sealed_requires_login
def pair_this_box_poll(request):  # rbac-allow: polls-a-request-this-box-already-holds-the-secret-for
    """Ask the cloud whether the request has been approved yet."""
    from apps.sync_engine import pairing_client

    return JsonResponse(pairing_client.poll(), status=200)


__all__ = ["pair_this_box", "pair_this_box_poll", "pair_this_box_start"]
