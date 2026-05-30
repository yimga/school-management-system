"""v4.00.87 Wave 19 T5 — DLQ operator HTML UI smoke.

Wave 12 T4 (v4.00.80) shipped ``WebhookDeadLetterListView`` returning
JSON for operator triage of webhook dead-letter rows. This target adds a
human-readable HTML response surface gated on ``?format=html``; the
default JSON shape is unchanged.

Cases:

  1. GET ``/super/migration/operator/dlq/?format=html`` (staff) -> 200
     + ``Content-Type: text/html``.
  2. HTML body contains the page title text.
  3. HTML body contains a ``<table>`` OR the empty-state marker
     ``data-rmc-dlq-empty`` (the queue may be empty on the dev DB).
  4. ``data-rmc-dlq-row-count`` attribute is present in the HTML.
  5. ``?format=html&status=replayed`` applies the filter (status pill
     marker appears OR empty-state marker appears).
  6. The HTML body NEVER contains ``payload_b64`` substring.
  7. The HTML body NEVER contains ``tenant_schema`` substring.
  8. Default ``?format=`` unset still returns JSON (no regression).
  9. Anonymous user GET ``?format=html`` -> 302 (staff gate).
 10. The ``migration_cloud_dlq_replay`` URL name resolves via reverse().

We invoke the view directly via ``RequestFactory`` (mirroring the Wave
12 T4 smoke) so we side-step the production middleware stack. The
``@method_decorator(staff_member_required, name="dispatch")`` gate IS
exercised regardless.
"""

import os
import sys

# Use the dev DB (config.settings) — same rationale as the Wave 12 T4
# smoke: config.settings_test in-memory SQLite costs ~5min on Windows
# spinning up 845 migrations.
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

_HERE = os.path.dirname(os.path.abspath(__file__))
_PROJECT_ROOT = os.path.dirname(_HERE)
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

import django  # noqa: E402

django.setup()

import json  # noqa: E402

from django.contrib.auth import get_user_model  # noqa: E402
from django.contrib.auth.models import AnonymousUser  # noqa: E402
from django.test import RequestFactory  # noqa: E402
from django.urls import reverse  # noqa: E402


User = get_user_model()


CASES = 0


def _ok(label):
    global CASES
    CASES += 1
    print(f"[OK {CASES:02d}] {label}")


print("=" * 70)
print("v4.00.87 Wave 19 T5 — DLQ operator HTML UI smoke")
print("=" * 70)


# --------------------------------------------------------------------------
# Fixture: a pending DLQ row + a staff user (so the pending HTML page has
# at least one row to assert the <table> / replay button surface).
# --------------------------------------------------------------------------
from apps.integrations_marketplace import webhook_dead_letter as dlq  # noqa: E402
from apps.integrations_marketplace.models import WebhookDeadLetter  # noqa: E402
from apps.migration_cloud.views_dlq_admin import (  # noqa: E402
    WebhookDeadLetterListView,
)


# Clean up prior smoke fixtures.
WebhookDeadLetter.objects.filter(
    provider="test-htmlui", event_type="grade.pushed",
).delete()


row = dlq.enqueue_dead_letter(
    provider="test-htmlui",
    event_type="grade.pushed",
    payload=b'{"k":"v"}',
    reason="http_504",
)
assert row is not None, "enqueue_dead_letter returned None"
assert row.status == "pending", row.status
dlq_id = row.pk


staff, _ = User.objects.get_or_create(
    username="dlq-htmlui-smoke-staff",
    defaults={"is_staff": True},
)
if not staff.is_staff:
    staff.is_staff = True
    staff.save(update_fields=["is_staff"])


rf = RequestFactory()
view = WebhookDeadLetterListView.as_view()


# --------------------------------------------------------------------------
# Case 1: GET ?format=html (staff) -> 200 + text/html.
# --------------------------------------------------------------------------
req = rf.get("/super/migration/operator/dlq/?format=html")
req.user = staff
resp = view(req, shell="super")
assert resp.status_code == 200, (resp.status_code, resp.content[:300])
content_type = resp.get("Content-Type", "") or resp.headers.get("Content-Type", "")
assert content_type.startswith("text/html"), content_type
_ok(f"GET ?format=html (staff) -> 200 + Content-Type={content_type}")


# --------------------------------------------------------------------------
# Case 2: HTML body contains the page title text.
# --------------------------------------------------------------------------
html = resp.content.decode("utf-8")
assert "Webhook Dead Letter Queue" in html, (
    "page title 'Webhook Dead Letter Queue' missing from HTML body"
)
_ok("HTML body contains the 'Webhook Dead Letter Queue' title")


