"""v4.00.59 — OneRoster v1.2 Demographics endpoints (read-only).

Surfaces the OneRoster ``Demographic`` resource as a projection over
``apps.people.models.StudentProfile`` data. Sparse projection — only the
fields we actually hold (sex / birthDate) are populated; the rest of the
v1.2 spec fields are emitted as empty strings per the optional-field
contract.

Endpoints (mounted under ``/api/roster/v1p2/``):

* ``GET demographics/`` — paginated list
* ``GET demographics/<sourcedId>/`` — single record
* ``GET students/<sourcedId>/demographics/`` — projection for one student

All endpoints are bearer-gated via the existing ``apps.api.oneroster._gate``
contract. NEVER raises — model unavailability returns 503; missing rows
return 404.
"""
from __future__ import annotations

import logging
from typing import Any, Iterable

from django.http import HttpRequest, JsonResponse
from django.views.decorators.http import require_http_methods

from apps.api.oneroster import _envelope, _gate, _paginate

logger = logging.getLogger(__name__)


_GENDER_TO_SEX = {
    "MALE": "male",
    "FEMALE": "female",
    "NON_BINARY": "other",
    "OTHER": "other",
    "PREFER_NOT_TO_SAY": "",
}


def _demographic_from_student(s) -> dict[str, Any]:
    """Project a StudentProfile row into a OneRoster Demographic dict.

    Sparse fields per the v1.2 contract: missing data emits an empty
    string rather than null so JSON consumers don't need null-checks.
    """
    birth_date = ""
    if getattr(s, "date_of_birth", None) is not None:
        try:
            birth_date = s.date_of_birth.isoformat()
        except Exception:  # noqa: BLE001
            birth_date = ""
    sex = _GENDER_TO_SEX.get((getattr(s, "gender", "") or "").upper(), "")
    date_last_modified = ""
    upd = getattr(s, "updated_at", None) or getattr(s, "modified_at", None)
    if upd is not None:
        try:
            date_last_modified = upd.isoformat()
        except Exception:  # noqa: BLE001
            date_last_modified = ""
    return {
        "sourcedId": f"demo-{s.pk}",
        "status": "active",
        "dateLastModified": date_last_modified,
        "birthDate": birth_date,
        "sex": sex,
        "americanIndianOrAlaskaNative": "",
        "asian": "",
        "blackOrAfricanAmerican": "",
        "nativeHawaiianOrOtherPacificIslander": "",
        "white": "",
        "demographicRaceTwoOrMoreRaces": "",
        "hispanicOrLatinoEthnicity": "",
        "countryOfBirthCode": "",
        "stateOfBirthAbbreviation": "",
        "cityOfBirth": (getattr(s, "place_of_birth", "") or ""),
        "publicSchoolResidenceStatus": "",
    }


def _iter_demographics() -> Iterable[dict[str, Any]]:
    try:
        from apps.people.models import StudentProfile
    except Exception as exc:  # noqa: BLE001
        logger.debug("oneroster demographics: StudentProfile unavailable: %s", exc)
        return
    qs = StudentProfile.objects.all()  # tenant-isolation-allow: oneroster-demographics-platform-scope-bearer-auth
    for s in qs[:1000]:
        yield _demographic_from_student(s)


@require_http_methods(["GET"])
def demographics_collection(request: HttpRequest):
    """v4.00.59 — Paginated list of Demographic records."""
    gate = _gate(request)
    if gate is not None:
        return gate
    items = list(_iter_demographics())
    page, meta = _paginate(request, items)
    return _envelope("demographics", page, meta)


@require_http_methods(["GET"])
def demographic_detail(request: HttpRequest, sourced_id: str):
    """v4.00.59 — Single Demographic record by sourcedId (``demo-<pk>``)."""
    gate = _gate(request)
    if gate is not None:
        return gate
    if not sourced_id.startswith("demo-"):
        return JsonResponse({"error": "bad_sourced_id"}, status=400)
    pk = sourced_id[5:]
    if not pk:
        return JsonResponse({"error": "bad_sourced_id"}, status=400)
    try:
        from apps.people.models import StudentProfile
    except Exception:  # noqa: BLE001
        return JsonResponse({"error": "models_unavailable"}, status=503)
    try:
        obj = StudentProfile.objects.filter(pk=pk).first()  # tenant-isolation-allow: oneroster-demographic-by-pk-bearer-auth
    except (ValueError, TypeError):
        return JsonResponse({"error": "bad_sourced_id"}, status=400)
    if obj is None:
        return JsonResponse({"error": "not_found", "sourcedId": sourced_id}, status=404)
    return JsonResponse({"demographic": _demographic_from_student(obj)})


@require_http_methods(["GET"])
def student_demographics(request: HttpRequest, sourced_id: str):
    """v4.00.59 — Demographic for a single student, identified by user pk.

    ``sourced_id`` here is the student's user pk (matches the OneRoster
    students endpoint sourcedId, which projects User.pk).
    """
    gate = _gate(request)
    if gate is not None:
        return gate
    try:
        from apps.people.models import StudentProfile
    except Exception:  # noqa: BLE001
        return JsonResponse({"error": "models_unavailable"}, status=503)
    try:
        obj = StudentProfile.objects.filter(user_id=sourced_id).first()  # tenant-isolation-allow: oneroster-demographic-by-user-id-bearer-auth
    except (ValueError, TypeError):
        return JsonResponse({"error": "bad_sourced_id"}, status=400)
    if obj is None:
        return JsonResponse({"error": "not_found", "sourcedId": sourced_id}, status=404)
    return JsonResponse({"demographic": _demographic_from_student(obj)})
