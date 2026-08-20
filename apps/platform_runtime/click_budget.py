"""One definition of "how many clicks did this shortcut save?".

R5 of the dead-end spec asks that "fewer clicks" stop being an aspiration and
become a number that can regress and be caught. That only works if the number
is *derived*. Hand-assigned values are the aspiration wearing a digit: the
registry in ``tenant_daily_ops`` carried ``clicks_saved: 1`` and
``clicks_saved: 2`` with nothing behind them, and no way to tell a wrong one
from a right one.

The derivation
--------------
A reader who does not have a shortcut reaches a screen by walking the menu it
lives under. ``/portal/teacher/homework/gradebook/`` is Portal, then Teacher,
then Homework, then Gradebook — four steps. A chip that jumps straight there
costs one click, so it saves three.

So: **clicks saved = path segments - 1**, floored at 1.

That is not a perfect model of the navigation graph, and it is not meant to
be. It is reproducible, it is computed from the destination rather than
asserted about it, and it moves in the right direction for the right reason —
a shortcut deep into the app saves more than one to a top-level page. A number
you can recompute is worth more than a number you have to trust.

It also cannot silently drift. When a route moves, the number moves with it;
when a destination is deleted, the saving goes to zero rather than staying on
the books as a claim about a screen that no longer exists.

Pairs with ``apps.platform_runtime.click_tracking``, which measures what
readers *actually* did. This module is the claim; that one is the evidence.
Keep them apart — a claim that edits itself to match the evidence measures
nothing.
"""

from __future__ import annotations

from django.urls import NoReverseMatch, reverse

# A shortcut always saves at least one step, or it would not be a shortcut.
MIN_CLICKS_SAVED = 1


def clicks_saved_for_path(path: str) -> int:
    """Clicks a direct link to ``path`` saves over walking there by hand.

    Returns 0 for an empty path — no destination, no saving. A querystring is
    ignored: filtering a list you already reached is not a navigation step.
    """
    if not path:
        return 0
    segments = [seg for seg in path.split("?")[0].split("/") if seg]
    if not segments:
        return 0
    return max(MIN_CLICKS_SAVED, len(segments) - 1)


def clicks_saved_for_url_name(url_name: str) -> int:
    """As above, for a named route on the *current* urlconf.

    Returns 0 when the name does not reverse here. A destination absent from
    this host saves nobody anything, and reporting otherwise would inflate the
    ledger with links this reader cannot follow.
    """
    if not url_name:
        return 0
    try:
        return clicks_saved_for_path(reverse(url_name))
    except NoReverseMatch:
        return 0
