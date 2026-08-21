"""Box-local pairing screen.

Deliberately its own urlconf rather than a few more paths bolted onto siteconfig:
these views are the only part of the platform that answers an ANONYMOUS caller on a
box, and keeping them in one named place is what makes that property reviewable
instead of something you have to grep for.
"""
from __future__ import annotations

from django.urls import path

from apps.sync_engine.views_pairing import (
    pair_this_box,
    pair_this_box_poll,
    pair_this_box_start,
)

app_name = "sync_engine"

urlpatterns = [
    path("pair-this-box/", pair_this_box, name="pair_this_box"),  # rbac-allow: display-only-while-unpaired-see-views_pairing
    path("pair-this-box/start/", pair_this_box_start, name="pair_this_box_start"),  # rbac-allow: creates-a-request-that-grants-nothing-until-approved
    path("pair-this-box/poll/", pair_this_box_poll, name="pair_this_box_poll"),  # rbac-allow: requires-the-poll-secret-this-box-already-holds
]
