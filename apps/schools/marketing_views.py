"""
RunMyCampus marketing and SEO endpoints.
"""
from __future__ import annotations

import json
import os
import random
from copy import deepcopy
from datetime import datetime, timezone as dt_timezone
from urllib.parse import urlparse

from django.conf import settings
from django.contrib.admin.views.decorators import staff_member_required
from django.templatetags.static import static
from django.db.models import Count, Q
from django.http import Http404, HttpResponse
from django.shortcuts import render, redirect
from django.urls import NoReverseMatch, reverse
from django.utils import timezone
from django.views.decorators.http import require_GET, require_POST
from django.views.decorators.csrf import csrf_protect

from apps.schools.host_routing import get_canonical_base_domain
from apps.siteconfig.brand_registry import resolve_global_brand_context
from apps.siteconfig.global_catalog import GlobalGeoCatalog

# Optional: region/variant for future A/B or regional content (file naming: slug.json or slug_region_variant.json).
MARKETING_CONTENT_DIR = os.path.join(getattr(settings, "BASE_DIR", os.getcwd()), "config", "marketing_content")


def _load_marketing_page_from_file(
    slug: str,
    region: str | None = None,
    variant: str | None = None,
) -> tuple[dict, dict] | None:
    """
    Load marketing page content from config/marketing_content/{slug}.json.
    Returns (page_dict, extras_dict) compatible with marketing_page template, or None if file missing/invalid.
    Optional region/variant allow future file names like slug_region_variant.json for regional or A/B content.
    """
    slug = (slug or "").strip().lower()
    if not slug:
        return None
    # Try region/variant-specific file first if provided (future use)
    candidates = [f"{slug}.json"]
    if region:
        candidates.insert(0, f"{slug}_{region}.json")
    if region and variant:
        candidates.insert(0, f"{slug}_{region}_{variant}.json")
    for filename in candidates:
        path = os.path.join(MARKETING_CONTENT_DIR, filename)
        if not os.path.isfile(path):
            continue
        try:
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
        except (json.JSONDecodeError, OSError):
            continue
        if not isinstance(data, dict):
            continue
        # Build page dict: label, seo_title, seo_description, headline, subheadline, schema_type, segments
        page = {
            "label": data.get("label", ""),
            "seo_title": data.get("seo_title", ""),
            "seo_description": data.get("seo_description", ""),
            "headline": data.get("headline", ""),
            "subheadline": data.get("subheadline", ""),
            "schema_type": data.get("schema_type", "WebPage"),
            "segments": data.get("segments") if isinstance(data.get("segments"), list) else [],
        }
        extras = data.get("extras")
        if not isinstance(extras, dict):
            extras = {}
        return (page, extras)
    return None


MARKETING_PAGE_DEFINITIONS = {
    "product": {
        "label": "Product",
        "seo_title": "RunMyCampus Product - Unified school operations platform",
        "seo_description": "One platform for admissions, academics, finance, communication, and compliance across every campus.",
        "headline": "One operating system for every school workflow.",
        "subheadline": "Run admissions, academics, billing, communication, and compliance from a single tenant-first platform.",
        "schema_type": "SoftwareApplication",
        "segments": [
            {
                "title": "AI Co-pilot",
                "body": "Smart assistance for workflows, reporting, and decision support across admissions, academics, and operations.",
            },
            {
                "title": "Real-time Analytics",
                "body": "Live dashboards, enrollment and attendance trends, and actionable insights for school leaders.",
            },
            {
                "title": "Customizable Workflows",
                "body": "Adapt processes, forms, and approval chains to your school's policies without custom code.",
            },
            {
                "title": "Unified data model",
                "body": "Students, staff, payments, reports, and interventions share one source of truth.",
            },
            {
                "title": "Role-ready portals",
                "body": "School admins, teachers, parents, and students get purpose-built workflows.",
            },
            {
                "title": "Global tenancy",
                "body": "Operate one campus or many with domain, policy, and branding isolation.",
            },
        ],
    },
    "products-admissions": {
        "label": "Admissions",
        "seo_title": "Admissions & Enrollment | RunMyCampus",
        "seo_description": "Automate admissions from application to enrollment. Capture leads, track applications, waitlists, and communications.",
        "headline": "Automate admissions from application to enrollment.",
        "subheadline": "Capture leads, qualify applicants, and onboard students in one configurable flow.",
        "schema_type": "WebPage",
        "segments": [
            {"title": "Application workflow", "body": "From enquiry to decision with configurable stages and automation."},
            {"title": "Waitlists & communications", "body": "Manage waitlists and automated parent and staff communications."},
            {"title": "Analytics", "body": "Funnel and conversion dashboards for admissions leads and enrollment."},
        ],
    },
    "products-academics": {
        "label": "Academics",
        "seo_title": "Academics & Grades | RunMyCampus",
        "seo_description": "Syllabi, attendance, report cards, and interventions in one platform. Teacher and admin dashboards.",
        "headline": "Academics and grades in one place.",
        "subheadline": "Syllabi, attendance, report cards, and interventions with role-ready dashboards.",
        "schema_type": "WebPage",
        "segments": [
            {"title": "Grades and report cards", "body": "Configurable grading scales, report cards, and transcript-ready exports."},
            {"title": "Attendance", "body": "Daily attendance, trends, and early intervention signals."},
            {"title": "Teacher dashboard", "body": "One place for classes, grading, and parent communication."},
        ],
    },
    "products-finance": {
        "label": "Finance",
        "seo_title": "Finance & Billing | RunMyCampus",
        "seo_description": "Tuition billing, payment tracking, scholarships, and financial reporting for schools.",
        "headline": "Finance and billing tailored to schools.",
        "subheadline": "Fees, payments, and financial reporting without spreadsheets.",
        "schema_type": "WebPage",
        "segments": [
            {"title": "Tuition and fees", "body": "Billing cycles, payment plans, and fee structures by program or grade."},
            {"title": "Payment tracking", "body": "Payment gateways, receipts, and reconciliation in one place."},
            {"title": "Reporting", "body": "Financial dashboards and export-ready reports for leadership and auditors."},
        ],
    },
    "products-communication": {
        "label": "Communication",
        "seo_title": "Communication & Portals | RunMyCampus",
        "seo_description": "Role-ready portals for parents, teachers, and students. Messaging and announcements.",
        "headline": "Communication that reaches every role.",
        "subheadline": "Parents, teachers, and students stay connected with purpose-built portals.",
        "schema_type": "WebPage",
        "segments": [
            {"title": "Parent portal", "body": "Attendance, grades, fees, and messages in one place for families."},
            {"title": "Teacher and student portals", "body": "Class tools, assignments, and school-wide announcements."},
            {"title": "Messaging", "body": "SMS and email providers with governed templates and delivery tracking."},
        ],
    },
    "products-automation": {
        "label": "Automation",
        "seo_title": "Workflow Automation | RunMyCampus",
        "seo_description": "Configurable workflows: from grade-drop alerts to parent notifications and tutoring assignment.",
        "headline": "Automate school operations.",
        "subheadline": "Build flows without code: triggers, conditions, and actions that scale.",
        "schema_type": "WebPage",
        "segments": [
            {"title": "Triggers", "body": "Grade changes, attendance patterns, payments, and custom events."},
            {"title": "Actions", "body": "Notify teacher, notify parent, assign intervention, or update records."},
            {"title": "Visibility", "body": "Audit trails and dashboards for every automated step."},
        ],
    },
    "products-analytics": {
        "label": "Analytics",
        "seo_title": "Analytics & Reporting | RunMyCampus",
        "seo_description": "Real-time dashboards, enrollment and attendance trends, and actionable insights for school leaders.",
        "headline": "Analytics that inform decisions.",
        "subheadline": "Live dashboards, trends, and reports for enrollment, attendance, and outcomes.",
        "schema_type": "WebPage",
        "segments": [
            {"title": "Leader dashboards", "body": "Enrollment, attendance, and performance at a glance."},
            {"title": "Trends and reports", "body": "Export-ready reports and trend analysis for boards and regulators."},
            {"title": "AI insights", "body": "Predictive signals and recommended interventions where enabled."},
        ],
    },
    "school-management-system": {
        "label": "School Management System",
        "seo_title": "School Management System | RunMyCampus - One Platform for K-12 and Higher Ed",
        "seo_description": "Unified school management system for admissions, academics, finance, communication, and compliance. One platform for K-12 and higher ed.",
        "headline": "The school management system that scales.",
        "subheadline": "One platform for admissions, academics, finance, communication, and compliance—from single campus to multi-country.",
        "schema_type": "WebPage",
        "segments": [
            {"title": "Unified operations", "body": "Replace spreadsheets and point solutions with one tenant-first platform."},
            {"title": "K-12 and higher ed", "body": "Purpose-built workflows for every institution type."},
            {"title": "Multi-tenant from day one", "body": "Each school gets its own domain, branding, and data isolation."},
        ],
    },
    "student-information-system": {
        "label": "Student Information System",
        "seo_title": "Student Information System (SIS) | RunMyCampus",
        "seo_description": "Cloud-based student information system: enrollment, grades, attendance, and parent portals in one place.",
        "headline": "Student information system that connects everyone.",
        "subheadline": "Enrollment, grades, attendance, and parent communication in one secure platform.",
        "schema_type": "WebPage",
        "segments": [
            {"title": "Student 360", "body": "One view per student: profile, attendance, grades, and interventions."},
            {"title": "Role-ready portals", "body": "Admins, teachers, parents, and students get the right data and tools."},
            {"title": "Reporting and compliance", "body": "Export-ready reports and regional compliance defaults."},
        ],
    },
    "education-erp": {
        "label": "Education ERP",
        "seo_title": "Education ERP | RunMyCampus - Unified School Operations",
        "seo_description": "Education ERP for schools: academics, finance, HR, and operations in one platform. Multi-campus and multi-country ready.",
        "headline": "Education ERP that runs your entire operation.",
        "subheadline": "Academics, finance, HR, and operations in one platform—from single school to enterprise.",
        "schema_type": "WebPage",
        "segments": [
            {"title": "End-to-end operations", "body": "From admissions to graduation, finance to compliance, in one system."},
            {"title": "Multi-campus", "body": "Central oversight with campus-level autonomy and branding."},
            {"title": "Global-ready", "body": "Multi-currency, multi-language, and country-specific compliance."},
        ],
    },
    "school-administration-software": {
        "label": "School Administration Software",
        "seo_title": "School Administration Software | RunMyCampus",
        "seo_description": "School administration software for admins, principals, and district leaders. Dashboards, workflows, and reporting in one place.",
        "headline": "School administration software that empowers leaders.",
        "subheadline": "Dashboards, workflows, and reporting for admins, principals, and district leaders.",
        "schema_type": "WebPage",
        "segments": [
            {"title": "Admin dashboards", "body": "Enrollment, attendance, finance, and compliance at a glance."},
            {"title": "Configurable workflows", "body": "Approvals, communications, and processes without custom code."},
            {"title": "Audit and reporting", "body": "Audit trails and export-ready reports for boards and regulators."},
        ],
    },
    "solutions": {
        "label": "Solutions",
        "seo_title": "RunMyCampus Solutions - K12, multi-campus, and private schools",
        "seo_description": "Purpose-built deployment patterns for private schools, district networks, and multi-campus operators.",
        "headline": "Solutions aligned to your school model.",
        "subheadline": "Deploy fast with templates for private schools, district groups, and multi-entity education organizations.",
        "schema_type": "CollectionPage",
        "segments": [
            {
                "title": "Single-campus schools",
                "body": "Launch quickly with ready workflows for onboarding, grading, fee management, and reporting.",
            },
            {
                "title": "Multi-campus networks",
                "body": "Standardize operations while preserving campus-level autonomy and identity.",
            },
            {
                "title": "Regional operators",
                "body": "Use localization controls for language, compliance profiles, terms, and grading systems.",
            },
        ],
    },
    "pricing": {
        "label": "Pricing",
        "seo_title": "RunMyCampus Pricing - Transparent plans for growing schools",
        "seo_description": "Transparent school management pricing with plan tiers, add-ons, and enterprise deployment options.",
        "headline": "Pricing that scales with your campus.",
        "subheadline": "Choose a plan by operating model, unlock add-ons, and keep billing visibility across every tenant.",
        "schema_type": "OfferCatalog",
        "segments": [
            {
                "title": "Plan clarity",
                "body": "Map plans to usage, student volume, and feature needs without hidden complexity.",
            },
            {
                "title": "Add-on flexibility",
                "body": "Enable advanced modules as your school grows, from integrations to analytics.",
            },
            {
                "title": "Super-admin oversight",
                "body": "Track trial status, usage, and billing posture in one command center.",
            },
        ],
    },
    "compare": {
        "label": "Compare",
        "seo_title": "RunMyCampus Compare - Evaluate school management alternatives",
        "seo_description": "Compare tenant architecture, admin controls, and parent/teacher experience before choosing your platform.",
        "headline": "Compare on architecture, not just feature count.",
        "subheadline": "Use objective criteria to evaluate tenancy, security, workflow depth, and long-term operational fit.",
        "schema_type": "WebPage",
        "segments": [
            {
                "title": "Tenant isolation",
                "body": "Each school can run on dedicated domain, controls, and policy boundaries.",
            },
            {
                "title": "Operational depth",
                "body": "Finance, academics, support, and compliance are first-class modules, not bolt-ons.",
            },
            {
                "title": "Command center visibility",
                "body": "Super-admin workflows centralize approvals, support queues, and health indicators.",
            },
        ],
    },
    "case-studies": {
        "label": "Case Studies",
        "seo_title": "RunMyCampus Case Studies - Real school implementation outcomes",
        "seo_description": "See how schools improve onboarding speed, intervention outcomes, and operational control with RunMyCampus.",
        "headline": "Results from real school operations.",
        "subheadline": "Case patterns show how teams reduce onboarding friction, improve intervention response, and scale governance.",
        "schema_type": "CollectionPage",
        "segments": [
            {
                "title": "Faster onboarding",
                "body": "New campuses provision with clearer timelines and less manual setup overhead.",
            },
            {
                "title": "Better intervention response",
                "body": "Risk monitoring and action-center workflows improve follow-through for at-risk learners.",
            },
            {
                "title": "Higher support visibility",
                "body": "Global queues and SLA tracking reduce blind spots across growing tenant portfolios.",
            },
        ],
    },
    "security-compliance": {
        "label": "Security & Compliance",
        "seo_title": "RunMyCampus Security & Compliance - FERPA/GDPR-ready controls",
        "seo_description": "Security-first tenancy with audit trails, access controls, compliance regions, and operational monitoring.",
        "headline": "Security and compliance built into daily operations.",
        "subheadline": "Protect tenant data with auditability, policy controls, and region-aware compliance defaults.",
        "schema_type": "WebPage",
        "segments": [
            {
                "title": "Tenant-scoped controls",
                "body": "Data access, policy settings, and activity traces stay scoped to each school.",
            },
            {
                "title": "Audit readiness",
                "body": "Operational events, support actions, and administrative changes remain reviewable.",
            },
            {
                "title": "Regional compliance posture",
                "body": "Map schools to compliance regions and align workflows to local obligations.",
            },
        ],
    },
    "security": {
        "label": "Security",
        "seo_title": "RunMyCampus Security - Architecture and encryption",
        "seo_description": "Security architecture, encryption at rest and in transit, and access controls for RunMyCampus.",
        "headline": "Security by design.",
        "subheadline": "Encryption, tenant isolation, and access controls protect your school data.",
        "schema_type": "WebPage",
        "segments": [
            {"title": "Architecture", "body": "Subdomain tenant isolation; dedicated host contract for public, tenant, and manager surfaces."},
            {"title": "Encryption", "body": "Encryption at rest and in transit; secrets and credentials managed securely."},
            {"title": "Access controls", "body": "Role-based access and audit trails for all administrative and support actions."},
        ],
    },
    "compliance": {
        "label": "Compliance",
        "seo_title": "RunMyCampus Compliance - FERPA, GDPR, regional",
        "seo_description": "Compliance posture for FERPA, GDPR, and regional education regulations.",
        "headline": "Compliance that scales with you.",
        "subheadline": "FERPA and GDPR-aligned workflows; regional compliance defaults and audit readiness.",
        "schema_type": "WebPage",
        "segments": [
            {"title": "FERPA alignment", "body": "Student record access and disclosure controls aligned to FERPA practices."},
            {"title": "GDPR readiness", "body": "Data subject rights, lawful basis, and cross-border transfer considerations."},
            {"title": "Regional defaults", "body": "Country-specific compliance profiles and terminology from the global registry."},
        ],
    },
    "ferpa": {
        "label": "FERPA",
        "seo_title": "RunMyCampus and FERPA - Student privacy",
        "seo_description": "How RunMyCampus supports FERPA-aligned student record and privacy practices.",
        "headline": "FERPA-aligned student record practices.",
        "subheadline": "Access controls, audit trails, and disclosure safeguards for education records.",
        "schema_type": "WebPage",
        "segments": [
            {"title": "Access and disclosure", "body": "Role-based access to education records; audit trails for disclosure events."},
            {"title": "Consent and consent management", "body": "Where applicable, consent and preference controls for sharing and communications."},
        ],
    },
    "gdpr": {
        "label": "GDPR",
        "seo_title": "RunMyCampus and GDPR - Data protection",
        "seo_description": "GDPR and EU data protection alignment for RunMyCampus.",
        "headline": "GDPR and data protection alignment.",
        "subheadline": "Lawful basis, data subject rights, and cross-border transfer considerations.",
        "schema_type": "WebPage",
        "segments": [
            {"title": "Lawful basis and purpose", "body": "Processing aligned to contract and legitimate interest where appropriate."},
            {"title": "Data subject rights", "body": "Access, rectification, erasure, and portability support via platform and processes."},
            {"title": "Cross-border and DPA", "body": "Transfer mechanisms and data processing agreements where required."},
        ],
    },
    "lgpd": {
        "label": "LGPD",
        "seo_title": "RunMyCampus and LGPD - Brazilian data protection",
        "seo_description": "LGPD (Lei Geral de Proteção de Dados) alignment for RunMyCampus.",
        "headline": "LGPD alignment for Brazilian operations.",
        "subheadline": "Data processing in line with LGPD principles and legal basis.",
        "schema_type": "WebPage",
        "segments": [
            {"title": "Legal basis", "body": "Processing based on consent, contract, or legitimate interest as appropriate."},
            {"title": "Rights of data subjects", "body": "Access, correction, deletion, and portability in line with LGPD."},
        ],
    },
    "integrations": {
        "label": "Integrations",
        "seo_title": "RunMyCampus Integrations - SIS, LMS, payments, and messaging",
        "seo_description": "Integrate LMS, payment gateways, messaging providers, and external services with governance controls.",
        "headline": "Integrations with governance, not chaos.",
        "subheadline": "Connect external systems while controlling activation, audit context, and operational blast radius.",
        "schema_type": "ItemList",
        "segments": [
            {
                "title": "Integration registry",
                "body": "Manage service entries and switch states in one governed control surface.",
            },
            {
                "title": "Interoperability APIs",
                "body": "Expose standards-aware endpoints for identity, academic workflows, and data exchange.",
            },
            {
                "title": "Operational safeguards",
                "body": "Track reasons, activity, and changes for every integration toggle.",
            },
        ],
    },
    "book-demo": {
        "label": "Book Demo",
        "seo_title": "Book a RunMyCampus Demo - See tenant operations live",
        "seo_description": "Schedule a platform demo focused on public experience, tenant access, and super-admin command workflows.",
        "headline": "Book a focused platform walkthrough.",
        "subheadline": "See public discovery, tenant login flow, and super-admin command center in one guided demo.",
        "schema_type": "Service",
        "segments": [
            {
                "title": "Public growth flow",
                "body": "Review SEO pages, discovery UX, and conversion paths from first visit to trial.",
            },
            {
                "title": "Tenant experience",
                "body": "Validate portal access journeys for school admins, teachers, and parents.",
            },
            {
                "title": "Super-admin control",
                "body": "Inspect mission-control workflows for approvals, billing visibility, and support governance.",
            },
        ],
    },
    "about": {
        "label": "About",
        "seo_title": "About RunMyCampus - Global school operations platform",
        "seo_description": "Learn about RunMyCampus mission, team, and commitment to schools worldwide.",
        "headline": "About RunMyCampus.",
        "subheadline": "One platform for global school operations, built for 195 countries.",
        "schema_type": "WebPage",
        "segments": [
            {"title": "Mission", "body": "Empower every school with unified operations, compliance, and growth tools."},
            {"title": "Global reach", "body": "Multi-language, multi-currency, and data residency options for every region."},
            {"title": "Security first", "body": "Schema-per-tenant isolation and audit-ready controls for trust and compliance."},
        ],
    },
    "features": {
        "label": "Features",
        "seo_title": "RunMyCampus Features - Admissions, academics, finance, and more",
        "seo_description": "Explore features for admissions, academics, finance, communication, and compliance.",
        "headline": "Features that scale with your campus.",
        "subheadline": "From admissions to finance, one platform for every school workflow.",
        "schema_type": "CollectionPage",
        "segments": [
            {"title": "AI Co-pilot", "body": "Smart assistance for workflows, reporting, and decision support across the platform."},
            {"title": "Real-time Analytics", "body": "Live dashboards and actionable insights for enrollment, attendance, and operations."},
            {"title": "Customizable Workflows", "body": "Adapt processes, forms, and approvals to your school's policies."},
            {"title": "Admissions & enrollment", "body": "Online applications, applicant tracking, and enrollment management."},
            {"title": "Academics & grading", "body": "Curriculum, gradebooks, report cards, and metadata-driven rubrics."},
            {"title": "Finance & billing", "body": "Fee management, invoicing, multi-currency, and audit trail."},
        ],
    },
    "blog": {
        "label": "Blog",
        "seo_title": "RunMyCampus Blog - Topics for leading faculties",
        "seo_description": "Insights, product updates, and best practices for school operators.",
        "headline": "Topics of leading faculties.",
        "subheadline": "Product updates, best practices, and stories from schools worldwide.",
        "schema_type": "Blog",
        "segments": [
            {"title": "Product updates", "body": "New features and improvements to the RunMyCampus platform."},
            {"title": "Best practices", "body": "How schools use RunMyCampus for admissions, compliance, and operations."},
            {"title": "Global education", "body": "Trends and insights for K-12 and international school operations."},
        ],
    },
    "contact": {
        "label": "Contact Us",
        "seo_title": "Contact RunMyCampus - Get in touch",
        "seo_description": "Contact RunMyCampus for sales, support, or partnership inquiries.",
        "headline": "Contact us.",
        "subheadline": "Sales, support, and partnership inquiries. We respond within 24 hours.",
        "schema_type": "ContactPage",
        "segments": [
            {"title": "Sales", "body": "Request a demo or discuss plans for your school or network."},
            {"title": "Support", "body": "Existing customers can reach 24/7 support via the tenant portal or support hub."},
            {"title": "Partnerships", "body": "Integrations, resellers, and technology partners."},
        ],
    },
    "privacy": {
        "label": "Privacy Policy",
        "seo_title": "RunMyCampus Privacy Policy",
        "seo_description": "How RunMyCampus collects, uses, and protects your data.",
        "headline": "Privacy Policy",
        "subheadline": "How we collect, use, and protect your data. FERPA and GDPR aligned.",
        "schema_type": "WebPage",
        "segments": [
            {"title": "Data we collect", "body": "Account, usage, and school data necessary to operate the platform."},
            {"title": "How we use it", "body": "To provide and improve the service, support, and compliance."},
            {"title": "Your rights", "body": "Access, correction, deletion, and portability where applicable by law."},
        ],
    },
    "terms": {
        "label": "Terms of Service",
        "seo_title": "RunMyCampus Terms of Service",
        "seo_description": "Terms of service for the RunMyCampus platform.",
        "headline": "Terms of Service",
        "subheadline": "Terms governing use of the RunMyCampus platform and services.",
        "schema_type": "WebPage",
        "segments": [
            {"title": "Acceptance", "body": "By using the platform you agree to these terms."},
            {"title": "Use of service", "body": "Permitted use, account responsibility, and acceptable use."},
            {"title": "Limitation of liability", "body": "Standard limitations as permitted by applicable law."},
        ],
    },
    "cookie-policy": {
        "label": "Cookie Policy",
        "seo_title": "RunMyCampus Cookie Policy",
        "seo_description": "How RunMyCampus uses cookies and similar technologies on its public website.",
        "headline": "Cookie Policy",
        "subheadline": "How we use cookies and similar technologies on our public website.",
        "schema_type": "WebPage",
        "segments": [
            {"title": "What we use", "body": "We use strictly necessary cookies for session and security. When analytics or chat widgets are enabled via settings, third-party cookies may be used; we document them in deployment settings."},
            {"title": "Your choices", "body": "You can disable non-essential cookies via browser settings. Essential cookies are required for the site to function."},
            {"title": "Updates", "body": "We may update this policy when we add or change features that use cookies. The date of the last update is reflected on this page."},
        ],
    },
    "developers": {
        "label": "Developers",
        "seo_title": "RunMyCampus Developer Portal - API & Integrations",
        "seo_description": "API documentation, authentication, rate limits, and integration guides for RunMyCampus.",
        "headline": "Developer Portal & API.",
        "subheadline": "Build integrations with versioned APIs, webhooks, and LTI. Auth, rate limiting, and OpenAPI documented.",
        "schema_type": "WebPage",
        "segments": [
            {"title": "API access", "body": "Authenticate with API keys or OAuth; versioned endpoints under /api/."},
            {"title": "Rate limiting", "body": "Per-tenant and per-IP limits; 429 with Retry-After for fair use."},
            {"title": "Integrations", "body": "LTI 1.3, OneRoster, webhooks, and custom integrations. See docs for details."},
        ],
    },
    # Section 11.5: Public website superiority — category clarity, vertical landings, migration-first, trust center, app marketplace
    "why-switch": {
        "label": "Why Switch",
        "seo_title": "Why Switch to RunMyCampus - Migration-first school management",
        "seo_description": "Migrate from spreadsheets or legacy SIS with minimal risk. Clear timelines, data import, and tenant isolation.",
        "headline": "Why switch to RunMyCampus.",
        "subheadline": "Migration-first design: bring your data, keep your workflows, gain one platform for operations.",
        "schema_type": "WebPage",
        "segments": [
            {"title": "Migration-first", "body": "Structured import paths and provisioning so you move data once and run on a single source of truth."},
            {"title": "No lock-in", "body": "Export and portability options so you stay in control of your school data."},
            {"title": "Same day readiness", "body": "Templates and blueprints get you live quickly without starting from scratch."},
        ],
    },
    "10-reasons": {
        "label": "10 Reasons",
        "seo_title": "10 Reasons Schools Choose RunMyCampus",
        "seo_description": "Why schools and operators choose RunMyCampus: one platform, multi-tenant from day one, global compliance, and migration support.",
        "headline": "10 reasons schools choose RunMyCampus.",
        "subheadline": "From single campus to enterprise white-label—one platform for admissions, academics, finance, and compliance.",
        "schema_type": "WebPage",
        "segments": [
            {"title": "One platform", "body": "Admissions, academics, finance, communication, and compliance in one place—no tool sprawl."},
            {"title": "Multi-tenant from day one", "body": "Each school gets its own domain, branding, and data isolation."},
            {"title": "Global compliance", "body": "FERPA, GDPR, and regional defaults. 195+ country-ready profiles."},
            {"title": "Migration support", "body": "Guided import, phased rollout, and dedicated support during go-live."},
            {"title": "Role-ready portals", "body": "Admins, teachers, parents, and students get purpose-built workflows."},
            {"title": "Operator command center", "body": "Super-admin visibility across tenants for approvals, support, and billing."},
            {"title": "Developer platform", "body": "APIs, webhooks, and an app marketplace to extend without custom code."},
            {"title": "Transparent pricing", "body": "Starter, Growth, and Enterprise plans that map to your stage."},
            {"title": "Security by design", "body": "Encryption at rest and in transit, audit trails, role-based access."},
            {"title": "We set you up", "body": "Dedicated onboarding and support—you're not just buying software."},
        ],
    },
    "resources": {
        "label": "Resources",
        "seo_title": "Resources - Reports, Guides, and Webinars | RunMyCampus",
        "seo_description": "Reports, implementation checklists, webinars, and best practices for school operations.",
        "headline": "Resources to run your campus.",
        "subheadline": "Reports, checklists, webinars, and guides—all in one place.",
        "schema_type": "CollectionPage",
        "segments": [
            {"title": "State of School Operations report", "body": "Download our flagship report on how schools are unifying operations."},
            {"title": "Buyer toolkit", "body": "Checklists and implementation timeline for evaluation and go-live."},
            {"title": "Webinars", "body": "Customer roundtables and migration best practices. Register for upcoming sessions."},
            {"title": "Blog", "body": "Admissions, finance, multi-campus, migration, and compliance topics."},
        ],
    },
    "events": {
        "label": "Events",
        "seo_title": "Events and Webinars | RunMyCampus",
        "seo_description": "Upcoming webinars, customer roundtables, and RunMyCampus Live—our annual education operations summit.",
        "headline": "Events and webinars.",
        "subheadline": "Join customer roundtables, webinars, and be first to know for RunMyCampus Live.",
        "schema_type": "WebPage",
        "segments": [
            {"title": "Customer roundtable", "body": "Monthly session: Migration in 90 days. Register for the next session."},
            {"title": "RunMyCampus Live", "body": "Annual education operations summit. Be first to know when we announce dates."},
        ],
    },
    "verticals": {
        "label": "By School Type",
        "seo_title": "RunMyCampus by School Type - K12, private, international, district",
        "seo_description": "Purpose-built for private K12, international schools, and multi-campus districts. ROI and workflows by vertical.",
        "headline": "Built for your school type.",
        "subheadline": "Vertical-specific workflows, compliance defaults, and ROI that match how you operate.",
        "schema_type": "CollectionPage",
        "segments": [
            {"title": "Private K12", "body": "Admissions, grading, fee management, and parent communication in one tenant."},
            {"title": "International schools", "body": "Multi-currency, multi-language, and region-aware compliance out of the box."},
            {"title": "Districts & networks", "body": "Multi-campus with central oversight and school-level autonomy."},
        ],
    },
    "trust-center": {
        "label": "Trust Center",
        "seo_title": "RunMyCampus Trust Center - Security, compliance, and privacy",
        "seo_description": "Security and compliance trust center: certifications, data handling, auditability, and regional compliance.",
        "headline": "Security and compliance trust center.",
        "subheadline": "Transparent security posture, compliance alignment, and audit-ready controls for schools and regulators.",
        "schema_type": "WebPage",
        "segments": [
            {"title": "Security", "body": "Tenant isolation, encryption, access controls, and audit logs as standard."},
            {"title": "Compliance", "body": "Region-aware defaults and workflows aligned to local education and data regulations."},
            {"title": "Transparency", "body": "Documented practices, runbooks, and support for audits and due diligence."},
        ],
    },
    "app-marketplace": {
        "label": "App Marketplace",
        "seo_title": "RunMyCampus App Marketplace - Extend your campus platform",
        "seo_description": "Discover apps and blueprints that extend RunMyCampus: integrations, themes, and workflow packs.",
        "headline": "App marketplace.",
        "subheadline": "Extend your platform with approved apps, blueprint packs, and integrations—governed and tenant-safe.",
        "schema_type": "ItemList",
        "segments": [
            {"title": "Blueprint packs", "body": "Pre-built policy and workflow bundles for faster setup and best practices."},
            {"title": "Integrations", "body": "LMS, payments, messaging, and data exchange with versioning and kill switches."},
            {"title": "Governed rollout", "body": "Review pipeline, permission scopes, and sandbox so only safe extensions reach your tenant."},
        ],
    },
    # Section 11.5: Interactive preview and clean demo
    "demo": {
        "label": "Clean demo",
        "seo_title": "RunMyCampus Demo - Try the platform",
        "seo_description": "See RunMyCampus in action. Clean, focused demo of school operations—admissions, academics, and reporting.",
        "headline": "Try RunMyCampus.",
        "subheadline": "A clean, focused demo of school operations. No sign-up required to explore.",
        "schema_type": "WebPage",
        "segments": [
            {"title": "What you'll see", "body": "Dashboard, student list, grading, and report card preview with sample data. Read-only where applicable."},
            {"title": "Book a live demo", "body": "Get a guided walkthrough and Q&A. We'll show tenant login, manager command center, and migration flows."},
        ],
    },
    "interactive-preview": {
        "label": "Interactive preview",
        "seo_title": "RunMyCampus Interactive Preview - Explore the product",
        "seo_description": "Interactive product preview: explore the interface with sample data. No account required.",
        "headline": "Interactive preview.",
        "subheadline": "Explore the interface with sample data. Links to full demo and sign-up when you're ready.",
        "schema_type": "WebPage",
        "segments": [
            {"title": "Sample experience", "body": "Navigate a simulated school backend: dashboards, lists, and forms with safe sample data."},
            {"title": "Next step", "body": "Book a live demo or start a trial to get your own tenant and real data migration."},
        ],
    },
    "buyer-toolkit": {
        "label": "Buyer Toolkit",
        "seo_title": "RunMyCampus Buyer Toolkit - Evaluation checklist and implementation guide",
        "seo_description": "Download the school management buyer evaluation checklist and implementation timeline. Role-based ownership for school lead, IT, finance, and admissions.",
        "headline": "Buyer toolkit and implementation checklist.",
        "subheadline": "Evaluate RunMyCampus with a structured checklist and plan rollout with clear role ownership.",
        "schema_type": "WebPage",
        "segments": [
            {"title": "Buyer evaluation checklist", "body": "Criteria for tenancy, security, localization, and support. Use before you commit."},
            {"title": "Implementation checklist", "body": "Phased rollout with school lead, IT, finance, and admissions ownership. Download and track progress."},
        ],
    },
}

