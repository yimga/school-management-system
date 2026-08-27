"""A box reachable by IP cannot use a named Caddy site block.

FOUND ON A LIVE BOX, not reasoned about at a desk. 10.10.20.137 had a healthy
terminator, a certificate that asserted 10.10.20.137, and `https://10.10.20.137/`
failed for every browser on the network:

    no SNI                 -> "no peer certificate available"
    SNI gilead-tech.local  -> subject=CN=gilead-tech.local
    SNI 10.10.20.137       -> subject=CN=gilead-tech.local
    curl https://10.10.20.137/  -> 000, handshake 0.000s

The TLS server_name extension carries DNS names only (RFC 6066), and every browser
omits it for an IP literal. A named site block is a host matcher with nothing to
match on, so Caddy presents NO certificate -- which FAILS the connection rather than
warning. There is no "proceed anyway" for a handshake that never produced a
certificate, so this is worse than the untrusted-CA warning it looks like.

The renderer already knew named blocks are host matchers. It only acted on that for
MOBILITY. Being reachable by IP is a different route to the same failure, and it
applies to a box bolted to a shelf that will never move -- which is most of them.

Everything here is a SimpleTestCase: rendering a config reads no database, and the
moment this matters is a box that has not finished coming up.
"""

from __future__ import annotations

from django.test import SimpleTestCase

from apps.schools import edge_tls

DIR = "/app/var/edge-tls"
CERT = f"{DIR}/tls.crt"
KEY = f"{DIR}/tls.key"


def _render(dns, ips, mode=edge_tls.MODE_SELF_SIGNED, **kwargs):
    kwargs.setdefault("cert_path", CERT)
    kwargs.setdefault("key_path", KEY)
    return edge_tls.caddyfile(mode, list(dns), list(ips), **kwargs)


def _site_line(text):
    for line in text.splitlines():
        stripped = line.strip()
        if stripped and not stripped.startswith("#"):
            return stripped
    return ""


class AnIpAddressCannotBeMatchedBySniTests(SimpleTestCase):
    def test_a_certificate_that_covers_an_ip_gets_a_catch_all_site(self):
        # The exact shape the live box had.
        rendered = _render(
            ["gilead-tech.local", "gilead-tech.school.lan", "schoolmanagement", "localhost"],
            ["10.10.20.137", "127.0.0.1"],
        )
        self.assertEqual(_site_line(rendered), ":443 {")

    def test_one_ip_is_enough(self):
        self.assertEqual(_site_line(_render(["box.school.lan"], ["10.0.0.9"])), ":443 {")

    def test_names_only_is_left_alone(self):
        # Nothing is broken for a name-only box, and widening it anyway would be a
        # change made for symmetry rather than for a reason.
        rendered = _render(["gilead-tech.local", "gilead-tech.school.lan"], [])
        self.assertEqual(
            _site_line(rendered), "gilead-tech.local, gilead-tech.school.lan {"
        )

    def test_the_key_pair_is_still_what_is_served(self):
        # A catch-all that quietly fell back to `tls internal` would serve Caddy's own
        # CA -- so the ca.crt walked round the building matches nothing the box
        # presents, and no error anywhere mentions it.
        rendered = _render(["box.school.lan"], ["10.0.0.9"])
        self.assertIn(f"tls {CERT} {KEY}", rendered)
        self.assertNotIn("tls internal", rendered)

    def test_port_80_does_not_go_dead(self):
        # Caddy adds an automatic HTTP->HTTPS redirect for a NAMED site and not for
        # `:443`. Switching to the catch-all without this would silently kill port 80.
        rendered = _render(["box.school.lan"], ["10.0.0.9"])
        self.assertIn(":80 {", rendered)
        self.assertIn("redir https://{host}{uri} 302", rendered)
        # Comments stripped first. The block explains "302 and never 301", so
        # asserting against the raw text catches the reasoning rather than the
        # directive -- a test that fails for being well documented.
        directives = [
            line for line in rendered.splitlines() if not line.strip().startswith("#")
        ]
        self.assertNotIn("301", "\n".join(directives))

    def test_the_reason_is_written_down_where_the_next_person_will_look(self):
        # Without this, `:443` reads as sloppiness and gets "tidied" back into a name
        # list by somebody being helpful -- and the box loses https-by-IP again with
        # nothing to explain why.
        rendered = _render(["box.school.lan"], ["10.0.0.9"])
        self.assertIn("SNI", rendered)
        self.assertIn("IP literal", rendered)

    def test_the_names_are_still_recorded_even_though_they_are_not_matched(self):
        rendered = _render(["box.school.lan"], ["10.0.0.9"])
        self.assertIn("box.school.lan", rendered)
        self.assertIn("10.0.0.9", rendered)


