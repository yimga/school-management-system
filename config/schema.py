"""
Full GraphQL schema (optional/future-work pool).
Query: health, me { username, email, isStaff }, schoolCount (staff only), schools { id, name, slug } (staff only).
"""

import graphene
from django.contrib.auth import get_user_model
from django.db import DatabaseError, OperationalError, ProgrammingError

from apps.schools.control_plane import user_has_control_plane_access

User = get_user_model()

# §2.4: Typed tuple for GraphQL school registry resolve (allowlist 0).
_GRAPHQL_SCHOOL_RESOLVE_ERRORS = (
    ImportError,
    AttributeError,
    TypeError,
    ValueError,
    DatabaseError,
    OperationalError,
    ProgrammingError,
)


def _can_access_global_school_registry(request) -> bool:
    if request is None:
        return False
    user = getattr(request, "user", None)
    if not user_has_control_plane_access(user):
        return False
    host_kind = (getattr(request, "public_host_kind", None) or "").lower()
    return host_kind == "manager"


class UserType(graphene.ObjectType):
    username = graphene.String()
    email = graphene.String()
    is_staff = graphene.Boolean()
    is_superuser = graphene.Boolean()

    def resolve_username(self, info):
        return getattr(self, "username", None) or ""

    def resolve_email(self, info):
        return getattr(self, "email", None) or ""

    def resolve_is_staff(self, info):
        return getattr(self, "is_staff", False)

    def resolve_is_superuser(self, info):
        return getattr(self, "is_superuser", False)


class SchoolType(graphene.ObjectType):
    id = graphene.ID()
    name = graphene.String()
    slug = graphene.String()

    def resolve_id(self, info):
        return str(self.pk) if self.pk else None

    def resolve_name(self, info):
        return getattr(self, "name", None) or ""

    def resolve_slug(self, info):
        return getattr(self, "slug", None) or ""


class Query(graphene.ObjectType):
    health = graphene.String()
    me = graphene.Field(UserType)
    school_count = graphene.Int()
    schools = graphene.List(SchoolType, limit=graphene.Int(default_value=20))

    def resolve_health(self, info):
        return "ok"

    def resolve_me(self, info):
        user = getattr(info.context, "user", None)
        if not user or not getattr(user, "is_authenticated", False):
            return None
        return user

    def resolve_school_count(self, info):
        request = getattr(info, "context", None)
        if not _can_access_global_school_registry(request):
            return None
        try:
            from apps.schools.models import School

            return School.objects.filter(is_active=True).count()
        except _GRAPHQL_SCHOOL_RESOLVE_ERRORS:
            return None

    def resolve_schools(self, info, limit=20):
        request = getattr(info, "context", None)
        if not _can_access_global_school_registry(request):
            return []
        try:
            from apps.schools.models import School

            return list(
                School.objects.filter(is_active=True).order_by("name")[
                    : max(1, min(limit, 100))
                ]
            )
        except _GRAPHQL_SCHOOL_RESOLVE_ERRORS:
            return []


schema = graphene.Schema(query=Query)