MARKETING_PAGE_EXTRAS = {
    "product": {
        "trust_strip": ["Unified data model", "Role-ready portals", "Global tenancy", "FERPA aligned", "GDPR ready"],
        "metrics": [
            {"value": "1", "label": "unified data model", "detail": "Admissions, academics, finance, and communication stay in one platform."},
            {"value": "4", "label": "core operator modules", "detail": "Enrollment, academics, operations, and support control surfaces."},
            {"value": "3", "label": "role portals", "detail": "Parent, teacher, and student experiences stay role-specific and auditable."},
            {"value": "24/7", "label": "operational continuity", "detail": "Manager-level workflows keep support and governance responsive."},
        ],
        "execution_blocks": [
            {
                "title": "Admissions to enrollment continuity",
                "body": "Lead capture, qualification, and onboarding transitions run without disconnected tooling.",
            },
            {
                "title": "Intervention action center",
                "body": "Risk signals route into assignment-ready intervention workflows for fast follow-through.",
            },
            {
                "title": "Governed integration model",
                "body": "Connect LMS, messaging, and payment providers with operational safeguards and traceability.",
            },
        ],
        "faqs": [
            {"question": "What is RunMyCampus AI Co-pilot?", "answer": "AI Co-pilot provides smart assistance for workflows, reporting, and decision support across admissions, academics, and operations."},
            {"question": "Does RunMyCampus offer real-time analytics?", "answer": "Yes. Live dashboards show enrollment and attendance trends, with actionable insights for school leaders."},
            {"question": "Can we customize workflows to our school?", "answer": "Yes. Customizable Workflows let you adapt processes, forms, and approval chains to your policies without custom code."},
            {"question": "How does the unified data model work?", "answer": "Students, staff, payments, reports, and interventions share one source of truth across the platform."},
        ],
    },
    "solutions": {
        "metrics": [
            {"value": "3", "label": "deployment archetypes", "detail": "Single-campus, multi-campus, and regional operator models."},
            {"value": "195+", "label": "country-ready design", "detail": "Localization logic aligns terminology and compliance defaults by region."},
            {"value": "1", "label": "manager command center", "detail": "Central oversight with school-level autonomy across tenants."},
            {"value": "100%", "label": "subdomain isolation", "detail": "Tenant boundaries remain explicit and secure for every school."},
        ],
        "execution_blocks": [
            {
                "title": "Single-campus launch packs",
                "body": "Pre-configured patterns reduce setup time for school leads and operations teams.",
            },
            {
                "title": "Multi-campus governance rails",
                "body": "Standardize shared policy while preserving school identity, workflows, and ownership.",
            },
            {
                "title": "Regional adaptation without forks",
                "body": "Global registry hydration keeps language and compliance variants out of core business logic.",
            },
        ],
        "faqs": [
            {"question": "What deployment options does RunMyCampus support?", "answer": "Single-campus, multi-campus networks, and regional operator models with templates for each."},
            {"question": "Is RunMyCampus available in our country?", "answer": "RunMyCampus is designed for 195+ country-ready profiles with localization for language, compliance, and terms."},
            {"question": "How does multi-campus governance work?", "answer": "Manager command center provides central oversight while preserving school-level autonomy and identity."},
            {"question": "Can each school keep its own domain?", "answer": "Yes. Subdomain isolation gives each tenant explicit, secure boundaries and dedicated branding."},
        ],
    },
    "pricing": {
        "metrics": [
            {"value": "3", "label": "clear plan bands", "detail": "Starter, Growth, and Enterprise White-label framing."},
            {"value": "0", "label": "migration guesswork", "detail": "Plan boundaries map to growth stages and governance requirements."},
            {"value": "1", "label": "billing oversight layer", "detail": "Manager workflows provide trial and usage visibility across tenants."},
            {"value": "Flexible", "label": "add-on model", "detail": "Activate advanced modules as schools scale operational complexity."},
        ],
        "faqs": [
            {"question": "What plans does RunMyCampus offer?", "answer": "Starter for single-campus schools, Growth for multi-campus networks, and Enterprise White-label for operators at national scale."},
            {"question": "Can I try RunMyCampus before committing?", "answer": "Yes. Start a free trial from the signup flow; you can also book a demo for a guided walkthrough."},
            {"question": "How does billing work for multiple schools?", "answer": "Manager workflows provide visibility into trial status, usage, and billing across all tenants in one command center."},
        ],
        "execution_blocks": [
            {
                "title": "Transparent growth path",
                "body": "Schools can start lean, then add modules for analytics, integrations, and operator workflows.",
            },
            {
                "title": "Enterprise white-label readiness",
                "body": "High-scale operators get dedicated governance, compliance posture, and branding control.",
            },
            {
                "title": "Cost aligned to operations",
                "body": "Plans are designed around actual usage and institutional operating models, not feature sprawl.",
            },
        ],
    },
    "compare": {
        "metrics": [
            {"value": "1", "label": "canonical host contract", "detail": "Public, tenant, manager, API, and docs surfaces are explicitly separated."},
            {"value": "100%", "label": "subdomain tenancy", "detail": "No path-based tenant rendering in production contract."},
            {"value": "3", "label": "governance layers", "detail": "School-level control, manager oversight, and registry-based defaults."},
            {"value": "Audit-ready", "label": "operator traceability", "detail": "Support and provisioning actions remain attributable and reviewable."},
        ],
        "execution_blocks": [
            {
                "title": "Architecture fit assessment",
                "body": "Map your current operating model to strict host, tenancy, and governance requirements.",
            },
            {
                "title": "Migration risk reduction",
                "body": "Stage rollout with redirect compatibility and operational smoke checks before cutover.",
            },
            {
                "title": "Support readiness validation",
                "body": "Confirm manager workflow coverage for provisioning, escalation, and impersonation audit trails.",
            },
        ],
        "comparison_rows": [
            {
                "criterion": "Tenant isolation",
                "runmycampus": "Strict subdomain tenancy, isolated auth and data context.",
                "legacy": "Path-based tenancy increases cross-tenant risk and routing complexity.",
            },
            {
                "criterion": "Operations governance",
                "runmycampus": "Dedicated manager host for support, approvals, and health visibility.",
                "legacy": "Mixed admin routes on public host dilute control boundaries.",
            },
            {
                "criterion": "Localization strategy",
                "runmycampus": "Registry-driven hydration for terminology and compliance defaults.",
                "legacy": "Country-specific forks and hardcoded strings create maintenance debt.",
            },
            {
                "criterion": "Growth path",
                "runmycampus": "Plan-based scale from single campus to white-label enterprise.",
                "legacy": "Feature sprawl without operational stage alignment.",
            },
        ],
        "migration_narrative": [
            "Assess your current stack against host, tenancy, and governance criteria above.",
            "Plan data migration and redirect strategy with dry-run and parity checks before cutover.",
            "Use RunMyCampus migration tools and templates to move students, staff, and historical data.",
            "Go live with phased rollout and dedicated support; validate with smoke tests and rollback readiness.",
        ],
    },
    "case-studies": {
        "metrics": [
            {"value": "42%", "label": "faster onboarding cycles", "detail": "Template-led school launch patterns shorten go-live timelines."},
            {"value": "31%", "label": "faster intervention response", "detail": "Action-center workflows improve follow-through speed for at-risk learners."},
            {"value": "2.3x", "label": "support visibility gain", "detail": "Manager control workflows reduce unresolved queue blind spots."},
            {"value": "99.9%", "label": "platform continuity target", "detail": "Operational posture designed for day-to-day reliability."},
        ],
        "execution_blocks": [
            {
                "title": "Onboarding playbook rollout",
                "body": "Standardized launch templates reduce setup drift between schools and operators.",
            },
            {
                "title": "Intervention protocol adoption",
                "body": "Risk dashboards and assignment workflows improve consistency of learner support actions.",
            },
            {
                "title": "Support command workflow",
                "body": "Escalation pathways and audit traces improve decision velocity for manager teams.",
            },
        ],
        "case_cards": [
            {
                "title": "Multi-campus governance modernization",
                "result": "Reduced onboarding time while preserving campus identity autonomy.",
                "impact": "Faster go-live and clearer ownership boundaries.",
                "outcomes": ["42% faster onboarding", "3 campuses live in 8 weeks", "Single sign-on across network"],
            },
            {
                "title": "Admissions-to-enrollment conversion lift",
                "result": "Unified enquiry, qualification, and onboarding workflow improved conversion flow.",
                "impact": "Lower handoff friction and better counselor throughput.",
                "outcomes": ["31% higher application-to-enrollment rate", "50% less manual data re-entry", "2-week shorter cycle"],
            },
            {
                "title": "Regional localization program",
                "result": "Registry-driven terminology and compliance defaults removed regional hardcoding.",
                "impact": "Faster country rollout with lower maintenance overhead.",
                "outcomes": ["4 countries on one codebase", "60% less localization effort", "Same-day terminology updates"],
            },
        ],
    },
    "book-demo": {
        "metrics": [
            {"value": "45 min", "label": "guided walkthrough", "detail": "Structured review of public, tenant, and manager experiences."},
            {"value": "3", "label": "live surface demonstrations", "detail": "Marketing conversion, tenant login, and manager operations in one session."},
            {"value": "1", "label": "architecture recommendation", "detail": "You receive a clear operating model fit summary."},
            {"value": "Next-day", "label": "follow-up package", "detail": "Implementation notes and rollout guidance after demo completion."},
        ],
        "execution_blocks": [
            {
                "title": "Discovery alignment",
                "body": "Capture your institution profile, constraints, and target operating outcomes before the walkthrough.",
            },
            {
                "title": "Live platform scenario",
                "body": "Run real workflows across public acquisition, tenant identity, and manager operations.",
            },
            {
                "title": "Actionable next-step plan",
                "body": "Receive a deployment sequence with conversion, governance, and onboarding priorities.",
            },
        ],
        "demo_agenda": [
            "Public authority flow: homepage, discovery, and conversion paths.",
            "Tenant experience: branded login, role portals, and workflow continuity.",
            "Manager control: provisioning, support desk, and audit traces.",
            "Implementation roadmap: phased rollout and success criteria.",
        ],
    },
    "buyer-toolkit": {
        "implementation_timeline": [
            {"phase": "1", "title": "Discovery and signup", "owner": "School lead", "items": ["Evaluate platform fit", "Start free trial", "Confirm data and compliance requirements"]},
            {"phase": "2", "title": "Tenant and data setup", "owner": "IT", "items": ["Provision tenant", "Import students and staff", "Configure SSO and integrations"]},
            {"phase": "3", "title": "Finance and billing", "owner": "Finance", "items": ["Configure fee structure", "Connect payment gateway", "Run first billing cycle"]},
            {"phase": "4", "title": "Academics and go-live", "owner": "Admissions / Academics", "items": ["Configure grading and terms", "Train teachers and staff", "Go live and monitor"]},
        ],
        "checklist_intro": "Use this checklist to evaluate RunMyCampus before you commit. Download and track progress.",
    },
    "security-compliance": {
        "trust_strip": ["FERPA aligned", "GDPR ready", "SOC 2 roadmap", "Encryption at rest & in transit", "Audit trails"],
    },
    "integrations": {
        "integration_trust_categories": [
            {"name": "SIS & student data", "summary": "OneRoster, Ed-Fi, and custom SIS sync. Student records stay in sync with your source of truth.", "icon": "SIS"},
            {"name": "LMS & LTI", "summary": "LTI 1.3 and deep linking. Connect Canvas, Moodle, Google Classroom, and other LMS providers.", "icon": "LMS"},
            {"name": "Payments", "summary": "Stripe, PayPal, and regional gateways. Multi-currency and receipt automation.", "icon": "Pay"},
            {"name": "Messaging", "summary": "SMS and email providers for notifications, reminders, and alerts. Delivery tracking.", "icon": "Msg"},
            {"name": "Identity", "summary": "SAML and OAuth. Single sign-on with your identity provider.", "icon": "SSO"},
        ],
    },
    "why-switch": {
        "faqs": [
            {"question": "Why switch from spreadsheets to RunMyCampus?", "answer": "One platform for admissions, academics, finance, and compliance with guided import and no ongoing spreadsheet sync."},
            {"question": "How long does migration take?", "answer": "Timelines depend on data volume and complexity; templates and support typically get schools live in weeks."},
            {"question": "Can we keep our existing data?", "answer": "Yes. Structured import paths let you bring students, staff, and historical data into a single source of truth."},
            {"question": "What if we need to leave the platform?", "answer": "Export and portability options keep you in control of your school data with no lock-in."},
        ],
    },
    "10-reasons": {},
    "resources": {},
    "events": {},
    "trust-center": {
        "architecture_summary": "RunMyCampus uses a strict host contract: public (runmycampus.com), tenant (school subdomains), and manager (manager.runmycampus.com) surfaces are separated. Each tenant is isolated by subdomain with dedicated session and data context.",
        "encryption_copy": "Data is encrypted at rest and in transit. Credentials and secrets are managed with secure storage and access controls. API and integration traffic uses TLS.",
        "sla_uptime": {
            "uptime_target": "99.9%",
            "sla_summary": "RunMyCampus targets 99.9% platform availability. Planned maintenance is communicated in advance.",
            "status_url": None,  # Set via MARKETING_STATUS_PAGE_URL in settings if you have a public status page
            "support_summary": "24/7 operator readiness for critical issues. Support and governance from manager workflows.",
        },
        "integration_trust_categories": [
            {"name": "SIS & student data", "summary": "OneRoster, Ed-Fi, and custom SIS sync. Student records stay in sync with your source of truth.", "icon": "SIS"},
            {"name": "LMS & LTI", "summary": "LTI 1.3 and deep linking. Connect Canvas, Moodle, Google Classroom, and other LMS providers.", "icon": "LMS"},
            {"name": "Payments", "summary": "Stripe, PayPal, and regional gateways. Multi-currency and receipt automation.", "icon": "Pay"},
            {"name": "Messaging", "summary": "SMS and email providers for notifications, reminders, and alerts. Delivery tracking.", "icon": "Msg"},
            {"name": "Identity", "summary": "SAML and OAuth. Single sign-on with your identity provider.", "icon": "SSO"},
        ],
    },
}

