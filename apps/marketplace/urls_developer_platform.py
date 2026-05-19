"""URL routes for Move 1 developer-platform surfaces.

Mounted at:
  - public  : /marketplace/...   (config/urls.py)
  - tenant  : /marketplace/...   (config/tenant_urls.py)
  - control : /super/marketplace/...   (config/manager_urls.py)
"""

from django.urls import path

from apps.marketplace import views_developer_platform as v


app_name = "marketplace_dev"


public_urlpatterns = [
    path("apps/<slug:slug>/", v.public_app_detail, name="public_app_detail"),
    path("apps/<slug:slug>/rate/", v.submit_rating_view, name="submit_rating"),
    # rbac-allow: public marketplace catalog JSON for developer platform discovery
    path("api/v1/catalog/", v.public_app_catalog_api, name="public_app_catalog_api"),
    # rbac-allow: publisher self-signup onboarding (email verification follows)
    path("publisher/signup/", v.publisher_signup_view, name="publisher_signup"),
    # rbac-allow: email verification link from publisher signup mail
    path("publisher/verify-email/", v.verify_email_view, name="verify_email"),
]


operator_urlpatterns = [
    path("signups/", v.signup_review_queue, name="signup_review_queue"),
    path("signups/<int:signup_id>/decide/", v.signup_decide, name="signup_decide"),
    path(
        "publisher/metrics.json",
        v.partner_dashboard_metrics,
        name="partner_dashboard_metrics",
    ),
    path(
        "publisher/webhooks/",
        v.publisher_webhook_log,
        name="publisher_webhook_log",
    ),
    # Publisher self-serve CRUD for their app's webhook endpoints + versions.
    path("publisher/apps/<slug:app_slug>/webhooks/", v.webhook_endpoints_view, name="webhook_endpoints"),
    path(
        "publisher/apps/<slug:app_slug>/webhooks/<int:endpoint_id>/edit/",
        v.webhook_endpoint_edit_view,
        name="webhook_endpoint_edit",
    ),
    path("publisher/apps/<slug:app_slug>/versions/", v.app_versions_view, name="app_versions"),
    path("ratings/<int:rating_id>/reply/", v.publisher_reply_view, name="publisher_reply"),
]


urlpatterns = public_urlpatterns + operator_urlpatterns
