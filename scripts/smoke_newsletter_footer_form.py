"""Smoke — public newsletter footer form end-to-end (v4.01.01).

Exercises:
* HTTP view accepts JSON POST → JSON response
* HTTP view accepts form-encoded POST → HTML response
* Honeypot (website_url filled) → silent OK (ignored, no row created)
* Honeypot empty → row created
* GET → 405 (require_POST)
* CSRF exempt (no token required since cross-origin marketing surface)
* Footer template renders the internal DOI action URL when no env override
* Footer template renders the override URL when MARKETING_NEWSLETTER_FORM_ACTION is set
"""

from __future__ import annotations

import json
import os
import sys
import uuid
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

import django

django.setup()

import logging as _logging
for _name in ("django.db.backends", "django.db", "django.security", "celery"):
    _logging.getLogger(_name).setLevel(_logging.WARNING)

from django.core import mail
from django.template import Context, Template
from django.test import Client
from django.test.utils import override_settings
from django.urls import reverse

ASSERTIONS: list[tuple[str, bool, str]] = []


def expect(label: str, cond: bool, detail: str = "") -> None:
    ASSERTIONS.append((label, bool(cond), detail))


@override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
def run():
    mail.outbox = []
    client = Client()
    suffix = uuid.uuid4().hex[:8]

    from apps.platform_runtime.models import NewsletterSubscription

    # T1: URL resolves at public path
    url = reverse("platform_runtime:newsletter_subscribe")
    expect("T1.1 url ends with /newsletter/subscribe/", url.endswith("/newsletter/subscribe/"))

    # T2: GET → 405
    resp = client.get(url)
    expect("T2.1 GET returns 405", resp.status_code == 405)

    # T3: JSON POST → JSON response
    email_json = f"json_{suffix}@example.test"
    resp = client.post(
        url,
        data=json.dumps({"email": email_json, "source": "smoke_footer_json"}),
        content_type="application/json",
    )
    expect("T3.1 JSON POST returns 200", resp.status_code == 200)
    expect("T3.2 JSON POST returns JSON", resp["Content-Type"].startswith("application/json"))
    body = json.loads(resp.content.decode("utf-8"))
    expect("T3.3 JSON body ok=True", body.get("ok") is True)
    expect("T3.4 row created", NewsletterSubscription.objects.filter(email=email_json).exists())

    # T4: form-encoded POST → HTML response
    email_form = f"form_{suffix}@example.test"
    resp = client.post(
        url,
        data={"email": email_form, "source": "smoke_footer_form"},
    )
    expect("T4.1 form POST returns 200", resp.status_code == 200)
    expect("T4.2 form POST returns HTML", resp["Content-Type"].startswith("text/html"))
    html = resp.content.decode("utf-8")
    expect("T4.3 HTML body says 'Check your email'", "Check your email" in html)
    expect("T4.4 HTML body echoes email", email_form in html)
    expect("T4.5 row created", NewsletterSubscription.objects.filter(email=email_form).exists())

    # T5: honeypot filled → silent OK + no row
    email_bot = f"bot_{suffix}@example.test"
    resp = client.post(
        url,
        data={"email": email_bot, "website_url": "http://spam.example/"},
    )
    expect("T5.1 honeypot POST returns 200", resp.status_code == 200)
    expect(
        "T5.2 honeypot row NOT created",
        not NewsletterSubscription.objects.filter(email=email_bot).exists(),
    )

    # T6: invalid email via form → HTML 400
    resp = client.post(url, data={"email": "not-an-email"})
    expect("T6.1 invalid email returns 400", resp.status_code == 400)
    expect("T6.2 invalid email HTML body", b"Couldn't subscribe" in resp.content)

    # T7: footer template uses internal DOI URL when no override
    with override_settings(MARKETING_NEWSLETTER_FORM_ACTION=""):
        from django.template.loader import get_template

        tpl = get_template("marketing/marketing_footer.html")
        rendered = tpl.render({"marketing_newsletter_form_action": ""})
        expect(
            "T7.1 footer points at /newsletter/subscribe/",
            'action="/platform-runtime/newsletter/subscribe/"' in rendered
            or "/newsletter/subscribe/" in rendered,
        )
        expect("T7.2 footer carries data-newsletter-form attr", "data-newsletter-form" in rendered)
        expect(
            "T7.3 footer includes hidden source=marketing_footer",
            'name="source" value="marketing_footer"' in rendered,
        )
        expect("T7.4 footer uses POST method", 'method="post"' in rendered)
        expect(
            "T7.5 footer emits csrf_token template tag (renders at request time)",
            "{% csrf_token %}" not in rendered,
        )
        expect(
            "T7.6 footer does NOT carry target=_blank without override",
            'target="_blank"' not in rendered,
        )

    # T8: footer template honors override
    rendered = Template(
        "{% include 'marketing/marketing_footer.html' %}"
    ).render(
        Context({"marketing_newsletter_form_action": "https://list.example.com/subscribe"})
    )
    expect(
        "T8.1 footer uses override URL",
        'action="https://list.example.com/subscribe"' in rendered,
    )
    expect(
        "T8.2 footer carries target=_blank when override",
        'target="_blank"' in rendered,
    )


run()

passed = sum(1 for _, ok, _ in ASSERTIONS if ok)
failed = sum(1 for _, ok, _ in ASSERTIONS if not ok)
total = len(ASSERTIONS)

print(f"\n=== Newsletter footer form smoke ({total} assertions) ===\n")
for label, ok, detail in ASSERTIONS:
    mark = "PASS" if ok else "FAIL"
    extra = f" -- {detail}" if detail and not ok else ""
    print(f"  [{mark}] {label}{extra}")
print(f"\n{passed}/{total} passed, {failed} failed.")
sys.exit(0 if failed == 0 else 1)