TOPICAL_LANDING_DEFINITIONS = {
    "admissions-software": {
        "label": "Admissions Software",
        "seo_title": "Admissions Software for Schools | RunMyCampus",
        "seo_description": "End-to-end admissions software: enquiry capture, applicant tracking, interviews, and enrollment in one platform.",
        "headline": "Admissions software that converts.",
        "subheadline": "From first enquiry to enrolled student—one flow for applications, qualification, and onboarding.",
        "focus_points": [
            "Campaign-aware enquiry forms and lead routing by school.",
            "Applicant tracking with counselor assignments and document checklist.",
            "Accept-to-enrollment handoff without spreadsheets or duplicate entry.",
        ],
        "role_pain": "Admissions teams juggle spreadsheets, email, and legacy tools—leading to lost leads and slow conversion.",
        "migration_angle": "Import existing enquiries and applicants; map counselor workflows; go live with one source of truth.",
        "proof_points": ["Faster application-to-enrollment conversion", "Single enquiry pipeline", "Counselor assignment visibility"],
        "related_slugs": ["school-erp", "k12-school-management-system", "multi-campus-school-software"],
    },
    "school-erp": {
        "label": "School ERP",
        "seo_title": "School ERP | RunMyCampus - Unified operations platform",
        "seo_description": "School ERP for academics, finance, HR, and operations. One platform for grades, fees, attendance, and reporting.",
        "headline": "School ERP without the sprawl.",
        "subheadline": "Academics, finance, attendance, and reporting in one tenant-first platform—no legacy silos.",
        "focus_points": [
            "Unified data model: students, staff, fees, and grades in one source of truth.",
            "Role-ready portals for admin, teachers, parents, and students.",
            "Audit trails, compliance defaults, and export-ready reports.",
        ],
        "role_pain": "Finance, academics, and operations run on separate systems—leading to duplicate data and reporting gaps.",
        "migration_angle": "Map your current modules to RunMyCampus; import students, staff, and fees; phase out legacy ERP.",
        "proof_points": ["One source of truth", "Role-ready portals", "Audit-ready reporting"],
        "related_slugs": ["admissions-software", "k12-school-management-system", "parent-app"],
    },
    "parent-app": {
        "label": "Parent App",
        "seo_title": "Parent App for Schools | RunMyCampus",
        "seo_description": "Parent portal for attendance, grades, fees, and communication. One app for school-family engagement.",
        "headline": "The parent app schools and families trust.",
        "subheadline": "Attendance, grades, fees, and messages in one place—so parents stay informed without chasing updates.",
        "focus_points": [
            "Real-time visibility into attendance, grades, and assignments.",
            "Fee statements and payment history in the parent portal.",
            "School messaging and announcements with delivery tracking.",
        ],
        "role_pain": "Parents chase teachers and office staff for grades and updates; schools lack a single channel for family communication.",
        "migration_angle": "Turn on the parent portal; no separate app to install—parents use one link for all school communication.",
        "proof_points": ["One place for attendance, grades, fees", "School-controlled messaging", "No app sprawl"],
        "related_slugs": ["school-erp", "k12-school-management-system"],
    },
    "k12-school-management-system": {
        "label": "K12 School Management",
        "seo_title": "K12 School Management System | RunMyCampus",
        "seo_description": "K12-ready workflows for enrollment, attendance, grades, communication, and parent engagement.",
        "headline": "K12 operations in one platform.",
        "subheadline": "Coordinate academics, attendance, communication, and family engagement without tool sprawl.",
        "focus_points": [
            "Term and grading workflows aligned to school calendars.",
            "Parent and teacher portals with role-specific access.",
            "At-risk student insights for earlier intervention.",
        ],
        "role_pain": "K12 admins and teachers need one system that handles enrollment, grades, attendance, and parent communication.",
        "migration_angle": "Import students and terms from your SIS or spreadsheets; configure grading and calendars; go live with teacher and parent access.",
        "proof_points": ["Term and calendar alignment", "Teacher and parent portals", "At-risk insights"],
        "related_slugs": ["admissions-software", "school-erp", "parent-app"],
    },
    "multi-campus-school-software": {
        "label": "Multi-Campus Operations",
        "seo_title": "Multi-Campus School Software | RunMyCampus",
        "seo_description": "Run multiple schools with centralized oversight and campus-level autonomy from a single platform.",
        "headline": "Multi-campus control without bottlenecks.",
        "subheadline": "Standardize governance while preserving each campus identity, workflows, and accountability.",
        "focus_points": [
            "Global super-admin command center for all tenants.",
            "Per-campus domain, branding, and policy isolation.",
            "Shared reporting for approvals, billing, and support.",
        ],
        "role_pain": "Multi-campus operators need central visibility without forcing one-size-fits-all on each school.",
        "migration_angle": "Provision campuses as tenants; migrate one or many at a time; keep central reporting and support workflows.",
        "proof_points": ["Per-campus autonomy", "Central command center", "Shared reporting"],
        "related_slugs": ["school-erp", "admissions-software", "student-passport-transcript-portability"],
    },
    "student-passport-transcript-portability": {
        "label": "Student Passport Portability",
        "seo_title": "Student Passport & Transcript Portability | RunMyCampus",
        "seo_description": "Portable student passport and transcript workflows for smooth transitions across schools.",
        "headline": "Portable student records across school transitions.",
        "subheadline": "Enable secure transcript and passport continuity when learners move between institutions.",
        "focus_points": [
            "Global student passport identifiers for continuity.",
            "Transfer invite workflow between source and destination schools.",
            "Document-ready evidence trail for transcript portability.",
        ],
        "role_pain": "When students move between schools, records are lost or re-entered manually—slowing enrollment and hurting continuity.",
        "migration_angle": "Adopt the student passport model; enable transfer workflows so sending and receiving schools share a single record.",
        "proof_points": ["Portable identifier", "Transfer workflow", "Document-ready transcripts"],
        "related_slugs": ["k12-school-management-system", "multi-campus-school-software", "school-erp"],
    },
}

