# apps/api/search_api.py
"""
Global Search API
Location: apps/api/search_api.py

Unified search across all system resources
"""

from django.views import View
from django.http import JsonResponse
from django.contrib.auth.decorators import login_required
from django.utils.decorators import method_decorator
from django.db.models import Q
from django.db.utils import DatabaseError
from django.core.exceptions import FieldDoesNotExist, ObjectDoesNotExist
from django.views.decorators.http import require_http_methods
from django.urls import reverse, NoReverseMatch
import logging

logger = logging.getLogger(__name__)

# §2.4: enrich may skip on DB/shape errors (broad_exception_audit apps/api)
_STUDENT_STORY_ENRICH_ERRORS = (
    DatabaseError,
    TypeError,
    ValueError,
    KeyError,
    AttributeError,
    IndexError,
)


@method_decorator(login_required, name="dispatch")
@method_decorator(require_http_methods(["GET"]), name="dispatch")
class GlobalSearchAPI(View):
    """
    Global search across system

    Query Parameters:
    - q: search query (required, min 2 chars)
    - type: specific type to search (optional: all, student, teacher, class, invoice, subject)
    - limit: results per type (default 20)

    Usage:
    GET /api/search/?q=john&limit=20
    GET /api/search/?q=math&type=subject
    """

    SEARCH_CONFIG = {
        "student": {
            "model": "StudentProfile",
            "search_fields": [
                "first_name",
                "last_name",
                "student_code",
                "admission_number",
            ],
            "icon": "bi-person",
            "color": "primary",
        },
        "teacher": {
            "model": "TeacherProfile",
            "search_fields": [
                "user__first_name",
                "user__last_name",
                "staff_id",
                "position_title",
            ],
            "icon": "bi-person-badge",
            "color": "success",
        },
        "class": {
            "model": "Classroom",
            "search_fields": ["name", "code"],
            "icon": "bi-people",
            "color": "info",
        },
        "subject": {
            "model": "Subject",
            "search_fields": ["name", "category"],
            "icon": "bi-book",
            "color": "warning",
        },
        "invoice": {
            "model": "Invoice",
            "search_fields": [
                "reference",
                "student__first_name",
                "student__last_name",
                "student__student_code",
            ],
            "icon": "bi-receipt",
            "color": "danger",
        },
    }

    ELEVATED_ROLES = {
        "ADMIN",
        "LEADERSHIP",
        "PRINCIPAL",
        "VICE_PRINCIPAL",
        "DEAN",
        "HOD",
        "CENSOR",
        "BURSAR",
        "IT_ADMIN",
        "BOARDING_MANAGER",
    }

    FINANCE_ROLES = {
        "ADMIN",
        "LEADERSHIP",
        "PRINCIPAL",
        "BURSAR",
    }

    def _safe_reverse(self, name, args=None, kwargs=None, fallback="#"):
        try:
            return reverse(name, args=args, kwargs=kwargs)
        except NoReverseMatch:
            return fallback

    def _student_url(self, user, student):
        role = getattr(user, "role", None) or ""
        if role in self.ELEVATED_ROLES:
            u = self._safe_reverse(
                "accounts:backend_student_detail", kwargs={"student_id": student.id}
            )
            if u != "#":
                return u
        if user.is_staff or user.is_superuser:
            return self._safe_reverse(
                "admin:people_studentprofile_change", args=[student.id]
            )

        if role == User.Role.PARENT:
            return self._safe_reverse("portal:parent_child_results", args=[student.id])
        if role == User.Role.TEACHER:
            base = self._safe_reverse("evals:teacher_marks_list")
            if base == "#":
                return base
            return f"{base}?classroom={student.classroom_id}"

        return "#"

    def _teacher_url(self, user, teacher):
        if user.is_staff or user.is_superuser:
            return self._safe_reverse(
                "admin:people_teacherprofile_change", args=[teacher.id]
            )
        return "#"

    def _classroom_url(self, user, classroom):
        if user.is_staff or user.is_superuser:
            return self._safe_reverse(
                "admin:academics_classroom_change", args=[classroom.id]
            )
        return "#"

    def _subject_url(self, user, subject):
        if user.is_staff or user.is_superuser:
            return self._safe_reverse(
                "admin:academics_subject_change", args=[subject.id]
            )
        return "#"

    def _invoice_url(self, invoice):
        return self._safe_reverse(
            "finance:invoice_detail",
            args=[invoice.id],
            fallback=f"/finance/invoices/{invoice.id}/",
        )

    def get(self, request):
        query = request.GET.get("q", "").strip()
        search_type = request.GET.get("type", "all")
        limit = int(request.GET.get("limit", 20))

        # Validate query
        if len(query) < 2:
            return JsonResponse(
                {"error": "Query too short. Minimum 2 characters required."}, status=400
            )

        school = getattr(request, "school", None)
        school_id = getattr(school, "id", None) if school else None
        # Read layer: OpenSearch when configured (non-negotiable integration point)
        want_story = request.GET.get("story") in ("1", "true", "yes")
        try:
            from apps.api.search_read_layer import search as search_read_layer

            data = search_read_layer(
                q=query,
                search_type=search_type if search_type != "all" else None,
                school_id=school_id,
                limit=limit,
            )
            if data is not None:
                if want_story and school:
                    data = dict(data)
                    data["results"] = self._enrich_student_stories(
                        list(data.get("results") or []), school, request.user
                    )
                return JsonResponse(data)
        except (ImportError, AttributeError, TypeError, ValueError) as e:
            logger.debug("Search read layer skipped: %s", e)

        results = []
        if search_type == "all":
            types_to_search = list(self.SEARCH_CONFIG.keys())
        else:
            types_to_search = [search_type]

        for search_type_key in types_to_search:
            config = self.SEARCH_CONFIG.get(search_type_key)
            if not config:
                continue

            try:
                items = self._search_type(
                    config, query, limit, request.user, school=school
                )
                results.extend(items)
            except (
                ImportError,
                AttributeError,
                TypeError,
                ValueError,
                ObjectDoesNotExist,
                DatabaseError,
            ) as e:
                logger.error("Search error for %s: %s", search_type_key, e)

        if want_story and school:
            results = self._enrich_student_stories(results, school, request.user)

        return JsonResponse({"query": query, "count": len(results), "results": results})

    def _enrich_student_stories(self, results, school, user):
        """Attach cross-module story preview to student search hits (linkage-first command bar)."""
        from apps.people.models import StudentProfile
        from apps.portal.one_record import build_student_story_preview

        role = (getattr(user, "role", None) or "").upper()
        if role == User.Role.TEACHER:
            inc_fin, inc_comm = False, False
        elif role == User.Role.PARENT:
            inc_fin, inc_comm = False, True
        else:
            inc_fin = bool(
                user.is_staff
                or user.is_superuser
                or role in self.FINANCE_ROLES
                or role in self.ELEVATED_ROLES
            )
            inc_comm = inc_fin or role in self.ELEVATED_ROLES

        for r in results:
            if not isinstance(r, dict) or r.get("type") != "student":
                continue
            sid = r.get("id")
            if sid is None:
                continue
            # Use ORM pk= (not int()) so JSON/string IDs from the API layer resolve correctly
            # for integer StudentProfile PKs; avoids silent skips when sid is str.
            try:
                st = StudentProfile.objects.select_related("school").get(
                    pk=sid, school_id=school.id
                )
            except (StudentProfile.DoesNotExist, TypeError, ValueError):
                continue
            try:
                r["story"] = build_student_story_preview(
                    st, school, include_finance=inc_fin, include_communications=inc_comm
                )
            except _STUDENT_STORY_ENRICH_ERRORS as e:
                logger.debug("student story enrich skipped: %s", e)
        return results

    def _search_type(self, config, query, limit, user, school=None):
        """Search a specific resource type. Section 25.3: when school is set, all querysets are tenant-scoped."""
        results = []

        # Build query
        q_object = Q()
        for field in config["search_fields"]:
            q_object |= Q(**{f"{field}__icontains": query})

        # Get model dynamically
        if config["model"] == "StudentProfile":
            from apps.people.models import StudentProfile

            role = getattr(user, "role", None)
            base = StudentProfile.objects.filter(q_object, is_active=True)
            if school is not None:
                base = base.filter(school=school)
            if user.is_staff or user.is_superuser or role in self.ELEVATED_ROLES:
                items = base[:limit]
            elif role == User.Role.TEACHER:
                from apps.evals.models import TeacherAssignment

                teacher = getattr(user, "teacher_profile", None)
                if not teacher:
                    return results
                classroom_ids = list(
                    TeacherAssignment.objects.filter(
                        teacher=teacher,
                        is_active=True,
                    )
                    .values_list("subject_assignment__classroom_id", flat=True)
                    .distinct()
                )
                items = StudentProfile.objects.filter(
                    q_object,
                    is_active=True,
                    classroom_id__in=classroom_ids,
                )[:limit]
            elif role == User.Role.PARENT:
                from apps.people.models import StudentGuardian

                student_ids = StudentGuardian.objects.filter(
                    guardian_user=user,
                    can_view_results=True,
                ).values_list("student_id", flat=True)
                items = StudentProfile.objects.filter(
                    q_object,
                    is_active=True,
                    id__in=student_ids,
                )[:limit]
            elif role == User.Role.STUDENT:
                try:
                    StudentProfile._meta.get_field("user")
                    items = StudentProfile.objects.filter(
                        q_object, user=user, is_active=True
                    )[:limit]
                except FieldDoesNotExist:
                    return results
            else:
                return results

            for item in items:
                results.append(
                    {
                        "id": item.id,
                        "type": "student",
                        "title": f"{item.last_name} {item.first_name}",
                        "description": f"{item.classroom.name} - Code: {item.student_code}",
                        "url": self._student_url(user, item),
                        "icon": "bi-person",
                    }
                )

        elif config["model"] == "TeacherProfile":
            from apps.people.models import TeacherProfile

            role = getattr(user, "role", None)
            if not (user.is_staff or user.is_superuser or role in self.ELEVATED_ROLES):
                return results

            base = TeacherProfile.objects.filter(q_object, user__is_active=True)
            if school is not None:
                base = base.filter(school=school)
            items = base[:limit]
            for item in items:
                results.append(
                    {
                        "id": item.id,
                        "type": "teacher",
                        "title": item.user.get_full_name(),
                        "description": f"Staff ID: {item.staff_id}",
                        "url": self._teacher_url(user, item),
                        "icon": "bi-person-badge",
                    }
                )

        elif config["model"] == "Classroom":
            from apps.academics.models import Classroom

            base = Classroom.objects.filter(q_object)
            if school is not None:
                base = base.filter(school=school)
            items = base[:limit]
            for item in items:
                results.append(
                    {
                        "id": item.id,
                        "type": "class",
                        "title": item.name,
                        "description": f"Code: {item.code}",
                        "url": self._classroom_url(user, item),
                        "icon": "bi-people",
                    }
                )

        elif config["model"] == "Subject":
            from apps.academics.models import Subject

            base = Subject.objects.filter(q_object)
            if school is not None:
                base = base.filter(school=school)
            items = base[:limit]
            for item in items:
                results.append(
                    {
                        "id": item.id,
                        "type": "subject",
                        "title": item.name,
                        "description": f"Category: {item.get_category_display()}",
                        "url": self._subject_url(user, item),
                        "icon": "bi-book",
                    }
                )

        elif config["model"] == "Invoice":
            from apps.finance.models import Invoice

            role = getattr(user, "role", None)
            base = Invoice.objects.filter(q_object)
            if school is not None:
                base = base.filter(school=school)
            if user.is_staff or user.is_superuser or role in self.FINANCE_ROLES:
                items = base[:limit]
            elif role == User.Role.PARENT:
                from apps.people.models import StudentGuardian

                student_ids = StudentGuardian.objects.filter(
                    guardian_user=user,
                    can_view_finance=True,
                ).values_list("student_id", flat=True)
                items = base.filter(student_id__in=student_ids)[:limit]
            elif role == User.Role.STUDENT:
                try:
                    from apps.people.models import StudentProfile

                    StudentProfile._meta.get_field("user")
                    student_profile = StudentProfile.objects.filter(user=user).first()
                except FieldDoesNotExist:
                    student_profile = None
                if not student_profile:
                    return results
                items = base.filter(student=student_profile)[:limit]
            else:
                return results

            for item in items:
                results.append(
                    {
                        "id": item.id,
                        "type": "invoice",
                        "title": f"Invoice #{item.id}",
                        "description": f"Student: {item.student.first_name} {item.student.last_name}"
                        if item.student
                        else "Student: N/A",
                        "url": self._invoice_url(item),
                        "icon": "bi-receipt",
                    }
                )

        return results


@method_decorator(login_required, name="dispatch")
class SearchSuggestionsAPI(View):
    """
    Get search suggestions for autocomplete.
    Section 25.3: cache key is tenant-scoped so same user in multiple schools has separate history.
    """

    def get(self, request):
        from django.core.cache import cache
        from apps.siteconfig.cache_utils import tenant_cache_key
from apps.accounts.models import User  # role enum

        key = tenant_cache_key(f"search_history_{request.user.id}", request)
        history = cache.get(key, [])

        return JsonResponse(
            {
                "suggestions": history[-5:]  # Last 5 searches
            }
        )