# --------------------------------------------------------------------------
# Case 3: HTML contains a <table> OR the empty-state marker.
# --------------------------------------------------------------------------
has_table = "<table" in html
has_empty = "data-rmc-dlq-empty" in html
assert has_table or has_empty, (
    "neither <table> nor data-rmc-dlq-empty present in HTML body"
)
_ok(
    "HTML body has <table>"
    + (f" (rows>=1, dlq_id={dlq_id} visible: {str(dlq_id) in html})" if has_table
       else " OR empty-state marker")
)


# --------------------------------------------------------------------------
# Case 4: data-rmc-dlq-row-count attribute present.
# --------------------------------------------------------------------------
assert "data-rmc-dlq-row-count" in html, (
    "data-rmc-dlq-row-count attribute missing from HTML body"
)
_ok("data-rmc-dlq-row-count attribute present")


# --------------------------------------------------------------------------
# Case 5: ?status=replayed filter is applied.
# --------------------------------------------------------------------------
req = rf.get("/super/migration/operator/dlq/?format=html&status=replayed")
req.user = staff
resp_replayed = view(req, shell="super")
assert resp_replayed.status_code == 200, resp_replayed.status_code
html_replayed = resp_replayed.content.decode("utf-8")
# The filter is reflected either by the active segment marker OR by the
# status pill in the table OR (if no replayed rows exist) by the empty
# state copy mentioning "replayed".
assert (
    'data-rmc-dlq-segment="replayed"' in html_replayed
    and 'is-active' in html_replayed
), "replayed segment is not marked active in the filter nav"
# Sanity: status filter context echoed somewhere in the body.
assert "replayed" in html_replayed, "filter status 'replayed' missing from body"
_ok("?format=html&status=replayed -> replayed segment active in nav")


# --------------------------------------------------------------------------
# Case 6: HTML body NEVER contains 'payload_b64' (defense-in-depth).
# --------------------------------------------------------------------------
assert "payload_b64" not in html, "payload_b64 leaked into HTML body"
assert "payload_b64" not in html_replayed, (
    "payload_b64 leaked into replayed-filter HTML body"
)
_ok("HTML body never contains 'payload_b64' (defense-in-depth)")


# --------------------------------------------------------------------------
# Case 7: HTML body NEVER contains 'tenant_schema' (defense-in-depth).
# --------------------------------------------------------------------------
assert "tenant_schema" not in html, "tenant_schema leaked into HTML body"
assert "tenant_schema" not in html_replayed, (
    "tenant_schema leaked into replayed-filter HTML body"
)
_ok("HTML body never contains 'tenant_schema' (defense-in-depth)")


# --------------------------------------------------------------------------
# Case 8: Default GET (no ?format=) still returns JSON. Regression guard.
# --------------------------------------------------------------------------
req = rf.get("/super/migration/operator/dlq/")
req.user = staff
resp_json = view(req, shell="super")
assert resp_json.status_code == 200, resp_json.status_code
ct_json = resp_json.get("Content-Type", "") or resp_json.headers.get("Content-Type", "")
assert ct_json.startswith("application/json"), (
    f"default GET regressed Content-Type to {ct_json}"
)
body = json.loads(resp_json.content)
assert "rows" in body and "count" in body and "status_filter" in body, body
_ok(f"default GET (no ?format=) still returns JSON (Content-Type={ct_json})")


# --------------------------------------------------------------------------
# Case 9: Anonymous user hitting ?format=html -> 302 (staff_member_required).
# --------------------------------------------------------------------------
req = rf.get("/super/migration/operator/dlq/?format=html")
req.user = AnonymousUser()
resp_anon = view(req, shell="super")
assert resp_anon.status_code in (302, 403), (
    resp_anon.status_code, resp_anon.content[:200]
)
_ok(f"anonymous GET ?format=html -> {resp_anon.status_code} (staff gate fired)")


# --------------------------------------------------------------------------
# Case 10: reverse() resolves the replay URL name (referenced in template).
# --------------------------------------------------------------------------
replay_url = reverse(
    "migration_cloud_super:migration_cloud_dlq_replay",
    kwargs={"dlq_id": dlq_id},
)
assert "/operator/dlq/" in replay_url and "/replay/" in replay_url, replay_url
assert str(dlq_id) in replay_url, replay_url
_ok(f"reverse('migration_cloud_super:migration_cloud_dlq_replay') -> {replay_url}")


# Cleanup smoke fixtures.
WebhookDeadLetter.objects.filter(
    provider="test-htmlui",
    event_type="grade.pushed",
    pk=dlq_id,
).delete()


print("=" * 70)
print(f"v4.00.87 Wave 19 T5 — DLQ operator HTML UI smoke OK ({CASES}/{CASES} cases)")
print("=" * 70)