INSTITUTION_LANDING_DEFINITIONS = {
    "k12": {
        "label": "K-12",
        "seo_title": "K-12 School Management | RunMyCampus",
        "seo_description": "RunMyCampus for K-12: enrollment, grades, attendance, and parent engagement in one platform.",
        "headline": "K-12 operations in one platform.",
        "subheadline": "Elementary and secondary schools get enrollment, academics, communication, and compliance without tool sprawl.",
        "workflow_examples": [
            {"title": "Enrollment and attendance", "body": "Daily attendance, term calendars, and parent visibility in one flow."},
            {"title": "Grades and report cards", "body": "Grading workflows and report cards aligned to your school calendar."},
            {"title": "Parent and teacher portals", "body": "Role-ready access so families and staff see what they need."},
        ],
        "compliance_angle": "FERPA-aligned workflows and regional compliance defaults for K-12.",
        "migration_pathway": "Import students and staff from your SIS or spreadsheets; configure terms and grading; go live with teacher and parent access.",
        "cta_primary": "Start free trial",
        "cta_secondary": "Book demo",
    },
    "universities": {
        "label": "Universities",
        "seo_title": "University Management Platform | RunMyCampus",
        "seo_description": "RunMyCampus for higher ed: admissions, academic structure, and multi-campus governance.",
        "headline": "Higher ed operations that scale.",
        "subheadline": "Admissions, academic structure, and multi-campus governance for universities and colleges.",
        "workflow_examples": [
            {"title": "Admissions and enrollment", "body": "From application to enrolled student with counselor workflows and document tracking."},
            {"title": "Academic structure", "body": "Programs, courses, and sections with role-based access for faculty and staff."},
            {"title": "Multi-campus governance", "body": "Central oversight with campus-level autonomy and reporting."},
        ],
        "compliance_angle": "GDPR and FERPA-aligned controls with audit trails and data residency options.",
        "migration_pathway": "Map your current SIS and CRM; migrate students and courses; phase in by campus or module.",
        "cta_primary": "Start free trial",
        "cta_secondary": "Book demo",
    },
    "technical-schools": {
        "label": "Technical schools",
        "seo_title": "Technical School Management | RunMyCampus",
        "seo_description": "RunMyCampus for career and technical education: programs, certification, and placement tracking.",
        "headline": "Career and technical education, unified.",
        "subheadline": "Programs, certification tracking, and placement workflows in one platform.",
        "workflow_examples": [
            {"title": "Program and certification tracking", "body": "Track credentials and certifications with audit-ready records."},
            {"title": "Placement and outcomes", "body": "Placement and employment outcomes for reporting and accreditation."},
            {"title": "Finance and billing", "body": "Tuition, aid, and billing aligned to technical program cycles."},
        ],
        "compliance_angle": "Regional accreditation and compliance reporting with role-based access.",
        "migration_pathway": "Import programs and students; configure certification workflows; connect to placement and reporting.",
        "cta_primary": "Start free trial",
        "cta_secondary": "Book demo",
    },
    "private-schools": {
        "label": "Private schools",
        "seo_title": "Private School Management | RunMyCampus",
        "seo_description": "RunMyCampus for independent and faith-based schools: full operations and fundraising.",
        "headline": "Private schools run with one platform.",
        "subheadline": "Independent and faith-based schools get admissions, academics, finance, and fundraising without sprawl.",
        "workflow_examples": [
            {"title": "Admissions and enrollment", "body": "Enquiry to enrollment with family communication and financial aid workflows."},
            {"title": "Academics and reporting", "body": "Grades, attendance, and report cards with parent and teacher portals."},
            {"title": "Development and fundraising", "body": "Donor and event management for advancement and engagement."},
        ],
        "compliance_angle": "Audit trails and policy controls for independent school governance.",
        "migration_pathway": "Import students and families; configure fees and aid; add development and events as needed.",
        "cta_primary": "Start free trial",
        "cta_secondary": "Book demo",
    },
    "government-education": {
        "label": "Government education",
        "seo_title": "Government Education Platform | RunMyCampus",
        "seo_description": "RunMyCampus for public sector and government-run institutions: compliance and reporting.",
        "headline": "Government education, compliant by design.",
        "subheadline": "Public sector and government-run institutions with compliance, reporting, and multi-entity governance.",
        "workflow_examples": [
            {"title": "Compliance and reporting", "body": "Audit-ready workflows and regional compliance defaults."},
            {"title": "Multi-entity governance", "body": "Central oversight with entity-level isolation and reporting."},
            {"title": "Access and security", "body": "Role-based access and encryption at rest and in transit."},
        ],
        "compliance_angle": "FERPA, GDPR, and government security requirements with data residency options.",
        "migration_pathway": "Map compliance and reporting requirements; migrate entities with phased rollout and audit trails.",
        "cta_primary": "Start free trial",
        "cta_secondary": "Book demo",
    },
}

ROLE_PAGE_DEFINITIONS = {
    "school-admin": {
        "label": "School admins",
        "seo_title": "School Admin Software | RunMyCampus",
        "seo_description": "RunMyCampus for school administrators: one console for enrollment, academics, finance, and reporting.",
        "headline": "One console for school operations.",
        "subheadline": "Enrollment, academics, finance, and reporting without switching tools or re-entering data.",
        "workflows": ["Enrollment and admissions", "Attendance and grades", "Fee and billing", "Reporting and compliance"],
        "dashboards": ["Student and staff overview", "Finance summary", "Compliance and audit"],
        "outcomes": ["Single source of truth", "Faster reporting", "Audit-ready operations"],
    },
    "teachers": {
        "label": "Teachers",
        "seo_title": "Teacher Portal & Tools | RunMyCampus",
        "seo_description": "RunMyCampus for teachers: grading, attendance, and parent communication in one place.",
        "headline": "Teacher tools that save time.",
        "subheadline": "Grading, attendance, and parent communication without leaving one platform.",
        "workflows": ["Attendance", "Grading and report cards", "Class and assignment visibility", "Parent messaging"],
        "dashboards": ["My classes", "Attendance summary", "Grade book"],
        "outcomes": ["Less duplicate entry", "Clear parent communication", "One place for grades"],
    },
    "parents": {
        "label": "Parents",
        "seo_title": "Parent Portal | RunMyCampus",
        "seo_description": "RunMyCampus parent portal: attendance, grades, fees, and messages in one place.",
        "headline": "One place for your child's school.",
        "subheadline": "Attendance, grades, fees, and messages so you stay informed without chasing updates.",
        "workflows": ["View attendance and grades", "Pay fees", "School messages and announcements"],
        "dashboards": ["My children", "Fee statements", "Message history"],
        "outcomes": ["Real-time visibility", "One login", "No app sprawl"],
    },
    "students": {
        "label": "Students",
        "seo_title": "Student Portal | RunMyCampus",
        "seo_description": "RunMyCampus student portal: assignments, grades, and school resources in one place.",
        "headline": "Your school, one place.",
        "subheadline": "Assignments, grades, and school resources so you stay on track.",
        "workflows": ["View assignments", "Check grades", "Access resources"],
        "dashboards": ["My classes", "Grades", "Upcoming"],
        "outcomes": ["Clear visibility", "One login", "Mobile-friendly"],
    },
    "it-directors": {
        "label": "IT directors",
        "seo_title": "IT & School Management Platform | RunMyCampus",
        "seo_description": "RunMyCampus for IT: tenant provisioning, SSO, integrations, and security.",
        "headline": "IT control without lock-in.",
        "subheadline": "Tenant provisioning, SSO, integrations, and security from one platform.",
        "workflows": ["Tenant and user provisioning", "SSO and identity", "Integrations and API"],
        "dashboards": ["Tenant health", "Integration status", "Audit and access"],
        "outcomes": ["Subdomain isolation", "API and webhooks", "Audit-ready"],
    },
    "government": {
        "label": "Government",
        "seo_title": "Government Education Operations | RunMyCampus",
        "seo_description": "RunMyCampus for government education: compliance, reporting, and multi-entity governance.",
        "headline": "Government education operations.",
        "subheadline": "Compliance, reporting, and multi-entity governance with audit trails and data residency.",
        "workflows": ["Compliance and reporting", "Multi-entity oversight", "Audit and access control"],
        "dashboards": ["Entity overview", "Compliance status", "Reporting"],
        "outcomes": ["Audit-ready", "Data residency options", "Role-based governance"],
    },
}

MIGRATE_PAGE_DEFINITIONS = {
    "": {
        "seo_title": "Migrate to RunMyCampus | School Data Migration",
        "seo_description": "Migrate from spreadsheets or legacy SIS with guided setup, field mapping, and support.",
        "headline": "Migrate with confidence.",
        "subheadline": "Move from spreadsheets or legacy systems with guided setup, field mapping, and rollback safety.",
        "migration_cloud_copy": "RunMyCampus runs on a secure, scalable cloud. Your data is migrated with validation and optional dry-run.",
        "field_mapping_copy": "Map your existing student, staff, and course data to RunMyCampus with templates and validation.",
        "validation_copy": "Validate data before and after migration with checks and reports.",
        "rollback_copy": "Plan for rollback with staged cutover and support so you can revert if needed.",
        "cta": "Book a migration call",
    },
    "from-power-school": {
        "seo_title": "Migrate from PowerSchool to RunMyCampus",
        "seo_description": "Step-by-step migration from PowerSchool to RunMyCampus: data mapping, validation, and go-live.",
        "headline": "Migrate from PowerSchool to RunMyCampus.",
        "subheadline": "Student, staff, and course data with guided mapping and validation.",
        "migration_cloud_copy": "Export from PowerSchool and import into RunMyCampus with field mapping and validation.",
        "field_mapping_copy": "Map PowerSchool fields to RunMyCampus; we provide templates for students, staff, and courses.",
        "validation_copy": "Validate enrollment and grade data before cutover; run parity reports.",
        "rollback_copy": "Staged cutover with rollback plan; keep PowerSchool read-only during transition.",
        "cta": "Book a PowerSchool migration call",
    },
    "from-blackbaud": {
        "seo_title": "Migrate from Blackbaud to RunMyCampus",
        "seo_description": "Migrate from Blackbaud to RunMyCampus: admissions, finance, and student data.",
        "headline": "Migrate from Blackbaud to RunMyCampus.",
        "subheadline": "Admissions, finance, and student data with guided mapping and support.",
        "migration_cloud_copy": "Move from Blackbaud to RunMyCampus with export and import workflows.",
        "field_mapping_copy": "Map Blackbaud data to RunMyCampus; templates for students, families, and fees.",
        "validation_copy": "Validate data before go-live; parity checks for key records.",
        "rollback_copy": "Phased rollout with rollback option; support during cutover.",
        "cta": "Book a Blackbaud migration call",
    },
    "from-infinite-campus": {
        "seo_title": "Migrate from Infinite Campus to RunMyCampus",
        "seo_description": "Migrate from Infinite Campus to RunMyCampus: student, course, and grade data.",
        "headline": "Migrate from Infinite Campus to RunMyCampus.",
        "subheadline": "Student, course, and grade data with mapping and validation.",
        "migration_cloud_copy": "Export from Infinite Campus and import into RunMyCampus with field mapping.",
        "field_mapping_copy": "Map Infinite Campus fields to RunMyCampus students, courses, and grades.",
        "validation_copy": "Validate enrollment and grades before cutover.",
        "rollback_copy": "Staged cutover with rollback plan.",
        "cta": "Book an Infinite Campus migration call",
    },
}

COMPARE_PAGE_DEFINITIONS = {
    "power-school": {
        "competitor_name": "PowerSchool",
        "seo_title": "RunMyCampus vs PowerSchool | Compare",
        "seo_description": "Compare RunMyCampus and PowerSchool: tenancy, security, and workflow depth.",
        "headline": "RunMyCampus vs PowerSchool.",
        "subheadline": "Compare tenancy, security, workflow depth, and long-term fit.",
        "criteria": [
            {"name": "Tenant isolation", "runmycampus": "Strict subdomain tenancy; each school isolated.", "competitor": "Path or district-based; shared infrastructure."},
            {"name": "Workflow depth", "runmycampus": "Admissions, academics, finance, compliance in one platform.", "competitor": "Strong SIS; other modules vary."},
            {"name": "Multi-campus", "runmycampus": "Native multi-tenant with manager command center.", "competitor": "District-centric; different product for multi-entity."},
        ],
    },
    "blackbaud": {
        "competitor_name": "Blackbaud",
        "seo_title": "RunMyCampus vs Blackbaud | Compare",
        "seo_description": "Compare RunMyCampus and Blackbaud: operations, fundraising, and platform approach.",
        "headline": "RunMyCampus vs Blackbaud.",
        "subheadline": "Compare operations, fundraising, and platform approach.",
        "criteria": [
            {"name": "Tenant isolation", "runmycampus": "Subdomain tenancy; each school isolated.", "competitor": "Multi-product; shared backend."},
            {"name": "Unified operations", "runmycampus": "One platform for admissions, academics, finance.", "competitor": "Separate products for SIS, RMM, etc."},
            {"name": "Pricing and scale", "runmycampus": "Transparent plans; scale from single campus to white-label.", "competitor": "Enterprise-focused; complex pricing."},
        ],
    },
    "infinite-campus": {
        "competitor_name": "Infinite Campus",
        "seo_title": "RunMyCampus vs Infinite Campus | Compare",
        "seo_description": "Compare RunMyCampus and Infinite Campus: K-12 SIS and operations.",
        "headline": "RunMyCampus vs Infinite Campus.",
        "subheadline": "Compare K-12 SIS, tenancy, and operations.",
        "criteria": [
            {"name": "Tenant isolation", "runmycampus": "Subdomain tenancy; each school isolated.", "competitor": "District-based; shared instance."},
            {"name": "Platform scope", "runmycampus": "Admissions, academics, finance, compliance in one.", "competitor": "Strong K-12 SIS; other modules vary."},
            {"name": "Integration", "runmycampus": "API, webhooks, LTI; marketplace.", "competitor": "Ecosystem and integrations vary."},
        ],
    },
}


def _safe_reverse(name: str, *, kwargs: dict | None = None) -> str:
    try:
        return reverse(name, kwargs=kwargs)
    except NoReverseMatch:
        return "#"
    except Exception:
        return "#"


def _marketing_nav() -> list[dict]:
    return [
        {"slug": slug, "label": page["label"], "path": f"/{slug}/"}
        for slug, page in MARKETING_PAGE_DEFINITIONS.items()
    ]


def _marketing_navbar_primary() -> list[dict]:
    """Primary marketing navbar: Product | Solutions | Pricing | Compare | Why Switch | Customers | Marketplace | Resources | Events | Company | [Login] [Start Free Trial]."""
    return [
        {"label": "Product", "path": _safe_reverse("marketing_product") or "/product/"},
        {"label": "Solutions", "path": _safe_reverse("marketing_solutions") or "/solutions/"},
        {"label": "Pricing", "path": _safe_reverse("marketing_pricing") or "/pricing/"},
        {"label": "Compare", "path": _safe_reverse("marketing_compare") or "/compare/"},
        {"label": "Why Switch", "path": _safe_reverse("marketing_why_switch") or "/why-switch/"},
        {"label": "Customers", "path": _safe_reverse("marketing_case_studies") or "/case-studies/"},
        {"label": "Marketplace", "path": _safe_reverse("marketing_app_marketplace") or "/app-marketplace/"},
        {"label": "Resources", "path": _safe_reverse("marketing_resources") or "/resources/"},
        {"label": "Events", "path": _safe_reverse("marketing_events") or "/events/"},
        {"label": "10 Reasons", "path": _safe_reverse("marketing_10_reasons") or "/10-reasons/"},
        {"label": "Company", "path": _safe_reverse("marketing_about") or "/about/"},
    ]


def _topical_nav() -> list[dict]:
    return [
        {"slug": slug, "label": topic["label"], "path": f"/solutions/{slug}/"}
        for slug, topic in TOPICAL_LANDING_DEFINITIONS.items()
    ]


def _get_country_from_request(request) -> str:
    """Country code (alpha-2) from GeoIP for marketing personalization."""
    try:
        from apps.compliance.access_control import get_country_from_ip

        ip = (
            request.META.get("HTTP_X_FORWARDED_FOR", "").split(",")[0].strip()
            or request.META.get("REMOTE_ADDR", "")
        )
        if not ip:
            return ""
        code = (get_country_from_ip(ip) or "").strip().upper()[:2]
        return code
    except Exception:
        return ""


def _normalize_country_code(value: str) -> str:
    alpha3 = GlobalGeoCatalog.normalize_country_code(value)
    alpha2 = GlobalGeoCatalog.alpha2_for_country(alpha3)
    if alpha2:
        return alpha2.upper()
    raw = (value or "").strip().upper()[:2]
    return raw


def _normalize_language_code(value: str, fallback: str = "en") -> str:
    raw = (value or "").strip().lower()
    if not raw:
        return fallback
    # Keep language only; regional variants are folded for route stability.
    return raw.split("-", 1)[0]


def _absolute_url(request, path: str) -> str:
    scheme = "https" if request.is_secure() else "http"
    host = (request.get_host() or "").split(":")[0]
    if not path.startswith("/"):
        path = f"/{path}"
    return f"{scheme}://{host}{path}"


def _global_hreflang_entries(request, *, country_code: str, language_code: str) -> list[dict]:
    language = _normalize_language_code(language_code or "en")
    country = _normalize_country_code(country_code)
    if not country:
        return []
    entries = []
    supported = ["en", "fr", "pt", "ar"]
    for item in supported:
        path = f"/{item}/{country.lower()}/"
        entries.append({"hreflang": f"{item}-{country}", "href": _absolute_url(request, path)})
    entries.append({"hreflang": "x-default", "href": _absolute_url(request, "/")})
    return entries


def _host_url(request, host: str, path: str = "/") -> str:
    if not host:
        return "#"
    scheme = "https" if request.is_secure() else "http"
    normalized_path = path if path.startswith("/") else f"/{path}"
    return f"{scheme}://{host}{normalized_path}"


def _get_regional_pitch(country_code: str, language_code: str) -> dict:
    """
    Merge RegionalPitch overrides over GlobalBrandRegistry defaults.
    """
    brand = resolve_global_brand_context(country_code=country_code, language_code=language_code)
    seo = brand.get("seo_config") or {}
    default = {
        "headline": seo.get("headline") or "RunMyCampus",
        "subheadline": seo.get("subheadline") or "Global school operations, localized for every campus.",
        "features": seo.get("features") or [],
        "visual_variant": seo.get("visual_variant") or "",
        "seo_title": seo.get("seo_title") or "RunMyCampus - Global School Operations",
        "seo_description": seo.get("seo_description") or "Tenant-first school platform for academics, finance, and operations.",
    }

    country = _normalize_country_code(country_code)
    if not country:
        return default

    try:
        from apps.siteconfig.models import RegionalPitch

        pitch = RegionalPitch.objects.filter(country_code=country, is_active=True).first()
    except Exception:
        pitch = None
    if not pitch:
        return default

    return {
        "headline": pitch.headline or default["headline"],
        "subheadline": pitch.subheadline or default["subheadline"],
        "features": pitch.features or default["features"],
        "visual_variant": pitch.visual_variant or default["visual_variant"],
        "seo_title": pitch.seo_title or default["seo_title"],
        "seo_description": pitch.seo_description or default["seo_description"],
    }


def _geo_copy_variations(country: str) -> dict:
    """Evidence-driven copy variations by geo cluster (Wave 4). Use in templates for CTA/headline by region."""
    variants = {
        "CM": {"cta_primary": "Démarrer l'essai gratuit", "proof_lead": "Adapté aux écoles francophones et au contexte local."},
        "CA": {"cta_primary": "Start free trial", "proof_lead": "Built for Canadian schools and multi-province deployments."},
        "NG": {"cta_primary": "Start free trial", "proof_lead": "Designed for Nigerian schools and WAEC alignment."},
        "GB": {"cta_primary": "Start free trial", "proof_lead": "UK term structures and British curriculum support."},
    }
    return variants.get(country, {"cta_primary": "Start free trial", "proof_lead": "One platform for admissions, academics, and operations."})


