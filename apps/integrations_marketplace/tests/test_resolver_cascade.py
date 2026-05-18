"""Cascade resolver tests — campus → school → parent_school → env_default."""

from __future__ import annotations

import json
import os
from unittest import mock

from django.test import TestCase

from apps.integrations_marketplace.resolver import (
    list_connections_for_school,
    resolve_connector_config,
)
from apps.schoolops.models import Campus
from apps.schools.models import School
from apps.siteconfig.models_platform_catalog import ServiceIntegration


def _make_school(name: str, parent: School | None = None) -> School:
    import uuid

    slug = f"{name.lower()}-{uuid.uuid4().hex[:8]}"
    return School.objects.create(
        name=name,
        slug=slug,
        subdomain=slug,
        parent_school=parent,
    )


def _make_si(*, school, campus=None, slug: str, config: dict, scopes=None, active=True):
    return ServiceIntegration.objects.create(
        school=school,
        campus=campus,
        connector_slug=slug,
        service_name=slug,
        service_type=ServiceIntegration.ServiceType.OAUTH,
        config=config,
        enabled_scopes=scopes or [],
        is_active=active,
    )


class ResolverUnknownConnectorTests(TestCase):
    def test_unknown_slug_returns_none(self):
        school = _make_school("Alpha")
        self.assertIsNone(
            resolve_connector_config("not-a-real-slug", school=school)
        )

    def test_valid_slug_no_config_returns_source_none(self):
        school = _make_school("Alpha")
        resolved = resolve_connector_config("zoom", school=school)
        self.assertIsNotNone(resolved)
        self.assertEqual(resolved.source, "none")
        self.assertFalse(resolved.is_configured)


class ResolverPerScopeTests(TestCase):
    def test_school_scoped_row_wins_when_only_one_exists(self):
        school = _make_school("Alpha")
        _make_si(school=school, slug="zoom", config={"access_token": "school-tok"})

        resolved = resolve_connector_config("zoom", school=school)
        self.assertEqual(resolved.source, "school")
        self.assertEqual(resolved.config["access_token"], "school-tok")
        self.assertTrue(resolved.is_configured)

    def test_campus_scoped_row_overrides_school_row(self):
        school = _make_school("Alpha")
        campus = Campus.objects.create(school=school, name="North")
        _make_si(school=school, slug="zoom", config={"access_token": "school-tok"})
        _make_si(
            school=school, campus=campus, slug="zoom",
            config={"access_token": "campus-tok"},
        )

        resolved = resolve_connector_config("zoom", school=school, campus=campus)
        self.assertEqual(resolved.source, "campus")
        self.assertEqual(resolved.config["access_token"], "campus-tok")

    def test_campus_lookup_falls_back_to_school_when_no_campus_row(self):
        school = _make_school("Alpha")
        campus = Campus.objects.create(school=school, name="South")
        _make_si(school=school, slug="zoom", config={"access_token": "school-tok"})

        resolved = resolve_connector_config("zoom", school=school, campus=campus)
        self.assertEqual(resolved.source, "school")
        self.assertEqual(resolved.config["access_token"], "school-tok")


class ResolverParentSchoolTests(TestCase):
    def test_child_school_inherits_parent_school_row(self):
        district = _make_school("District")
        child = _make_school("Child A", parent=district)
        _make_si(school=district, slug="zoom", config={"access_token": "district-tok"})

        resolved = resolve_connector_config("zoom", school=child)
        self.assertEqual(resolved.source, f"parent_school:{district.pk}")
        self.assertEqual(resolved.config["access_token"], "district-tok")

    def test_child_school_overrides_parent_when_own_row_exists(self):
        district = _make_school("District")
        child = _make_school("Child A", parent=district)
        _make_si(school=district, slug="zoom", config={"access_token": "district-tok"})
        _make_si(school=child, slug="zoom", config={"access_token": "child-tok"})

        resolved = resolve_connector_config("zoom", school=child)
        self.assertEqual(resolved.source, "school")
        self.assertEqual(resolved.config["access_token"], "child-tok")

    def test_grandchild_walks_two_levels_up(self):
        district = _make_school("District")
        middle = _make_school("Region East", parent=district)
        leaf = _make_school("Campus 1", parent=middle)
        _make_si(school=district, slug="zoom", config={"access_token": "district-tok"})

        resolved = resolve_connector_config("zoom", school=leaf)
        self.assertEqual(resolved.source, f"parent_school:{district.pk}")
        self.assertEqual(resolved.config["access_token"], "district-tok")


class ResolverInactiveRowsTests(TestCase):
    def test_inactive_school_row_is_skipped(self):
        district = _make_school("District")
        child = _make_school("Child A", parent=district)
        _make_si(school=district, slug="zoom", config={"access_token": "district-tok"})
        _make_si(
            school=child, slug="zoom", config={"access_token": "child-tok"}, active=False
        )

        resolved = resolve_connector_config("zoom", school=child)
        # Falls through to district because child's row is inactive.
        self.assertEqual(resolved.source, f"parent_school:{district.pk}")


class ResolverEnvDefaultTests(TestCase):
    def test_env_default_kicks_in_when_no_school_config(self):
        school = _make_school("Alpha")
        env = {
            "INTEGRATIONS_ZOOM_DEFAULT_CONFIG": json.dumps(
                {"access_token": "platform-default"}
            )
        }
        with mock.patch.dict(os.environ, env, clear=False):
            resolved = resolve_connector_config("zoom", school=school)
        self.assertEqual(resolved.source, "env_default")
        self.assertEqual(resolved.config["access_token"], "platform-default")

    def test_school_row_wins_over_env_default(self):
        school = _make_school("Alpha")
        _make_si(school=school, slug="zoom", config={"access_token": "school-tok"})
        env = {
            "INTEGRATIONS_ZOOM_DEFAULT_CONFIG": json.dumps(
                {"access_token": "platform-default"}
            )
        }
        with mock.patch.dict(os.environ, env, clear=False):
            resolved = resolve_connector_config("zoom", school=school)
        self.assertEqual(resolved.source, "school")
        self.assertEqual(resolved.config["access_token"], "school-tok")

    def test_invalid_json_env_is_ignored(self):
        school = _make_school("Alpha")
        env = {"INTEGRATIONS_ZOOM_DEFAULT_CONFIG": "{not json"}
        with mock.patch.dict(os.environ, env, clear=False):
            resolved = resolve_connector_config("zoom", school=school)
        self.assertEqual(resolved.source, "none")


class HubListingTests(TestCase):
    def test_list_connections_for_school_includes_every_registry_slug(self):
        school = _make_school("Alpha")
        entries = list_connections_for_school(school)
        slugs = {e["connector"]["slug"] for e in entries}
        for required in {"zoom", "slack", "microsoft_teams", "sendgrid"}:
            self.assertIn(required, slugs)

    def test_list_connections_marks_configured_rows(self):
        school = _make_school("Alpha")
        _make_si(school=school, slug="zoom", config={"access_token": "tok"})
        entries = list_connections_for_school(school)
        by_slug = {e["connector"]["slug"]: e for e in entries}
        self.assertTrue(by_slug["zoom"]["is_configured"])
        self.assertFalse(by_slug["slack"]["is_configured"])