class WhereTheCatchAllWouldNotHelpTests(SimpleTestCase):
    """It is applied for a reason, so it must not be applied where the reason is absent."""

    def test_acme_keeps_its_named_block(self):
        # ACME needs the named form for its own HTTP challenge, and a public CA cannot
        # issue for a private IP at all (see publicly_issuable) -- so a catch-all here
        # would break issuance to fix nothing.
        rendered = edge_tls.caddyfile(
            edge_tls.MODE_ACME, ["school.example.com"], ["10.0.0.5"], acme_email="a@b.c"
        )
        self.assertEqual(_site_line(rendered), "school.example.com, 10.0.0.5 {")

    def test_tls_internal_keeps_its_named_block(self):
        # With no key pair Caddy issues per SNI, which is exactly what a no-SNI client
        # cannot drive. A catch-all would not rescue the IP case and would lose the
        # names Caddy needs in order to issue anything.
        rendered = edge_tls.caddyfile(
            edge_tls.MODE_SELF_SIGNED, ["box.school.lan"], ["10.0.0.9"]
        )
        self.assertIn("tls internal", rendered)
        self.assertEqual(_site_line(rendered), "box.school.lan, 10.0.0.9 {")

    def test_mode_off_renders_no_site_at_all(self):
        rendered = edge_tls.caddyfile(edge_tls.MODE_OFF, ["box.school.lan"], ["10.0.0.9"])
        self.assertNotIn(":443", rendered)


class TheMobilityRouteStillWorksTests(SimpleTestCase):
    """The pre-existing reason for a catch-all must survive gaining a second one."""

    def test_a_moving_box_still_gets_the_catch_all(self):
        rendered = _render(["box.school.lan"], [], address_may_change=True)
        self.assertEqual(_site_line(rendered), ":443 {")

    def test_a_moving_box_keeps_its_own_explanation(self):
        # Two different reasons, two different things to tell the reader. A box that
        # moves needs to know its address is deliberately not pinned; a static box
        # with an IP needs to know about SNI.
        rendered = _render(["box.school.lan"], [], address_may_change=True)
        self.assertIn("deliberately NOT pinned", rendered)

    def test_a_moving_box_with_no_key_pair_is_still_refused(self):
        with self.assertRaises(ValueError):
            edge_tls.caddyfile(
                edge_tls.MODE_SELF_SIGNED, ["box.school.lan"], [], address_may_change=True
            )

    def test_both_reasons_at_once_produce_one_catch_all_and_one_redirect(self):
        rendered = _render(["box.school.lan"], ["10.0.0.9"], address_may_change=True)
        self.assertEqual(_site_line(rendered), ":443 {")
        self.assertEqual(rendered.count(":80 {"), 1)