def _tenant_example_slug_for_marketing() -> str | None:
    """
    Return a tenant slug suitable for marketing (e.g. regional landing).
    Prefer a non-excluded slug so links do not send users to school-not-found.
    """
    import os
    from django.conf import settings
    from apps.schools.models import School

    slug = getattr(settings, "TENANT_EXAMPLE_SLUG", None) or None
    if slug:
        return str(slug).strip().lower() or None
    excluded = {
        item.strip().lower()
        for item in (os.getenv("MARKETING_EXCLUDED_TENANT_SLUGS") or "").split(",")
        if item.strip()
    }
    school = (
        School.objects.filter(is_active=True)
        .order_by("created_at")
    )
    if excluded:
        school = school.exclude(slug__in=excluded).exclude(subdomain__in=excluded)
    return school.values_list("slug", flat=True).first()

def _marketing_context(request, *, country_code: str, language_code: str, regional: bool) -> dict:
    country = _normalize_country_code(country_code)
    brand = resolve_global_brand_context(country_code=country, language_code=language_code)
    language = _normalize_language_code(language_code, fallback=brand.get("primary_language") or "en")
    pitch = _get_regional_pitch(country, language)
    if regional and not country:
        raise Http404("Region not found")

    canonical_path = "/" if not regional else f"/{language}/{country.lower()}/"
    canonical_url = _absolute_url(request, canonical_path)
    hreflang_entries = _global_hreflang_entries(request, country_code=country, language_code=language)
    canonical_domain = get_canonical_base_domain()
    country_label = brand.get("country_name") or "Global"
    tenant_example_slug = _tenant_example_slug_for_marketing()
    tenant_login_path = "/authentication/login/"
    public_host = canonical_domain
    manager_host = f"manager.{canonical_domain}"
    api_host = f"api.{canonical_domain}"
    docs_host = f"docs.{canonical_domain}"
    tenant_host = f"{tenant_example_slug}.{canonical_domain}" if tenant_example_slug else f"your-school.{canonical_domain}"

    # School Identity card: link to tenant login only if we have a real example; else link to find school
    school_identity_primary_url = (
        _host_url(request, tenant_host, tenant_login_path)
        if tenant_example_slug
        else request.build_absolute_uri(_safe_reverse("find_school"))
    )
    school_identity_primary_label = "Tenant login" if tenant_example_slug else "Find your school"

    surface_cards = [
        {
            "name": "Global Authority",
            "host": public_host,
            "headline": "Public growth engine",
            "summary": "SEO-ready landing pages, localized proof blocks, and guided conversion flows for school operators.",
            "primary_cta_label": "Explore platform",
            "primary_cta_path": "/product/",
            "secondary_cta_label": "Find your school",
            "secondary_cta_path": _safe_reverse("global_login_discovery"),
        },
        {
            "name": "School Identity",
            "host": tenant_host,
            "headline": "White-label tenant access",
            "summary": "Tenant entry is branded with school identity while preserving strict subdomain isolation for security.",
            "primary_cta_label": school_identity_primary_label,
            "primary_cta_url": school_identity_primary_url,
            "secondary_cta_label": "School finder",
            "secondary_cta_path": _safe_reverse("find_school"),
        },
        {
            "name": "Manager Operations",
            "host": manager_host,
            "headline": "Command center for operators",
            "summary": "Global support, provisioning, and governance workflows run from a dedicated manager host.",
            "primary_cta_label": "Manager login",
            "primary_cta_url": _host_url(request, manager_host, tenant_login_path),
            "secondary_cta_label": "Architecture compare",
            "secondary_cta_path": "/compare/",
        },
    ]

    authority_metrics = [
        {
            "label": "Country Profile",
            "value": country_label,
            "detail": "Resolved from global brand registry.",
        },
        {
            "label": "Canonical Domain",
            "value": canonical_domain,
            "detail": "Public, tenant, and manager host contract.",
        },
        {
            "label": "API Surface",
            "value": api_host,
            "detail": "Integration-first architecture and governance.",
        },
        {
            "label": "Docs Surface",
            "value": docs_host,
            "detail": "Canonical implementation and onboarding guides.",
        },
    ]

    proof_points = [
        {
            "title": "Security-first tenancy",
            "body": "Every school is isolated on subdomain boundaries to protect sessions, policies, and data context.",
        },
        {
            "title": "Registry-driven localization",
            "body": f"Terminology, formatting, and compliance defaults adapt for {country_label} without branching code per tenant.",
        },
        {
            "title": "Operator observability",
            "body": "Support and manager workflows stay auditable across discovery, onboarding, and tenant operations.",
        },
    ]

    trust_badges = [
        "Regional compliance defaults",
        "Subdomain tenant isolation",
        "Cross-subdomain auth support",
        "Localized terminology and labels",
        "Manager command workflows",
        "API and documentation host split",
    ]

    rollout_steps = [
        {
            "step": "1",
            "title": "Acquire and convert",
            "body": "Drive acquisition from marketing pages with country/language messaging and clear conversion CTAs.",
        },
        {
            "step": "2",
            "title": "Locate the right school",
            "body": "Use school finder and discovery routes to route users to the exact tenant subdomain.",
        },
        {
            "step": "3",
            "title": "Operate at scale",
            "body": "Support and manager teams run governance, provisioning, and audit workflows from dedicated hosts.",
        },
    ]
    audience_segments = [
        {
            "name": "Single-campus schools",
            "summary": "Launch admissions, academics, billing, and parent communication from one operating console.",
            "cta_label": "See onboarding flow",
            "cta_path": _safe_reverse("signup_school"),
        },
        {
            "name": "School groups and chains",
            "summary": "Run multi-campus standards with local campus autonomy, branding, and policy controls.",
            "cta_label": "Compare architecture",
            "cta_path": "/compare/",
        },
        {
            "name": "Regional operators",
            "summary": "Scale language, terminology, and compliance defaults across country-specific deployments.",
            "cta_label": "Explore localized pages",
            "cta_path": "/solutions/",
        },
    ]

    proof_stats = [
        {"value": "3", "label": "dedicated surfaces", "detail": "Public, tenant, and manager host separation."},
        {"value": "195+", "label": "country-ready profiles", "detail": "Registry-driven localization and defaults."},
        {"value": "24/7", "label": "operator readiness", "detail": "Support and governance from manager workflows."},
        {"value": "100%", "label": "subdomain tenancy", "detail": "Strict isolation for tenant security boundaries."},
    ]
    # Wave 2: localized proof cards for country-language landing variants
    _proof_by_country = {
        "CM": [
            {"value": "3", "label": "surfaces dédiées", "detail": "Séparation public, tenant et manager."},
            {"value": "195+", "label": "pays pris en charge", "detail": "Localisation et conformité par région."},
            {"value": "24/7", "label": "disponibilité opérationnelle", "detail": "Support et gouvernance depuis le manager."},
            {"value": "100%", "label": "tenance par sous-domaine", "detail": "Isolation stricte par école."},
        ],
        "CA": [
            {"value": "3", "label": "dedicated surfaces", "detail": "Public, tenant, and manager host separation."},
            {"value": "195+", "label": "country-ready profiles", "detail": "Registry-driven localization and defaults."},
            {"value": "24/7", "label": "operator readiness", "detail": "Support and governance from manager workflows."},
            {"value": "100%", "label": "subdomain tenancy", "detail": "Strict isolation for tenant security boundaries."},
        ],
        "NG": [
            {"value": "3", "label": "dedicated surfaces", "detail": "Public, tenant, and manager host separation."},
            {"value": "195+", "label": "country-ready profiles", "detail": "Registry-driven localization and defaults."},
            {"value": "24/7", "label": "operator readiness", "detail": "Support and governance from manager workflows."},
            {"value": "100%", "label": "subdomain tenancy", "detail": "Strict isolation for tenant security boundaries."},
        ],
        "GB": [
            {"value": "3", "label": "dedicated surfaces", "detail": "Public, tenant, and manager host separation."},
            {"value": "195+", "label": "country-ready profiles", "detail": "Registry-driven localization and defaults."},
            {"value": "24/7", "label": "operator readiness", "detail": "Support and governance from manager workflows."},
            {"value": "100%", "label": "subdomain tenancy", "detail": "Strict isolation for tenant security boundaries."},
        ],
    }
    # Use localized proof stats when country matches (regional or geo-personalized main landing)
    if country in _proof_by_country:
        proof_stats = _proof_by_country[country]

    institution_logos = [
        "Greenfield Academy",
        "Nile Valley Schools",
        "Toronto Scholars Group",
        "Douala Science Institute",
        "Kampala Future Leaders",
        "Maple Heights College",
        "Blue Coast International",
        "Riverside Preparatory",
    ]
    _logos_by_country = {
        "CM": ["Institut des Sciences Douala", "Lycée Bilingue", "École Greenfield", "Réseau Nile Valley", "Académie Maple", "Campus Riverside"],
        "CA": ["Toronto Scholars Group", "Maple Heights College", "Blue Coast International", "Riverside Preparatory", "Nile Valley Schools", "Greenfield Academy"],
    }
    if regional and country in _logos_by_country:
        institution_logos = _logos_by_country[country]

    admissions_flow = [
        {
            "title": "Capture enquiries",
            "body": "Collect parent leads with campaign-aware forms and route follow-up ownership by school.",
        },
        {
            "title": "Qualify and schedule",
            "body": "Track counselor interactions, interview status, and required documents in one flow.",
        },
        {
            "title": "Convert and onboard",
            "body": "Move accepted applicants into tenant enrollment and activate role-ready access.",
        },
    ]

    pricing_snapshot = [
        {
            "plan": "Starter",
            "tagline": "For single-campus schools",
            "highlights": [
                "Admissions and enrollment core",
                "Academics, attendance, and reports",
                "Parent, teacher, and student portals",
            ],
            "cta_label": "Start free trial",
            "cta_path": _safe_reverse("signup_school"),
        },
        {
            "plan": "Growth",
            "tagline": "For expanding school networks",
            "highlights": [
                "Multi-campus governance",
                "Regional branding and localization",
                "Support workflow and SLA visibility",
            ],
            "cta_label": "View pricing",
            "cta_path": "/pricing/",
        },
        {
            "plan": "Enterprise White-label",
            "tagline": "For operators at national scale",
            "highlights": [
                "Dedicated manager operations",
                "Advanced API and integration controls",
                "Compliance and audit governance",
            ],
            "cta_label": "Book architecture call",
            "cta_path": "/book-demo/",
        },
    ]

    trust_controls = [
        "FERPA and GDPR aligned workflows",
        "Audit trails for support and admin actions",
        "Role-based access and approval controls",
        "Regional compliance defaults per country profile",
        "Cross-subdomain CSRF and session guardrails",
        "Host-level routing contract enforcement",
    ]

    # Plan 4.11: Post-enrollment revenue section (Events, Online Courses, Alumni)
    post_enrollment_revenue = [
        {
            "title": "School Events",
            "body": "Event ticketing, venue management, and sponsor engagement for school fundraisers and activities.",
        },
        {
            "title": "Online Courses",
            "body": "Course creation, student tracking, and certification for revenue and extended learning.",
        },
        {
            "title": "Alumni Network",
            "body": "Mentorship programs, fundraising campaigns, and career services for alumni relations.",
        },
    ]

    # Plan 4.11: explicit "Global features" list for hero (full list from plan)
    global_features = [
        "Multi-Language",
        "Multi-Currency",
        "Timezone-aware",
        "Country-Specific Grading",
        "Localized Holiday Calendars",
        "Data Residency",
        "AI-Powered Insights",
        "Customizable Workflows",
        "Scalable Architecture",
        "24/7 Global Support",
    ]

    structured_data = {
        "@context": "https://schema.org",
        "@type": "SoftwareApplication",
        "name": "RunMyCampus",
        "applicationCategory": "EducationalApplication",
        "operatingSystem": "Web",
        "url": canonical_url,
        "description": pitch.get("seo_description"),
        "areaServed": brand.get("country_name") or "Global",
    }
    canonical_base_url = request.build_absolute_uri("/")
    organization_schema_json = json.dumps(_organization_schema(canonical_base_url))

    # A/B testing: persist variant in session for hero/CTA (Plan 4.11)
    hero_variant = request.session.get("marketing_ab_variant")
    if not hero_variant:
        hero_variant = random.choice(["A", "B"])
        request.session["marketing_ab_variant"] = hero_variant
    marketing_cta_variant = request.session.get("marketing_cta_variant") or ""
    if not marketing_cta_variant:
        marketing_cta_variant = random.choice(["default", "secondary"])
        request.session["marketing_cta_variant"] = marketing_cta_variant

    demo_tenant_url = getattr(settings, "MARKETING_DEMO_TENANT_URL", "") or ""
    marketing_analytics_script_url = getattr(settings, "MARKETING_ANALYTICS_SCRIPT_URL", "") or ""
    marketing_analytics_preconnect_origin = ""
    if marketing_analytics_script_url:
        try:
            parsed = urlparse(marketing_analytics_script_url)
            if parsed.scheme and parsed.netloc:
                marketing_analytics_preconnect_origin = f"{parsed.scheme}://{parsed.netloc}"
        except Exception:
            pass

    # Outcome-focused landing copy (world-class SaaS front). Wave 4: evidence-driven by geo and channel.
    # Plan: default hero headline exactly "The Global Operating System for Education"; primary CTA Start Free Trial, secondary Book demo.
    hero_headline = "The Global Operating System for Education"
    hero_subheadline = "One platform for admissions, academics, finance, communication, and compliance. Run your campus with clarity and scale."
    _hero_by_country = {
        "CM": {"headline": "La plateforme pour les établissements scolaires modernes.", "subheadline": "Admissions, académique, finance, communication et conformité dans une seule plateforme. Gérez votre campus avec clarté."},
        "CA": {"headline": "The Global Operating System for Education", "subheadline": "One platform for admissions, academics, finance, and compliance. Trusted by schools across Canada and beyond."},
        "NG": {"headline": "The Global Operating System for Education", "subheadline": "One platform for admissions, academics, finance, and compliance. Trusted by schools across Nigeria and Africa."},
        "GB": {"headline": "The Global Operating System for Education", "subheadline": "One platform for admissions, academics, finance, and compliance. Trusted by schools across the UK and beyond."},
    }
    _hero_by_channel = {
        "google": {"headline": "The Global Operating System for Education", "subheadline": "One platform for admissions, academics, finance, and compliance. Try free—no credit card required."},
        "linkedin": {"headline": "School operations, unified.", "subheadline": "For education leaders: admissions, finance, compliance, and reporting in one platform. Scale without sprawl."},
        "facebook": {"headline": "Run your school on one platform.", "subheadline": "Admissions, finance, and compliance in one place. Start free—no credit card required."},
        "newsletter": {"headline": "The Global Operating System for Education", "subheadline": "For subscribers: one platform for admissions, academics, finance, and compliance. Book a demo or start free."},
    }
    if country in _hero_by_country:
        hero_headline = _hero_by_country[country].get("headline", hero_headline)
        hero_subheadline = _hero_by_country[country].get("subheadline", hero_subheadline)
    utm_source = (request.GET.get("utm_source") or "").strip().lower()
    if utm_source in _hero_by_channel:
        hero_headline = _hero_by_channel[utm_source].get("headline", hero_headline)
        hero_subheadline = _hero_by_channel[utm_source].get("subheadline", hero_subheadline)
    hero_ctas = [
        {"label": "Start Free Trial", "url": _safe_reverse("signup_school"), "primary": True},
        {"label": "Book a Demo", "url": _safe_reverse("marketing_book_demo") or "/book-demo/", "primary": False},
        {"label": "Login", "url": _safe_reverse("global_login_discovery"), "primary": False},
    ]
    trust_logos = [
        {"name": "School Trust", "image_url": ""},
        {"name": "Edu Partners", "image_url": ""},
        {"name": "Global Schools", "image_url": ""},
    ]
    # Module screenshot paths relative to static root (SVG placeholders included; replace with PNGs if desired)
    core_modules = [
        {"title": "Admissions & Enrollment", "summary": "Capture leads, track applications, and onboard students in one flow.", "screenshot_url": "images/marketing/module-admissions.svg"},
        {"title": "Academics & Grades", "summary": "Syllabi, attendance, report cards, and interventions in a single source of truth.", "screenshot_url": "images/marketing/module-academics.svg"},
        {"title": "Finance & Billing", "summary": "Fees, payments, and financial reporting tailored to your school model.", "screenshot_url": "images/marketing/module-finance.svg"},
        {"title": "Communication", "summary": "Parents, teachers, and students stay connected with role-ready portals.", "screenshot_url": "images/marketing/module-communication.svg"},
        {"title": "Compliance & Reporting", "summary": "Audit trails, regional compliance defaults, and export-ready reports.", "screenshot_url": "images/marketing/module-compliance.svg"},
    ]
    platform_cards = [
        {"title": "Workflows that adapt", "summary": "From enquiry to graduation, every step is configurable to your school's processes and policies."},
        {"title": "Dashboards that inform", "summary": "Leaders get real-time visibility into enrollment, attendance, and outcomes without switching tools."},
        {"title": "Marketplace that extends", "summary": "Add integrations and apps from the marketplace without leaving the platform."},
    ]
    migration_bullets = [
        "Import students, staff, and historical data from spreadsheets or legacy systems.",
        "Map your existing workflows to RunMyCampus modules with guided setup.",
        "Go live with phased rollout and dedicated support during migration.",
    ]
    migration_studio_image_url = getattr(settings, "MARKETING_MIGRATION_STUDIO_IMAGE_URL", None) or ""
    hero_dashboard_image_url = getattr(settings, "MARKETING_HERO_IMAGE_URL", None) or ""
    if not hero_dashboard_image_url:
        hero_dashboard_image_url = static("images/marketing/hero-placeholder.svg")
    hero_video_url = getattr(settings, "MARKETING_HERO_VIDEO_URL", None) or ""
    hero_video_poster_url = getattr(settings, "MARKETING_HERO_VIDEO_POSTER_URL", None) or hero_dashboard_image_url or ""
    product_demo_image_url = getattr(settings, "MARKETING_PRODUCT_DEMO_IMAGE_URL", None) or getattr(settings, "MARKETING_HERO_IMAGE_URL", None) or ""
    # Product visualization strip: scrolling/tabbed UI screens (Student 360, teacher dashboard, admin analytics)
    product_visualization_slides = getattr(settings, "MARKETING_PRODUCT_VISUALIZATION_SLIDES", None) or [
        {"title": "Student 360", "caption": "One view per student: attendance, grades, interventions.", "image_url": "", "image_static": "images/marketing/viz-student360.svg"},
        {"title": "Teacher dashboard", "caption": "Grades, attendance, and class tools in one place.", "image_url": "", "image_static": "images/marketing/viz-teacher.svg"},
        {"title": "Admin analytics", "caption": "Real-time enrollment, finance, and compliance dashboards.", "image_url": "", "image_static": "images/marketing/viz-admin.svg"},
    ]
    _ecosystem_icon = static("images/marketing/logo-placeholder.svg")
    _marketplace_path = _safe_reverse("marketing_app_marketplace") or "/app-marketplace/"
    _integrations_path = _safe_reverse("marketing_integrations") or "/integrations/"
    ecosystem_apps = [
        {"name": "LMS / LTI", "summary": "Connect your learning management system.", "image_url": _ecosystem_icon, "install_path": _marketplace_path, "cta_path": _marketplace_path, "cta_label": "Explore"},
        {"name": "Payment gateways", "summary": "Stripe, PayPal, and local providers.", "image_url": _ecosystem_icon, "install_path": _integrations_path, "cta_path": _integrations_path, "cta_label": "View integrations"},
        {"name": "Messaging", "summary": "SMS and email providers for notifications.", "image_url": _ecosystem_icon, "install_path": _integrations_path, "cta_path": _integrations_path, "cta_label": "View integrations"},
        {"name": "Single sign-on", "summary": "SAML and OAuth for enterprise identity.", "image_url": _ecosystem_icon, "install_path": _integrations_path, "cta_path": _integrations_path, "cta_label": "View integrations"},
    ]
    testimonials = [
        {"quote": "We moved from spreadsheets to RunMyCampus in one term. Admissions and billing are finally in one place.", "author": "Sarah M.", "role": "Operations Director, Greenfield Academy", "stars": 5},
        {"quote": "Multi-campus visibility without losing each school's identity. Exactly what we needed.", "author": "James K.", "role": "Network Lead, Nile Valley Schools", "stars": 5},
        {"quote": "Compliance and reporting used to take days. Now we have dashboards and exports in minutes.", "author": "Priya L.", "role": "Finance & Compliance, Toronto Scholars", "stars": 5},
    ]
    # Video testimonials: list of {url, title, thumbnail_url}; override via MARKETING_VIDEO_TESTIMONIALS when ready
    _video_testimonials_setting = getattr(settings, "MARKETING_VIDEO_TESTIMONIALS", None)
    if _video_testimonials_setting:
        video_testimonials = _video_testimonials_setting
    else:
        video_testimonials = [
            {"url": _safe_reverse("marketing_landing") or "#", "title": "Customer story", "thumbnail_url": static("images/marketing/testimonial-thumb.svg")},
        ]
    security_badges = [
        "FERPA aligned",
        "GDPR ready",
        "SOC 2 roadmap",
        "Encryption at rest & in transit",
        "Role-based access",
    ]
    final_cta_headline = "Ready to run your campus with one platform?"

    # Phase 2: Institutional coverage (section 2) – K-12, Universities, Technical, Private, Government
    institution_types = [
        {"label": "K-12", "summary": "Elementary and secondary schools with enrollment, grades, and parent engagement.", "path": "/solutions/"},
        {"label": "Universities", "summary": "Higher ed admissions, academic structure, and multi-campus governance.", "path": "/solutions/"},
        {"label": "Technical schools", "summary": "Career and technical education with certification and placement tracking.", "path": "/solutions/"},
        {"label": "Private schools", "summary": "Independent and faith-based schools with full operations and fundraising.", "path": "/solutions/"},
        {"label": "Government education", "summary": "Public sector and government-run institutions with compliance and reporting.", "path": "/solutions/"},
    ]

    # Phase 2: Workflow automation (section 4)
    workflow_automation = [
        {"title": "Enquiry to enrollment", "body": "Capture leads, qualify applicants, and onboard students in one configurable flow."},
        {"title": "Grades and attendance", "body": "Syllabi, report cards, and interventions with role-ready dashboards for teachers and admins."},
        {"title": "Fees and payments", "body": "Billing cycles, payment gateways, and financial reporting without spreadsheets."},
        {"title": "Approvals and audits", "body": "Configurable approval chains and audit trails for compliance and governance."},
    ]

    # Phase 2: Developer platform (section 8) – one card for landing
    developer_platform_card = {
        "title": "Developer platform",
        "summary": "APIs, webhooks, and SDKs to integrate RunMyCampus with your LMS, SIS, and internal tools.",
        "cta_label": "Developer docs",
        "cta_path": _safe_reverse("marketing_developers") or "/developers/",
    }

    # Non-negotiables: platform narrative
    platform_headline = "The one platform for school and education operations."
    category_claim = "The Shopify and Salesforce of school and education management."
    platform_pillar_grid = [
        {"label": "Admissions to graduation", "sub": "One flow from enquiry to completion."},
        {"label": "Single campus to multi-country", "sub": "Scale without sprawl."},
        {"label": "K–12 to higher ed", "sub": "Every institution type."},
        {"label": "School-led or operator-led", "sub": "Your operating model."},
    ]
    from_single_to_enterprise = [
        {"stage": "Single school", "summary": "One campus, one tenant. Launch in days."},
        {"stage": "Network", "summary": "Multi-campus with central oversight and campus autonomy."},
        {"stage": "White-label operator", "summary": "National scale with dedicated manager operations and branding."},
    ]

    # Non-negotiables: social proof & scale
    by_the_numbers = [
        {"value": "195+", "label": "countries"},
        {"value": "99.9%", "label": "uptime target"},
        {"value": "1", "label": "platform"},
    ]
    # Outcome metrics for data viz (e.g. case study outcomes); optional bar_pct for mini chart (0-100)
    outcome_metrics = getattr(settings, "MARKETING_OUTCOME_METRICS", None) or [
        {"value": "40%", "label": "less admin workload", "detail": "Schools report reduced time on manual processes.", "bar_pct": 40},
        {"value": "2×", "label": "faster admissions", "detail": "From application to decision in half the time.", "bar_pct": 50},
    ]
    _logo_placeholder = static("images/marketing/logo-placeholder.svg")
    customer_logos = [
        {"name": "Greenfield Academy", "logo_url": _logo_placeholder},
        {"name": "Nile Valley Schools", "logo_url": _logo_placeholder},
        {"name": "Toronto Scholars", "logo_url": _logo_placeholder},
    ]
    awards_recognition = [
        "FERPA aligned",
        "GDPR ready",
        "SOC 2 roadmap",
    ]
    review_badges = [
        {"name": "Capterra", "url": "#", "stars": "4.8", "reviews": "50+"},
        {"name": "G2", "url": "#", "stars": "4.7", "reviews": "30+"},
    ]
    ten_reasons_page_path = _safe_reverse("marketing_10_reasons") or "/10-reasons/"

    # Non-negotiables: discovery (role + challenge)
    for_your_role = [
        {"label": "Principal", "path": _safe_reverse("marketing_solutions") or "/solutions/", "summary": "Visibility and control across your school."},
        {"label": "Admin", "path": _safe_reverse("role_school_admin") or "/roles/school-admin/", "summary": "Day-to-day operations in one place."},
        {"label": "Finance", "path": _safe_reverse("marketing_pricing") or "/pricing/", "summary": "Billing, fees, and reporting."},
        {"label": "IT", "path": _safe_reverse("role_it_directors") or "/roles/it-directors/", "summary": "Integrations, security, and provisioning."},
        {"label": "Teacher", "path": _safe_reverse("role_teachers") or "/roles/teachers/", "summary": "Grades, attendance, and class tools."},
        {"label": "Parent", "path": _safe_reverse("role_parents") or "/roles/parents/", "summary": "One portal for your children."},
        {"label": "Operator", "path": _safe_reverse("marketing_app_marketplace") or "/app-marketplace/", "summary": "Multi-tenant command center."},
    ]
    solve_by_challenge = [
        {"title": "Reduce admin burden", "path": _safe_reverse("marketing_product") or "/product/"},
        {"title": "Multi-campus visibility", "path": _safe_reverse("marketing_case_studies") or "/case-studies/"},
        {"title": "Parent engagement", "path": _safe_reverse("marketing_solutions") or "/solutions/"},
        {"title": "Migration from spreadsheets", "path": _safe_reverse("migrate_marketing_page") or "/migrate/"},
        {"title": "Compliance without the headache", "path": _safe_reverse("marketing_security_compliance") or "/security-compliance/"},
    ]

    # Non-negotiables: ecosystem
    app_marketplace_hero = {
        "title": "App Marketplace",
        "summary": "Extend RunMyCampus with integrations and apps. Connect your LMS, payments, messaging, and identity providers.",
        "app_count": "50+",
        "cta_path": _safe_reverse("marketing_app_marketplace") or "/app-marketplace/",
        "cta_label": "View App Marketplace",
    }
    developer_story_summary = "By developers, for developers. APIs, webhooks, and SDKs let you build apps and integrations that schools install. Create custom storefronts and extend the platform."
    partners_list = [
        {"name": "Implementation Partner 1", "url": "#"},
        {"name": "Implementation Partner 2", "url": "#"},
    ]
    integrations_strip = ["Clever", "Google Classroom", "Stripe", "PayPal", "SAML", "OAuth"]

    # Non-negotiables: thought leadership
    gated_report_cta = {
        "headline": "Download the State of School Operations report",
        "url": _safe_reverse("marketing_resources") or "/resources/",
        "cta_label": "Get the report",
    }
    second_lead_magnet = {
        "title": "Implementation checklist",
        "summary": "Step-by-step checklist to go live with RunMyCampus.",
        "url": _safe_reverse("marketing_buyer_toolkit_download", kwargs={"document": "implementation-checklist"}) or "/buyer-toolkit/download/implementation-checklist/",
    }
    resources_hub_path = _safe_reverse("marketing_resources") or "/resources/"

    # Non-negotiables: events & community
    events_list = [
        {"title": "Customer roundtable: Migration in 90 days", "date": "Monthly", "cta_url": _safe_reverse("marketing_events") or "/events/", "cta_label": "Register"},
    ]
    flagship_event = {
        "name": "RunMyCampus Live",
        "summary": "Annual education operations summit. Be first to know when we announce dates.",
        "cta_url": _safe_reverse("marketing_events") or "/events/",
        "cta_label": "Be first to know",
    }
    community_cta = {
        "label": "Join our newsletter",
        "url": _safe_reverse("marketing_contact") or "/contact/",
        "summary": "Get product updates and best practices.",
    }

    # Non-negotiables: trust & support
    support_implementation_copy = "We set you up. Dedicated onboarding and support when you need it—so you're not just buying software, you're getting a partner for go-live."
    accessibility_line = "Accessible by design. We align with inclusive design practices and regional accessibility requirements."
    why_switch_path = _safe_reverse("marketing_why_switch") or "/why-switch/"

    # Non-negotiables: 3-step get started
    get_started_three_steps = [
        {"step": 1, "title": "Sign up", "body": "Start your free trial—no credit card required."},
        {"step": 2, "title": "Add your school", "body": "Configure your tenant, terms, and branding."},
        {"step": 3, "title": "Invite your team", "body": "Invite admins, teachers, and parents. Go live."},
    ]

    # Non-negotiables: product pillars (6) + AI + differentiation; link to deep product pages when available
    product_pillars_home = [
        {"title": "Admissions & Enrollment", "summary": "Capture leads, track applications, onboard students.", "path": _safe_reverse("marketing_products_admissions") or "/products/admissions/"},
        {"title": "Academics & Grades", "summary": "Syllabi, attendance, report cards, interventions.", "path": _safe_reverse("marketing_products_academics") or "/products/academics/"},
        {"title": "Finance & Billing", "summary": "Fees, payments, financial reporting.", "path": _safe_reverse("marketing_products_finance") or "/products/finance/"},
        {"title": "Communication", "summary": "Role-ready portals for parents, teachers, students.", "path": _safe_reverse("marketing_products_communication") or "/products/communication/"},
        {"title": "Compliance & Reporting", "summary": "Audit trails, regional compliance, export-ready reports.", "path": _safe_reverse("marketing_security_compliance") or "/security-compliance/"},
        {"title": "Manager / Operations", "summary": "Super-admin command center for multi-tenant operators.", "path": _safe_reverse("marketing_app_marketplace") or "/app-marketplace/"},
    ]
    hero_ai_line = "One platform for admissions, academics, finance, and compliance—with AI that helps your team save time."
    differentiation_block = [
        "Multi-tenant from day one: each school gets its own domain, branding, and data.",
        "Operator layer: one control plane for many campuses.",
        "Global-first: multi-currency, multi-language, multi-timezone, country-specific grading.",
        "One product: no feature sprawl—admissions, academics, finance, communication, compliance in one place.",
    ]

    # Enterprise path
    enterprise_path_copy = "For operators at national scale. Book an architecture call for dedicated governance, compliance posture, and white-label branding."

    # Asset defaults: use static placeholders when settings are unset (no 404s)
    global_map_image_url = getattr(settings, "MARKETING_GLOBAL_MAP_IMAGE_URL", None) or static("images/marketing/global-map.svg")
    illustration_workflow_url = getattr(settings, "MARKETING_ILLUSTRATION_WORKFLOW_URL", None) or static("images/marketing/illustration-workflow.svg")
    illustration_globe_url = getattr(settings, "MARKETING_ILLUSTRATION_GLOBE_URL", None) or static("images/marketing/illustration-globe.svg")
    illustration_students_url = getattr(settings, "MARKETING_ILLUSTRATION_STUDENTS_URL", None) or static("images/marketing/illustration-students.svg")

    # AI Intelligence section: dedicated homepage block (optional enhancements)
    ai_intelligence_features = [
        "Predict at-risk students and recommend interventions.",
        "Surface insights for enrollment and retention.",
        "Automate routine reporting so staff focus on teaching.",
    ]
    ai_intelligence_cta_path = _safe_reverse("marketing_products_analytics") or _safe_reverse("marketing_landing") or "/"

    return {
        "pitch": pitch,
        "brand": brand,
        "country_code": country,
        "language_code": language,
        "seo_title": pitch.get("seo_title"),
        "seo_description": pitch.get("seo_description"),
        "canonical_url": canonical_url,
        "hreflang_entries": hreflang_entries,
        "structured_data_json": json.dumps(structured_data),
        "marketing_nav": _marketing_nav(),
        "topical_nav": _topical_nav(),
        "canonical_domain": canonical_domain,
        "public_host": public_host,
        "manager_host": manager_host,
        "api_host": api_host,
        "docs_host": docs_host,
        "tenant_example_host": tenant_host,
        "surface_cards": surface_cards,
        "authority_metrics": authority_metrics,
        "proof_points": proof_points,
        "trust_badges": trust_badges,
        "rollout_steps": rollout_steps,
        "audience_segments": audience_segments,
        "proof_stats": proof_stats,
        "institution_logos": institution_logos,
        "admissions_flow": admissions_flow,
        "pricing_snapshot": pricing_snapshot,
        "trust_controls": trust_controls,
        "post_enrollment_revenue": post_enrollment_revenue,
        "global_features": global_features,
        "hero_variant": hero_variant,
        "marketing_cta_variant": marketing_cta_variant,
        "demo_tenant_url": demo_tenant_url,
        "marketing_analytics_script_url": marketing_analytics_script_url,
        "marketing_analytics_preconnect_origin": marketing_analytics_preconnect_origin,
        "SHOW_HEADER_CONTEXT_STRIP": False,
        # Landing revamp: outcome-focused copy and 10-section context
        "marketing_navbar_primary": _marketing_navbar_primary(),
        "hero_headline": hero_headline,
        "hero_subheadline": hero_subheadline,
        "hero_ctas": hero_ctas,
        "trust_logos": trust_logos,
        "core_modules": core_modules,
        "platform_cards": platform_cards,
        "migration_bullets": migration_bullets,
        "migration_studio_image_url": migration_studio_image_url,
        "ecosystem_apps": ecosystem_apps,
        "testimonials": testimonials,
        "video_testimonials": video_testimonials,
        "security_badges": security_badges,
        "final_cta_headline": final_cta_headline,
        "hero_dashboard_image_url": hero_dashboard_image_url,
        "hero_dashboard_image_srcset": getattr(settings, "MARKETING_HERO_IMAGE_SRCSET", None) or "",
        "hero_dashboard_image_sizes": getattr(settings, "MARKETING_HERO_IMAGE_SIZES", None) or "(max-width: 800px) 100vw, 800px",
        "hero_video_url": hero_video_url,
        "hero_video_poster_url": hero_video_poster_url,
        "product_demo_image_url": product_demo_image_url,
        "product_visualization_slides": product_visualization_slides,
        "organization_schema_json": organization_schema_json,
        "geo_copy": _geo_copy_variations(country),
        "marketing_calendly_url": getattr(settings, "MARKETING_CALENDLY_URL", None) or "",
        "institution_types": institution_types,
        "workflow_automation": workflow_automation,
        "developer_platform_card": developer_platform_card,
        "platform_headline": platform_headline,
        "category_claim": category_claim,
        "platform_pillar_grid": platform_pillar_grid,
        "from_single_to_enterprise": from_single_to_enterprise,
        "by_the_numbers": by_the_numbers,
        "outcome_metrics": outcome_metrics,
        "global_map_image_url": global_map_image_url,
        "global_stats": getattr(settings, "MARKETING_GLOBAL_STATS", None) or [
            {"label": "Countries", "value": "195+"},
            {"label": "Currencies", "value": "Multi-currency"},
            {"label": "Languages", "value": "Multi-language"},
        ],
        "illustration_workflow_url": illustration_workflow_url,
        "illustration_globe_url": illustration_globe_url,
        "illustration_students_url": illustration_students_url,
        "ai_intelligence_features": ai_intelligence_features,
        "ai_intelligence_cta_path": ai_intelligence_cta_path,
        "customer_logos": customer_logos,
        "awards_recognition": awards_recognition,
        "review_badges": review_badges,
        "ten_reasons_page_path": ten_reasons_page_path,
        "for_your_role": for_your_role,
        "solve_by_challenge": solve_by_challenge,
        "app_marketplace_hero": app_marketplace_hero,
        "developer_story_summary": developer_story_summary,
        "partners_list": partners_list,
        "integrations_strip": integrations_strip,
        "gated_report_cta": gated_report_cta,
        "second_lead_magnet": second_lead_magnet,
        "resources_hub_path": resources_hub_path,
        "events_list": events_list,
        "flagship_event": flagship_event,
        "community_cta": community_cta,
        "support_implementation_copy": support_implementation_copy,
        "accessibility_line": accessibility_line,
        "why_switch_path": why_switch_path,
        "get_started_three_steps": get_started_three_steps,
        "product_pillars_home": product_pillars_home,
        "hero_ai_line": hero_ai_line,
        "differentiation_block": differentiation_block,
        "enterprise_path_copy": enterprise_path_copy,
    }


