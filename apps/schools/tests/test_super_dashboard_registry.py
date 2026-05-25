"""Registry pagination and fleet metrics for super dashboard at scale."""

from django.test import TestCase, RequestFactory

from apps.schools.models import School
from apps.schools.super_dashboard_registry import (
    apply_registry_filters,
    build_registry_queryset,
    compute_fleet_registry_metrics,
    parse_registry_page_size,
    paginate_registry,
)


class SuperDashboardRegistryTests(TestCase):
    def setUp(self):
        self.factory = RequestFactory()

    def test_parse_registry_page_size_defaults_and_clamps(self):
        request = self.factory.get("/super/", {"page_size": "999"})
        self.assertEqual(parse_registry_page_size(request), 25)
        request = self.factory.get("/super/", {"page_size": "50"})
        self.assertEqual(parse_registry_page_size(request), 50)

    def test_fleet_metrics_empty_fleet(self):
        metrics = compute_fleet_registry_metrics(
            incident_school_ids=set(),
            churn_risk_school_ids=set(),
        )
        self.assertEqual(metrics.school_count, 0)
        self.assertEqual(metrics.countries_live_count, 0)

    def test_paginate_registry_returns_page(self):
        School.objects.create(name="Alpha Academy", slug="alpha", is_approved=True)
        School.objects.create(name="Beta School", slug="beta", is_approved=True)
        request = self.factory.get("/super/", {"page_size": "25"})
        page, search, state, page_size, extra = paginate_registry(
            request,
            incident_school_ids=set(),
            churn_risk_school_ids=set(),
            churn_risk_lookup={},
            country_names={},
            brand_profile_ids=set(),
        )
        self.assertEqual(page.paginator.count, 2)
        self.assertEqual(len(list(page.object_list)), 2)
        self.assertEqual(state, "all")
        self.assertEqual(search, "")

    def test_apply_registry_filters_search(self):
        School.objects.create(name="Unique Zephyr", slug="zephyr", is_approved=True)
        School.objects.create(name="Other", slug="other", is_approved=True)
        qs = apply_registry_filters(
            build_registry_queryset(),
            search="zephyr",
            state="all",
            incident_school_ids=set(),
            churn_risk_school_ids=set(),
        )
        self.assertEqual(qs.count(), 1)