class ThePortEightyRedirectMustNotBounceTheTrustPageTests(SimpleTestCase):
    """MEASURED on the live box, and the bug was in the fix for the previous bug.

        http://10.10.20.137/edge/trust/       -> 302 -> https://10.10.20.137/edge/trust/
        http://10.10.20.137/edge/trust/ca.crt -> 302 -> https://...
        http://10.10.20.137:10000/edge/trust/ -> 200

    Django exempts `^edge/trust/` in SECURE_REDIRECT_EXEMPT and says why: a device
    opens that page BECAUSE it does not trust this box, so redirecting it to HTTPS
    shows the very warning it came to fix. The `:80` block added for the catch-all
    site undid that one layer above Django -- and neither layer is wrong alone, which
    is why nothing caught it.
    """

    def _eighty(self, rendered):
        """The :80 block, comments stripped."""
        out, inside = [], False
        for line in rendered.splitlines():
            if line.startswith(":80 {"):
                inside = True
            if inside and not line.strip().startswith("#"):
                out.append(line)
            if inside and line == "}":
                inside = False
        return "\n".join(out)

    def test_the_trust_page_is_served_not_redirected(self):
        block = self._eighty(_render(["box.school.lan"], ["10.0.0.9"]))
        self.assertIn("handle @trust {", block)
        self.assertIn("reverse_proxy web:10000", block)

    def test_the_no_slash_form_is_matched_too(self):
        # People type the address off a sticker and leave the slash off. That form
        # would fall through to the redirect and land on the warning -- and Django
        # never gets the chance to APPEND_SLASH it, because it never sees it.
        block = self._eighty(_render(["box.school.lan"], ["10.0.0.9"]))
        self.assertIn("@trust path /edge/trust /edge/trust/*", block)

    def test_everything_that_is_not_the_trust_page_still_goes_to_https(self):
        block = self._eighty(_render(["box.school.lan"], ["10.0.0.9"]))
        self.assertIn("handle {", block)
        self.assertIn("redir https://{host}{uri} 302", block)

    def test_it_uses_handle_blocks_and_not_a_bare_redir(self):
        # Caddy orders directives by its OWN table, not by source order, and `redir`
        # sorts BEFORE `reverse_proxy`. So the obvious spelling -- a matcher-scoped
        # reverse_proxy sitting beside an unscoped redir -- still redirects the trust
        # page, and looks completely correct while doing it. `handle` blocks are
        # mutually exclusive and run in written order, which is the property we need.
        block = self._eighty(_render(["box.school.lan"], ["10.0.0.9"]))
        # Two handle blocks: the trust one and the catch-all. The @trust line above
        # them DEFINES the matcher and is not itself a handler.
        self.assertEqual(block.count("handle"), 2)
        self.assertIn("handle @trust {", block)
        self.assertIn("handle {", block)
        for line in block.splitlines():
            if line.strip().startswith("redir "):
                self.assertIn("\t\t", line, "redir must be INSIDE a handle block")

    def test_the_proxied_trust_page_still_declares_the_real_scheme(self):
        # X-Forwarded-Proto must say `http` here, because that is true. If it claimed
        # https, Django would consider the request secure, SECURE_REDIRECT_EXEMPT
        # would never be consulted, and the page would work for the wrong reason --
        # until something else depended on is_secure() being honest.
        block = self._eighty(_render(["box.school.lan"], ["10.0.0.9"]))
        self.assertIn("header_up X-Forwarded-Proto {scheme}", block)

    def test_django_and_caddy_agree_on_the_prefix(self):
        # The two layers spell this path in two places on purpose: Django's list has
        # to be total even on a checkout where edge_tls fails to import, and an
        # exemption that silently disappears has no symptom. So pin them together --
        # this is the test that makes two spellings safe.
        from django.conf import settings

        expected = "^" + edge_tls.TRUST_PATH.lstrip("/") + "/"
        self.assertIn(
            expected,
            list(settings.SECURE_REDIRECT_EXEMPT),
            "Caddy exempts %s but Django's SECURE_REDIRECT_EXEMPT does not carry %r"
            % (edge_tls.TRUST_PATH, expected),
        )

    def test_acme_gets_no_port_80_block_of_ours(self):
        # ACME proves control over :80. An explicit block of ours sitting on top of
        # the HTTP-01 challenge would break issuance -- and a publicly trusted
        # certificate needs no trust page at all, so there is nothing to exempt.
        rendered = edge_tls.caddyfile(
            edge_tls.MODE_ACME, ["school.example.com"], [], acme_email="a@b.c"
        )
        self.assertNotIn(":80 {", rendered)

    def test_a_name_only_box_is_a_KNOWN_GAP_and_is_recorded_as_one(self):
        # Not fixed, and deliberately not papered over. A box whose certificate names
        # no IP takes the NAMED branch, gets no `:80` block from us, and Caddy adds
        # its own automatic HTTP->HTTPS redirect for that host -- which bounces the
        # trust page exactly as ours did.
        #
        # The fix is not obviously "emit the block anyway": Caddy composes an explicit
        # `:80` catch-all with its own host-matched auto-redirect route, and which one
        # wins is a route-precedence question this suite cannot answer by rendering
        # text. It needs a running Caddy. Asserting the CURRENT behaviour means the
        # day somebody changes it, they are told, instead of this comment quietly
        # becoming untrue.
        rendered = _render(["box.school.lan"], [])
        self.assertNotIn(":80 {", rendered)
        self.assertEqual(_site_line(rendered), "box.school.lan {")