def _organization_schema(canonical_base_url: str) -> dict:
    """Schema.org Organization for RunMyCampus (Wave 2 SEO)."""
    return {
        "@context": "https://schema.org",
        "@type": "Organization",
        "name": "RunMyCampus",
        "url": canonical_base_url,
        "description": "RunMyCampus is a global school operations platform for admissions, academics, finance, and compliance.",
        "applicationCategory": "EducationalApplication",
    }


def _faq_schema(faq_list: list[dict], canonical_url: str) -> dict:
    """Schema.org FAQPage from list of {question, answer} (Wave 2 SEO)."""
    return {
        "@context": "https://schema.org",
        "@type": "FAQPage",
        "url": canonical_url,
        "mainEntity": [
            {"@type": "Question", "name": faq["question"], "acceptedAnswer": {"@type": "Answer", "text": faq["answer"]}}
            for faq in faq_list
        ],
    }


def _breadcrumb_list_schema(canonical_base_url: str, path_segments: list[tuple[str, str]]) -> dict:
    """Schema.org BreadcrumbList from (name, path) segments. path is relative (e.g. /, /product/)."""
    base = canonical_base_url.rstrip("/")
    items = []
    for i, (name, path) in enumerate(path_segments, 1):
        p = path if path.startswith("/") else "/" + path
        item_url = base + p if p != "/" else base + "/"
        items.append({
            "@type": "ListItem",
            "position": i,
            "name": name,
            "item": item_url,
        })
    return {
        "@context": "https://schema.org",
        "@type": "BreadcrumbList",
        "itemListElement": items,
    }


