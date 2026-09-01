"""Render a SHELL for real, with no database, so a test can read its output.

WHY
---
A test that reads ``portal_base.html`` and asserts a substring cannot tell markup
that renders from markup that has been moved inside ``{% comment %}``: the bytes
are identical and the page is not. Measured on 2026-08-31, 18 of 27 measurable
tests of that shape were VACUOUS -- they still passed with the template they name
rendering nothing (``scripts/verify_test_asserts_behaviour.py``).

The reason those tests read source instead of output is that a shell looks
expensive to render: ``render_to_string("base.html", {})`` raises
``VariableDoesNotExist: SITE``, because the shells depend on context processors
and context processors need a request. They do NOT need a database -- as long as
the user is anonymous. That is the whole trick, and it is what this module packages.

    render_shell("portal_base.html", urlconf=TENANT) -> 54,781 bytes, no DB

WHAT IT CANNOT DO, AND WHY THAT IS NOT A GAP YOU CAN PAPER OVER
---------------------------------------------------------------
An AUTHENTICATED user pulls a context processor into the ORM
(``TypeError: Field 'id' expected a number``), so authenticated-only chrome --
the operator tools tray, the nav-sidebar script, the form-draft bundle -- cannot
be reached from a ``SimpleTestCase``. A test for that chrome needs a real user and
therefore ``TestCase``. Do not fake it with a stub user: the stub is what raises.
"""

from __future__ import annotations

from django.contrib.auth.models import AnonymousUser
from django.test import RequestFactory
from django.template.loader import render_to_string
from django.urls import get_urlconf, set_urlconf

BASE_URLCONF = "config.urls"
TENANT_URLCONF = "config.tenant_urls"
MANAGER_URLCONF = "config.manager_urls"
PUBLIC_URLCONF = "config.public_urls"


def render_shell(
    template: str,
    *,
    urlconf: str = BASE_URLCONF,
    host_kind: str = "tenant",
    path: str = "/",
    **context: object,
) -> str:
    """Render ``template`` through the real context processors. No database.

    ``urlconf`` and ``host_kind`` are BOTH set because the shells branch on them
    independently: ``request.urlconf`` decides what ``{% url %}`` can reverse, and
    ``request.public_host_kind`` decides which host-guarded branch is taken. A test
    that sets only one of them is asserting about a host that does not exist.
    """
    request = RequestFactory().get(path)
    request.urlconf = urlconf
    request.user = AnonymousUser()
    request.public_host_kind = host_kind
    request.is_tenant_host = host_kind == "tenant"
    previous = get_urlconf()
    set_urlconf(urlconf)
    try:
        return render_to_string(template, context, request=request)
    finally:
        set_urlconf(previous)
