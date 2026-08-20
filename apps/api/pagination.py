"""Project-wide cursor pagination that orders by a column the model actually has.

WHY THIS EXISTS (2026-08-20). ``REST_FRAMEWORK["DEFAULT_PAGINATION_CLASS"]`` was
``rest_framework.pagination.CursorPagination``, whose own ``ordering`` default is
``"-created"``. Exactly **1 of this project's 794 models** has a ``created``
field (``sync_engine.EdgeSyncRun``); the convention here is ``created_at``, on
570 of them. So every DRF list endpoint that did not override
``pagination_class`` raised::

    FieldError: Cannot resolve keyword 'created' into field.
    Choices are: classroom, ..., created_at, date, id, remarks, school, ...

— an unconditional HTTP 500 on every GET. Observed live on a self-hosted box:
``GET /api/attendance/`` returning 500 on every poll from the Sync Center page,
which is how it was finally caught.

It had been caught before, twice, and fixed too narrowly: ``apps/api/entity_api.py``
and ``apps/api/mobile_api.py`` each grew a local ``_BoundedCursorPagination`` with
an explicit ordering. Both files carry a comment describing this exact defect.
Patching the two modules that were noticed left the DEFAULT — the actual cause —
broken for everything else, including the Migration Cloud REST API
(``BundleViewSet``, ``ScopedTokenViewSet``, ``WebhookSubscriptionViewSet``).

The fix belongs at the default, and it must not be another hardcoded field name:
218 models have no timestamp column at all, so any single literal is wrong
somewhere. :class:`RMCCursorPagination` therefore RESOLVES the ordering against
the queryset's model and falls back until it finds a real column.
"""

from __future__ import annotations

from django.conf import settings
from rest_framework.pagination import CursorPagination

# Tried in order when the declared ordering does not resolve on the model.
# ``-pk`` is last and always works: it is guaranteed to exist, non-null and
# unique, which is exactly what a cursor needs. The timestamps come first only
# because a caller reading a list wants newest-first, not insertion order.
FALLBACK_ORDERING = ("-created_at", "-created", "-timestamp", "-pk")


def _model_field_names(model) -> set[str]:
    names = {f.name for f in model._meta.get_fields()}
    names.add("pk")
    return names


def resolve_ordering(model, ordering) -> tuple[str, ...]:
    """Return an ordering tuple every term of which resolves on ``model``.

    Kept module-level and side-effect free so it can be asserted directly, and so
    a caller that is not a paginator (a gate, a contract test) can ask the same
    question without constructing a request.
    """
    if isinstance(ordering, str):
        ordering = (ordering,)
    ordering = tuple(ordering or ())
    if model is None:
        # Nothing to check against; trust the declaration rather than silently
        # reordering someone's queryset on a guess.
        return ordering
    names = _model_field_names(model)

    def resolves(term: str) -> bool:
        # Strip the descending marker, then keep only the first segment so a
        # related traversal ("-school__name") is judged on "school".
        return term.lstrip("-").split("__", 1)[0] in names

    if ordering and all(resolves(term) for term in ordering):
        return ordering
    for candidate in FALLBACK_ORDERING:
        if resolves(candidate):
            return (candidate,)
    return ("-pk",)


class RMCCursorPagination(CursorPagination):
    """Cursor pagination whose ordering is verified against the model.

    Also bounded: ``page_size_query_param`` lets a client page sensibly while
    ``max_page_size`` stops one request becoming an unbounded pull of a whole
    tenant roster. The two local paginators that predate this class already
    required both, so the default now matches what they had to hand-roll.
    """

    page_size_query_param = "page_size"
    max_page_size = getattr(settings, "API_MAX_PAGE_SIZE", 200)
    # The convention on 570 of 794 models. When a model lacks it,
    # ``resolve_ordering`` substitutes something that exists.
    ordering = "-created_at"

    def get_ordering(self, request, queryset, view):
        # Defer to DRF first so an OrderingFilter on the view still wins, then
        # verify. A filter-supplied ordering can name a field the model does not
        # have just as easily as a class attribute can.
        ordering = super().get_ordering(request, queryset, view)
        return resolve_ordering(getattr(queryset, "model", None), ordering)