def _structured_data_for_page(*, page_type: str, canonical_url: str, name: str, description: str, path: str) -> dict:
    base_url = canonical_url.rsplit(path, 1)[0] + "/" if path in canonical_url else canonical_url
    payload: dict = {
        "@context": "https://schema.org",
        "@type": page_type,
        "name": name,
        "url": canonical_url,
        "description": description,
        "isPartOf": {"@type": "WebSite", "name": "RunMyCampus", "url": base_url},
    }
    if page_type == "OfferCatalog":
        payload["itemListElement"] = [
            {"@type": "Offer", "name": "Starter", "description": "For single-campus schools: admissions, academics, portals."},
            {"@type": "Offer", "name": "Growth", "description": "For expanding networks: multi-campus, localization, support visibility."},
            {"@type": "Offer", "name": "Enterprise", "description": "White-label for national scale: manager operations, API, compliance."},
        ]
    if page_type == "ItemList":
        payload["itemListElement"] = [
            {"@type": "ListItem", "position": 1, "name": "LTI interoperability"},
            {"@type": "ListItem", "position": 2, "name": "Payment gateways"},
            {"@type": "ListItem", "position": 3, "name": "Messaging providers"},
        ]
    if page_type == "Service":
        payload["provider"] = {"@type": "Organization", "name": "RunMyCampus"}
        payload["serviceType"] = "School management platform demonstration"
    return payload


def _marketing_base_context(request) -> dict:
    geo_country = _get_country_from_request(request)
    return _marketing_context(
        request,
        country_code=geo_country,
        language_code=(getattr(request, "LANGUAGE_CODE", "") or "en"),
        regional=False,
    )


@require_GET
def marketing_landing(request):
    """Global marketing landing with geo-personalized copy."""
    from apps.schools.funnel_events import record_marketing_funnel_event
    record_marketing_funnel_event("visit", request)
    geo_country = _get_country_from_request(request)
    ctx = _marketing_context(
        request,
        country_code=geo_country,
        language_code=(getattr(request, "LANGUAGE_CODE", "") or "en"),
        regional=False,
    )
    return render(request, "schools/marketing_landing.html", ctx)


def _get_blog_posts(limit: int = 20):
    """Return published blog posts for marketing blog page; empty list if model unavailable."""
    try:
        from apps.siteconfig.models import BlogPost

        return list(
            BlogPost.objects.filter(is_published=True)
            .order_by("-published_at", "-created_at")[:limit]
        )
    except Exception:
        return []


@require_GET
def blog_post_detail(request, slug: str):
    """Single blog post at /blog/<slug>/."""
    try:
        from apps.siteconfig.models import BlogPost

        post = BlogPost.objects.filter(slug=slug, is_published=True).first()
    except Exception:
        post = None
    if not post:
        raise Http404("Blog post not found")

    base_ctx = _marketing_base_context(request)
    canonical_path = f"/blog/{post.slug}/"
    canonical_url = _absolute_url(request, canonical_path)
    ctx = {
        **base_ctx,
        "seo_title": post.title,
        "seo_description": (post.excerpt or post.title)[:160],
        "canonical_url": canonical_url,
        "post": post,
        "active_nav_slug": "blog",
    }
    return render(request, "schools/marketing_blog_detail.html", ctx)


@require_GET
def marketing_page(request, page_slug: str):
    normalized_slug = (page_slug or "").strip().lower()
    loaded = _load_marketing_page_from_file(normalized_slug)
    if loaded:
        page_copy = deepcopy(loaded[0])
        page_extras = deepcopy(loaded[1])
    else:
        page = MARKETING_PAGE_DEFINITIONS.get(normalized_slug)
        if not page:
            raise Http404("Page not found")
        page_copy = deepcopy(page)
        page_extras = deepcopy(MARKETING_PAGE_EXTRAS.get(normalized_slug, {}))
    base_ctx = _marketing_base_context(request)
    canonical_path = f"/{page_slug}/"
    canonical_url = _absolute_url(request, canonical_path)
    page_copy["slug"] = page_slug
    page_copy["path"] = canonical_path

    structured_data = _structured_data_for_page(
        page_type=page_copy.get("schema_type") or "WebPage",
        canonical_url=canonical_url,
        name=page_copy.get("label") or "RunMyCampus",
        description=page_copy.get("seo_description") or "",
        path=canonical_path,
    )

    blog_posts = _get_blog_posts() if page_slug == "blog" else []
    faq_schema_json = ""
    if page_extras.get("faqs"):
        faq_schema_json = json.dumps(_faq_schema(page_extras["faqs"], canonical_url))

    # BreadcrumbList schema: Home > Page label
    base_url = _absolute_url(request, "/").rstrip("/")
    breadcrumb_segments = [("Home", "/"), (page_copy.get("label") or page_slug, canonical_path)]
    breadcrumb_schema_json = json.dumps(_breadcrumb_list_schema(base_url, breadcrumb_segments))

    # Wave 3: SLA/uptime status URL from settings for trust-center
    if page_slug == "trust-center" and page_extras.get("sla_uptime"):
        status_url = getattr(settings, "MARKETING_STATUS_PAGE_URL", None) or ""
        page_extras["sla_uptime"] = {**page_extras["sla_uptime"], "status_url": status_url}

    ctx = {
        **base_ctx,
        "seo_title": page_copy.get("seo_title"),
        "seo_description": page_copy.get("seo_description"),
        "canonical_url": canonical_url,
        "structured_data_json": json.dumps(structured_data),
        "faq_schema_json": faq_schema_json,
        "breadcrumb_schema_json": breadcrumb_schema_json,
        "page": page_copy,
        "page_extras": page_extras,
        "active_nav_slug": page_slug,
        "blog_posts": blog_posts,
        "powerhouse_highlights": [
            "Predictive risk scoring and intervention action-center workflows.",
            "Student passport and transcript portability across schools.",
            "Super-admin mission control for approvals, billing, and support.",
        ],
    }
    return render(request, "schools/marketing_page.html", ctx)


@require_POST
@csrf_protect
def submit_demo_request(request):
    """
    Accept book-a-demo form POST (name, email, school, message).
    If MARKETING_DEMO_WEBHOOK_URL is set, POST JSON to it; then redirect to book-demo with ?submitted=1 or ?error=1.
    """
    name = (request.POST.get("name") or "").strip()[:256]
    email = (request.POST.get("email") or "").strip()[:256]
    school = (request.POST.get("school") or "").strip()[:256]
    message = (request.POST.get("message") or "").strip()[:2000]
    webhook_url = getattr(settings, "MARKETING_DEMO_WEBHOOK_URL", None) or ""
    success = False
    if webhook_url and email:
        payload = json.dumps({
            "name": name,
            "email": email,
            "school": school,
            "message": message,
        })
        try:
            from urllib.request import Request, urlopen
            from urllib.error import URLError, HTTPError

            req = Request(
                webhook_url,
                data=payload.encode("utf-8"),
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            urlopen(req, timeout=10)
            success = True
        except (URLError, HTTPError, OSError):
            pass
    elif email:
        # No webhook configured; still count as success so user sees confirmation (admin can check logs or add webhook later)
        success = True
    redirect_url = reverse("marketing_book_demo")
    if success:
        redirect_url += "?submitted=1"
    else:
        redirect_url += "?error=1"
    return redirect(redirect_url)


# Wave 3: Downloadable buyer toolkit and implementation checklist
_BUYER_CHECKLIST_HTML = """<!DOCTYPE html>
<html lang="en">
<head><meta charset="utf-8"><title>RunMyCampus Buyer Evaluation Checklist</title></head>
<body>
<h1>RunMyCampus Buyer Evaluation Checklist</h1>
<p>Use this checklist before you commit. RunMyCampus — The Operating System for Modern Schools.</p>
<h2>Tenancy &amp; architecture</h2>
<ul>
<li>[ ] Subdomain-based tenant isolation (not path-based)</li>
<li>[ ] Dedicated manager host for support and governance</li>
<li>[ ] Clear public / tenant / manager host contract</li>
</ul>
<h2>Security &amp; compliance</h2>
<ul>
<li>[ ] FERPA / GDPR alignment and regional compliance defaults</li>
<li>[ ] Audit trails for admin and support actions</li>
<li>[ ] Encryption at rest and in transit</li>
<li>[ ] Role-based access controls</li>
</ul>
<h2>Localization</h2>
<ul>
<li>[ ] Multi-language and multi-currency support</li>
<li>[ ] Country-specific grading and terminology</li>
<li>[ ] Data residency options</li>
</ul>
<h2>Support &amp; operations</h2>
<ul>
<li>[ ] 24/7 operator readiness and support visibility</li>
<li>[ ] Migration tools and guided setup</li>
<li>[ ] API and documentation host</li>
</ul>
<p>Downloaded from runmycampus.com. &copy; RunMyCampus.</p>
</body>
</html>
"""

_IMPLEMENTATION_CHECKLIST_HTML = """<!DOCTYPE html>
<html lang="en">
<head><meta charset="utf-8"><title>RunMyCampus Implementation Checklist</title></head>
<body>
<h1>RunMyCampus Implementation Checklist</h1>
<p>Phased rollout with role ownership. Track progress by phase.</p>
<h2>Phase 1 — Discovery and signup (Owner: School lead)</h2>
<ul>
<li>[ ] Evaluate platform fit and compare architecture</li>
<li>[ ] Start free trial</li>
<li>[ ] Confirm data and compliance requirements</li>
</ul>
<h2>Phase 2 — Tenant and data setup (Owner: IT)</h2>
<ul>
<li>[ ] Provision tenant and configure branding</li>
<li>[ ] Import students and staff</li>
<li>[ ] Configure SSO and integrations (LMS, payments, messaging)</li>
</ul>
<h2>Phase 3 — Finance and billing (Owner: Finance)</h2>
<ul>
<li>[ ] Configure fee structure and payment terms</li>
<li>[ ] Connect payment gateway</li>
<li>[ ] Run first billing cycle and reconcile</li>
</ul>
<h2>Phase 4 — Academics and go-live (Owner: Admissions / Academics)</h2>
<ul>
<li>[ ] Configure grading, terms, and report cards</li>
<li>[ ] Train teachers and staff</li>
<li>[ ] Go live and monitor; hand off to support</li>
</ul>
<p>Downloaded from runmycampus.com. &copy; RunMyCampus.</p>
</body>
</html>
"""


@require_GET
def buyer_toolkit_download(request, document: str):
    """Serve downloadable buyer or implementation checklist as HTML (save as PDF from browser)."""
    if document == "implementation-checklist":
        content = _IMPLEMENTATION_CHECKLIST_HTML
        filename = "runmycampus-implementation-checklist.html"
    elif document == "buyer-checklist":
        content = _BUYER_CHECKLIST_HTML
        filename = "runmycampus-buyer-evaluation-checklist.html"
    else:
        raise Http404("Document not found")
    response = HttpResponse(content, content_type="text/html; charset=utf-8")
    response["Content-Disposition"] = f'attachment; filename="{filename}"'
    return response


@require_GET
@staff_member_required
def marketing_funnel_dashboard(request):
    """Wave 4: Conversion funnel dashboard (visit -> discovery -> signup -> activation). Staff only."""
    from apps.schools.models import MarketingFunnelEvent

    now = timezone.now()
    all_time = MarketingFunnelEvent.objects.values("event_type").annotate(count=Count("id"))
    all_time_map = {r["event_type"]: r["count"] for r in all_time}
    visit = all_time_map.get("visit", 0)
    discovery = all_time_map.get("discovery", 0)
    signup = all_time_map.get("signup", 0)
    activation = all_time_map.get("activation", 0)

    # Last 7 and 30 days
    from datetime import timedelta
    week_ago = now - timedelta(days=7)
    month_ago = now - timedelta(days=30)
    last7 = MarketingFunnelEvent.objects.filter(created_at__gte=week_ago).values("event_type").annotate(count=Count("id"))
    last30 = MarketingFunnelEvent.objects.filter(created_at__gte=month_ago).values("event_type").annotate(count=Count("id"))
    last7_map = {r["event_type"]: r["count"] for r in last7}
    last30_map = {r["event_type"]: r["count"] for r in last30}

    # By channel (utm_source / utm_medium) for last 30 days
    channel_qs = (
        MarketingFunnelEvent.objects.filter(created_at__gte=month_ago)
        .values("utm_source", "utm_medium")
        .annotate(
            visit=Count("id", filter=Q(event_type="visit")),
            discovery=Count("id", filter=Q(event_type="discovery")),
            signup=Count("id", filter=Q(event_type="signup")),
            activation=Count("id", filter=Q(event_type="activation")),
        )
        .order_by("-visit")
    )
    channel_breakdown = [
        {
            "utm_source": r.get("utm_source") or "",
            "utm_medium": r.get("utm_medium") or "",
            "visit": r.get("visit", 0),
            "discovery": r.get("discovery", 0),
            "signup": r.get("signup", 0),
            "activation": r.get("activation", 0),
        }
        for r in channel_qs
    ]

    base_ctx = _marketing_base_context(request)
    ctx = {
        **base_ctx,
        "visit": visit,
        "discovery": discovery,
        "signup": signup,
        "activation": activation,
        "last7": last7_map,
        "last30": last30_map,
        "channel_breakdown": channel_breakdown,
    }
    return render(request, "schools/marketing_funnel_dashboard.html", ctx)


@require_GET
def topical_marketing_landing(request, topic_slug: str):
    topic = TOPICAL_LANDING_DEFINITIONS.get((topic_slug or "").strip().lower())
    if not topic:
        raise Http404("Topic not found")

    base_ctx = _marketing_base_context(request)
    canonical_path = f"/solutions/{topic_slug}/"
    canonical_url = _absolute_url(request, canonical_path)
    topic_copy = deepcopy(topic)
    topic_copy["slug"] = topic_slug
    topic_copy["path"] = canonical_path
    related_slugs = topic_copy.get("related_slugs") or []
    topic_copy["related_topics"] = [
        {"slug": s, "label": TOPICAL_LANDING_DEFINITIONS.get(s, {}).get("label", s)}
        for s in related_slugs
        if s
    ]

    structured_data = _structured_data_for_page(
        page_type="CollectionPage",
        canonical_url=canonical_url,
        name=topic_copy.get("label") or "RunMyCampus",
        description=topic_copy.get("seo_description") or "",
        path=canonical_path,
    )

    base_url = _absolute_url(request, "/").rstrip("/")
    breadcrumb_segments = [("Home", "/"), ("Solutions", "/solutions/"), (topic_copy.get("label") or topic_slug, canonical_path)]
    breadcrumb_schema_json = json.dumps(_breadcrumb_list_schema(base_url, breadcrumb_segments))

    ctx = {
        **base_ctx,
        "seo_title": topic_copy.get("seo_title"),
        "seo_description": topic_copy.get("seo_description"),
        "canonical_url": canonical_url,
        "structured_data_json": json.dumps(structured_data),
        "breadcrumb_schema_json": breadcrumb_schema_json,
        "topic": topic_copy,
        "active_nav_slug": "solutions",
    }
    return render(request, "schools/marketing_topic_page.html", ctx)


@require_GET
def institution_marketing_page(request, institution_slug: str):
    """Institutional segment landing: K-12, universities, technical-schools, private-schools, government-education."""
    definition = INSTITUTION_LANDING_DEFINITIONS.get((institution_slug or "").strip().lower())
    if not definition:
        raise Http404("Institution segment not found")
    base_ctx = _marketing_base_context(request)
    canonical_path = f"/solutions/{institution_slug}/"
    canonical_url = _absolute_url(request, canonical_path)
    page_copy = deepcopy(definition)
    page_copy["slug"] = institution_slug
    structured_data = _structured_data_for_page(
        page_type="CollectionPage",
        canonical_url=canonical_url,
        name=page_copy.get("label") or "RunMyCampus",
        description=page_copy.get("seo_description") or "",
        path=canonical_path,
    )
    base_url = _absolute_url(request, "/").rstrip("/")
    breadcrumb_segments = [("Home", "/"), ("Solutions", "/solutions/"), (page_copy.get("label") or institution_slug, canonical_path)]
    breadcrumb_schema_json = json.dumps(_breadcrumb_list_schema(base_url, breadcrumb_segments))
    ctx = {
        **base_ctx,
        "seo_title": page_copy.get("seo_title"),
        "seo_description": page_copy.get("seo_description"),
        "canonical_url": canonical_url,
        "structured_data_json": json.dumps(structured_data),
        "breadcrumb_schema_json": breadcrumb_schema_json,
        "page": page_copy,
        "active_nav_slug": "solutions",
    }
    return render(request, "marketing/marketing_institution_page.html", ctx)


@require_GET
def role_marketing_page(request, role_slug: str):
    """Role-based landing: school-admin, teachers, parents, students, it-directors, government."""
    definition = ROLE_PAGE_DEFINITIONS.get((role_slug or "").strip().lower())
    if not definition:
        raise Http404("Role page not found")
    base_ctx = _marketing_base_context(request)
    canonical_path = f"/roles/{role_slug}/"
    canonical_url = _absolute_url(request, canonical_path)
    page_copy = deepcopy(definition)
    page_copy["slug"] = role_slug
    structured_data = _structured_data_for_page(
        page_type="WebPage",
        canonical_url=canonical_url,
        name=page_copy.get("label") or "RunMyCampus",
        description=page_copy.get("seo_description") or "",
        path=canonical_path,
    )
    base_url = _absolute_url(request, "/").rstrip("/")
    breadcrumb_segments = [("Home", "/"), ("Roles", "/roles/"), (page_copy.get("label") or role_slug, canonical_path)]
    breadcrumb_schema_json = json.dumps(_breadcrumb_list_schema(base_url, breadcrumb_segments))
    ctx = {
        **base_ctx,
        "seo_title": page_copy.get("seo_title"),
        "seo_description": page_copy.get("seo_description"),
        "canonical_url": canonical_url,
        "structured_data_json": json.dumps(structured_data),
        "breadcrumb_schema_json": breadcrumb_schema_json,
        "page": page_copy,
        "active_nav_slug": "solutions",
    }
    return render(request, "marketing/marketing_role_page.html", ctx)


@require_GET
def migrate_marketing_page(request, source_slug: str | None = None):
    """Migration landing: /migrate/ (generic) or /migrate/from-power-school/ etc."""
    slug_key = (source_slug or "").strip().lower() if source_slug else ""
    definition = MIGRATE_PAGE_DEFINITIONS.get(slug_key)
    if not definition:
        raise Http404("Migration page not found")
    base_ctx = _marketing_base_context(request)
    canonical_path = f"/migrate/{source_slug}/" if source_slug else "/migrate/"
    canonical_url = _absolute_url(request, canonical_path)
    page_copy = deepcopy(definition)
    page_copy["slug"] = slug_key
    structured_data = _structured_data_for_page(
        page_type="WebPage",
        canonical_url=canonical_url,
        name="Migrate to RunMyCampus",
        description=page_copy.get("seo_description") or "",
        path=canonical_path,
    )
    base_url = _absolute_url(request, "/").rstrip("/")
    breadcrumb_segments = [("Home", "/"), ("Migrate", "/migrate/")]
    if slug_key:
        breadcrumb_segments.append((page_copy.get("headline", "Migration"), canonical_path))
    breadcrumb_schema_json = json.dumps(_breadcrumb_list_schema(base_url, breadcrumb_segments))
    ctx = {
        **base_ctx,
        "seo_title": page_copy.get("seo_title"),
        "seo_description": page_copy.get("seo_description"),
        "canonical_url": canonical_url,
        "structured_data_json": json.dumps(structured_data),
        "breadcrumb_schema_json": breadcrumb_schema_json,
        "page": page_copy,
        "active_nav_slug": "compare",
    }
    return render(request, "marketing/marketing_migrate_page.html", ctx)


@require_GET
def compare_marketing_page(request, competitor_slug: str):
    """Compare RunMyCampus vs competitor: power-school, blackbaud, infinite-campus."""
    definition = COMPARE_PAGE_DEFINITIONS.get((competitor_slug or "").strip().lower())
    if not definition:
        raise Http404("Compare page not found")
    base_ctx = _marketing_base_context(request)
    canonical_path = f"/compare/{competitor_slug}/"
    canonical_url = _absolute_url(request, canonical_path)
    page_copy = deepcopy(definition)
    page_copy["slug"] = competitor_slug
    structured_data = _structured_data_for_page(
        page_type="WebPage",
        canonical_url=canonical_url,
        name=f"RunMyCampus vs {page_copy.get('competitor_name', competitor_slug)}",
        description=page_copy.get("seo_description") or "",
        path=canonical_path,
    )
    base_url = _absolute_url(request, "/").rstrip("/")
    breadcrumb_segments = [("Home", "/"), ("Compare", "/compare/"), (page_copy.get("competitor_name", competitor_slug), canonical_path)]
    breadcrumb_schema_json = json.dumps(_breadcrumb_list_schema(base_url, breadcrumb_segments))
    ctx = {
        **base_ctx,
        "seo_title": page_copy.get("seo_title"),
        "seo_description": page_copy.get("seo_description"),
        "canonical_url": canonical_url,
        "structured_data_json": json.dumps(structured_data),
        "breadcrumb_schema_json": breadcrumb_schema_json,
        "page": page_copy,
        "active_nav_slug": "compare",
    }
    return render(request, "marketing/marketing_compare_page.html", ctx)


DEVELOPER_PAGE_DEFINITIONS = {
    "api": {
        "label": "API",
        "seo_title": "RunMyCampus API - OpenAPI and REST",
        "seo_description": "REST API and OpenAPI schema for RunMyCampus integrations.",
        "headline": "API overview",
        "subheadline": "REST API and OpenAPI schema available at your school subdomain after login.",
        "sections": [
            {"title": "Schema", "body": "OpenAPI 3 schema at /api/schema/ui/ on your tenant subdomain."},
            {"title": "Authentication", "body": "POST /api/auth/token/ with username/password; use Bearer token in Authorization header."},
        ],
    },
    "webhooks": {
        "label": "Webhooks",
        "seo_title": "RunMyCampus Webhooks",
        "seo_description": "Webhook events and payloads for RunMyCampus integrations.",
        "headline": "Webhooks",
        "subheadline": "Subscribe to events and receive payloads at your endpoint.",
        "sections": [
            {"title": "Events", "body": "Subscribe to enrollment, grade, and billing events."},
            {"title": "Delivery", "body": "Signed payloads and retry policy; configure in tenant settings."},
        ],
    },
    "integrations": {
        "label": "Integrations",
        "seo_title": "RunMyCampus Integrations - Developers",
        "seo_description": "Build integrations with RunMyCampus: SIS, LMS, payments.",
        "headline": "Integrations",
        "subheadline": "Connect SIS, LMS, payment gateways, and identity providers.",
        "sections": [
            {"title": "LTI 1.3", "body": "LTI launch and deep linking; readiness at /api/interop/lti13/."},
            {"title": "OneRoster", "body": "OneRoster API and CSV; readiness at /api/interop/oneroster/."},
            {"title": "Ed-Fi & CEDS", "body": "Ed-Fi and CEDS endpoints for student and grade data."},
        ],
    },
    "sdk": {
        "label": "SDK",
        "seo_title": "RunMyCampus SDK",
        "seo_description": "SDK and client libraries for RunMyCampus API.",
        "headline": "SDK",
        "subheadline": "Client libraries and auth helpers for API integration.",
        "sections": [
            {"title": "Repository", "body": "RunMyCampus SDK on GitHub: auth, base URL, and request helpers."},
            {"title": "Sandbox", "body": "Try the sandbox at /developer-portal/sandbox/ for app preview."},
        ],
    },
}

MARKETPLACE_PAGE_DEFINITIONS = {
    "": {
        "headline": "RunMyCampus Marketplace",
        "subheadline": "Apps and integrations to extend your platform.",
        "apps_copy": "Discover apps for admissions, academics, and operations.",
        "integrations_copy": "Connect LMS, payments, and identity providers.",
        "partners_copy": "Built with our partners for education.",
    },
    "apps": {"headline": "Marketplace apps", "subheadline": "Apps to extend RunMyCampus.", "apps_copy": "Browse and install apps.", "integrations_copy": "", "partners_copy": ""},
    "integrations": {"headline": "Integrations", "subheadline": "Connect your systems.", "apps_copy": "", "integrations_copy": "LMS, SIS, payments, messaging.", "partners_copy": ""},
    "partners": {"headline": "Partners", "subheadline": "Built with our partners.", "apps_copy": "", "integrations_copy": "", "partners_copy": "Partner solutions and certified integrations."},
}


@require_GET
def developer_marketing_page(request, section_slug: str):
    """Developer sub-pages: api, webhooks, integrations, sdk."""
    definition = DEVELOPER_PAGE_DEFINITIONS.get((section_slug or "").strip().lower())
    if not definition:
        raise Http404("Developer page not found")
    base_ctx = _marketing_base_context(request)
    canonical_path = f"/developers/{section_slug}/"
    canonical_url = _absolute_url(request, canonical_path)
    page_copy = deepcopy(definition)
    page_copy["slug"] = section_slug
    structured_data = _structured_data_for_page(
        page_type="WebPage",
        canonical_url=canonical_url,
        name=page_copy.get("label") or "RunMyCampus",
        description=page_copy.get("seo_description") or "",
        path=canonical_path,
    )
    ctx = {
        **base_ctx,
        "seo_title": page_copy.get("seo_title"),
        "seo_description": page_copy.get("seo_description"),
        "canonical_url": canonical_url,
        "structured_data_json": json.dumps(structured_data),
        "page": page_copy,
        "active_nav_slug": "solutions",
    }
    return render(request, "marketing/marketing_developer_page.html", ctx)


@require_GET
def marketplace_marketing_page(request, section: str = ""):
    """Marketplace landing and sections: apps, integrations, partners."""
    section_key = (section or "").strip().lower()
    definition = MARKETPLACE_PAGE_DEFINITIONS.get(section_key, MARKETPLACE_PAGE_DEFINITIONS.get(""))
    base_ctx = _marketing_base_context(request)
    if section_key:
        canonical_path = f"/marketplace/{section}/"
    else:
        canonical_path = "/marketplace/"
    canonical_url = _absolute_url(request, canonical_path)
    page_copy = deepcopy(definition)
    page_copy["slug"] = section_key
    structured_data = _structured_data_for_page(
        page_type="WebPage",
        canonical_url=canonical_url,
        name=page_copy.get("headline", "Marketplace"),
        description=page_copy.get("subheadline", "RunMyCampus Marketplace."),
        path=canonical_path,
    )
    ctx = {
        **base_ctx,
        "seo_title": f"{page_copy.get('headline', 'Marketplace')} | RunMyCampus",
        "seo_description": page_copy.get("subheadline", "RunMyCampus Marketplace."),
        "canonical_url": canonical_url,
        "structured_data_json": json.dumps(structured_data),
        "page": page_copy,
        "active_nav_slug": "solutions",
    }
    return render(request, "marketing/marketing_marketplace_page.html", ctx)


@require_GET
def regional_marketing_landing(request, country_code: str, language_code: str = "en"):
    """
    Regional landing page.
    Supported routes:
    - legacy: /cm/, /ca/
    - canonical: /<lang>/<country>/
    """
    normalized_country = _normalize_country_code(country_code)
    if not normalized_country:
        raise Http404("Region not found")
    ctx = _marketing_context(
        request,
        country_code=normalized_country,
        language_code=language_code or getattr(request, "LANGUAGE_CODE", "en"),
        regional=True,
    )
    return render(request, "schools/marketing_landing.html", ctx)


@require_GET
def marketing_robots_txt(request):
    lines = [
        "User-agent: *",
        "Allow: /",
        f"Sitemap: {_absolute_url(request, '/sitemap.xml')}",
    ]
    return HttpResponse("\n".join(lines) + "\n", content_type="text/plain")


def _sitemap_entries(request) -> list[tuple[str, str, str]]:
    """Return list of (loc, priority, changefreq) for marketing sitemap."""
    base = _absolute_url(request, "/").rstrip("/")
    path_specs: dict[str, tuple[str, str]] = {}  # path -> (priority, changefreq)

    path_specs["/"] = ("1.0", "weekly")
    for item in _marketing_nav():
        path = item["path"]
        if path in ("/pricing/", "/product/"):
            path_specs[path] = ("0.9", "weekly")
        else:
            path_specs[path] = ("0.8", "monthly")
    for item in _topical_nav():
        path_specs[item["path"]] = ("0.8", "monthly")
    path_specs["/discover/"] = ("0.8", "monthly")
    path_specs["/find/"] = ("0.8", "monthly")
    path_specs["/signup/"] = ("0.9", "weekly")
    path_specs["/book-demo/"] = ("0.9", "weekly")
    path_specs["/cookie-policy/"] = ("0.5", "monthly")
    # Phase 3–4: institution, role, migrate, compare, trust, developers, marketplace
    for inst in ("k12", "universities", "technical-schools", "private-schools", "government-education"):
        path_specs[f"/solutions/{inst}/"] = ("0.8", "monthly")
    for role in ("school-admin", "teachers", "parents", "students", "it-directors", "government"):
        path_specs[f"/roles/{role}/"] = ("0.8", "monthly")
    path_specs["/migrate/"] = ("0.8", "monthly")
    for src in ("from-power-school", "from-blackbaud", "from-infinite-campus"):
        path_specs[f"/migrate/{src}/"] = ("0.8", "monthly")
    for comp in ("power-school", "blackbaud", "infinite-campus"):
        path_specs[f"/compare/{comp}/"] = ("0.8", "monthly")
    for trust_path in ("/security/", "/compliance/", "/ferpa/", "/gdpr/", "/lgpd/"):
        path_specs[trust_path] = ("0.7", "monthly")
    for dev in ("api", "webhooks", "integrations", "sdk"):
        path_specs[f"/developers/{dev}/"] = ("0.7", "monthly")
    path_specs["/marketplace/"] = ("0.8", "monthly")
    path_specs["/marketplace/apps/"] = ("0.7", "monthly")
    path_specs["/marketplace/integrations/"] = ("0.7", "monthly")
    path_specs["/marketplace/partners/"] = ("0.7", "monthly")
    for prod in ("admissions", "academics", "finance", "communication", "automation", "analytics"):
        path_specs[f"/products/{prod}/"] = ("0.85", "monthly")
    for seo_slug in ("school-management-system", "student-information-system", "education-erp", "school-administration-software"):
        path_specs[f"/{seo_slug}/"] = ("0.85", "monthly")

    try:
        from apps.siteconfig.models import GlobalBrandRegistry

        countries = list(
            GlobalBrandRegistry.objects.filter(is_active=True)
            .values_list("iso_code", "primary_language")
            .order_by("iso_code")
        )
    except Exception:
        countries = []

    if not countries:
        countries = [("CM", "fr"), ("CA", "en"), ("US", "en")]

    for iso_code, language in countries:
        code = (iso_code or "").strip().lower()
        lang = _normalize_language_code(language or "en")
        if not code:
            continue
        path_specs[f"/{lang}/{code}/"] = ("0.7", "monthly")

    return [(base + (p if p != "/" else "/"), prio, freq) for p, (prio, freq) in path_specs.items()]


@require_GET
def marketing_sitemap_xml(request):
    """
    Lightweight sitemap for global marketing routes with priority and changefreq.
    """
    now = datetime.now(dt_timezone.utc).strftime("%Y-%m-%d")
    entries = _sitemap_entries(request)
    chunks = ["<?xml version=\"1.0\" encoding=\"UTF-8\"?>", "<urlset xmlns=\"http://www.sitemaps.org/schemas/sitemap/0.9\">"]
    for loc, priority, changefreq in entries:
        chunks.append("  <url>")
        chunks.append(f"    <loc>{loc}</loc>")
        chunks.append(f"    <lastmod>{now}</lastmod>")
        chunks.append(f"    <priority>{priority}</priority>")
        chunks.append(f"    <changefreq>{changefreq}</changefreq>")
        chunks.append("  </url>")
    chunks.append("</urlset>")
    return HttpResponse("\n".join(chunks), content_type="application/xml")


@require_GET
def developer_portal(request):
    """
    Developer portal (Section 6): API, webhooks, LTI/OneRoster, app lifecycle, SDK.
    Canonical on developer.runmycampus.com or /developer-portal/ on base.
    """
    base = get_canonical_base_domain() or request.get_host().split(":")[0]
    scheme = "https" if request.is_secure() else "http"
    # Interop and API schema live under tenant/school URL space; document paths.
    links = {
        "api_schema_path": "/api/schema/ui/",
        "api_schema_note": "Available after login at your school subdomain (e.g. yourschool.runmycampus.com/api/schema/ui/).",
        "interop_oneroster": request.build_absolute_uri("/api/interop/oneroster/"),
        "interop_lti13": request.build_absolute_uri("/api/interop/lti13/"),
        "interop_edfi": request.build_absolute_uri("/api/interop/edfi/"),
        "interop_ceds": request.build_absolute_uri("/api/interop/ceds/"),
        "webhooks_doc": f"{scheme}://docs.{base}/webhooks/" if base != "localhost" else request.build_absolute_uri("/docs/webhooks/"),
        "app_lifecycle_anchor": request.build_absolute_uri(reverse("developer_portal") + "#app-lifecycle"),
        "sandbox": request.build_absolute_uri(reverse("developer_sandbox")),
        "sdk_repo": "https://github.com/runmycampus/sdk",
    }
    base_ctx = _marketing_base_context(request)
    return render(request, "schools/developer_portal.html", {
        **base_ctx,
        "page_slug": "developer-portal",
        "headline": "Developer Portal",
        "subheadline": "APIs, webhooks, LTI, OneRoster, and app extensions.",
        "links": links,
    })


@require_GET
def developer_sdk(request):
    """
    SDK documentation page (Section 6): auth, base URL, and API reference pointers.
    """
    base = get_canonical_base_domain() or request.get_host().split(":")[0]
    scheme = "https" if request.is_secure() else "http"
    links = {
        "portal": request.build_absolute_uri(reverse("developer_portal")),
        "sandbox": request.build_absolute_uri(reverse("developer_sandbox")),
        "sdk_repo": "https://github.com/runmycampus/sdk",
        "api_schema_note": "After login at your school subdomain: /api/schema/ui/ for OpenAPI.",
        "auth_token": "POST /api/auth/token/ with username/password; use access token in Authorization: Bearer.",
        "auth_refresh": "POST /api/auth/token/refresh/ with refresh token.",
        "interop_edfi": "/api/interop/edfi/ (readiness); /api/interop/edfi/students/, .../studentSchoolAssociations/, .../grades/.",
        "interop_ceds": "/api/interop/ceds/ (readiness); /api/interop/ceds/students/, .../enrollments/, .../grades/.",
    }
    base_ctx = _marketing_base_context(request)
    return render(request, "schools/developer_sdk.html", {
        **base_ctx,
        "page_slug": "developer-sdk",
        "headline": "SDK & API reference",
        "subheadline": "Authentication, base URL, and API endpoints for RunMyCampus integrations.",
        "links": links,
    })


@require_GET
def developer_sandbox(request):
    """
    App sandbox (Section 6): iframe container with CSP for third-party app preview.
    Sandbox attribute restricts script/origin; placeholder content for now.
    """
    html = """<!DOCTYPE html><html><head><meta charset="utf-8"><title>Sandbox</title></head>
<body><p>App sandbox placeholder. Third-party apps run in an iframe with restricted permissions (CSP, sandbox attribute).</p></body></html>"""
    response = HttpResponse(html, content_type="text/html; charset=utf-8")
    response["Content-Security-Policy"] = "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; frame-ancestors 'self'"
    response["X-Frame-Options"] = "SAMEORIGIN"
    return response
