"""A person's name has no shape, so nothing was stopping one leaving.

The PII layer matches value SHAPES — an email, a phone number, a date. That is
why `{"full_name": "Ngwa Divine Ache"}` passed straight through BOTH controls:
`contains_hard_pii` saw nothing to match, so the external tier was allowed, and
`redact_for_external_inference` had nothing to substitute, so the name went to
the third-party model verbatim. The literal-value scrub in that redactor only
covers record values supplied in `metadata`, and the callers that serialise a
record into the PROMPT do not supply them.

A name reached the wire whenever the record carried no email, phone or date
beside it — a staff roster, a class list, a sections file.

What a name does have is a LABEL. Every realistic leak here is a serialised
record, and the field it sits under says exactly what it is. Matching the label
and replacing the value catches names without guessing which capitalised words
in prose are people — the guess that would make this gate fire on
"Applied Mechanics" and get itself switched off.

Registered as a HARD pattern, so it does both jobs at once: the payload is
refused the external tier AND the value is scrubbed if anything still goes out.

Audited when this landed: nine call sites platform-wide declare an allowlisted
`sensitivity_class`, and every one is a bounded projection of aggregates, enums
or the tenant's own name — none could reach a student. This closes the class,
not an active leak. `content_sensitivity` does NOT map to `sensitivity_class`,
so `run_ai_prompt` / `invoke_task` callers are denied the external tier anyway.

DB-free.
"""

from django.test import SimpleTestCase, override_settings

from services.inference import (
    contains_hard_pii,
    redact_for_external_inference,
)


class TheGapThisClosesTests(SimpleTestCase):
    """A name with no email, phone or date beside it."""

    LEAKS = (
        "{'full_name': 'Ngwa Divine Ache', 'class': 'Form 5A'}",
        '"student_name": "Tabi Ruth", "gender": "F"',
        "guardian = Mrs Ache Bernadette",
        "- surname: Mensah",
        "{'parent_contact': 'Kwabena Mensah'}",
        "next_of_kin: Bernadette Ache",
    )

    def test_a_labelled_name_is_refused_the_external_tier(self):
        for payload in self.LEAKS:
            with self.subTest(payload=payload):
                self.assertTrue(
                    contains_hard_pii(payload),
                    "a labelled personal field must deny the external tier",
                )

    def test_a_labelled_name_is_scrubbed_before_transport(self):
        for payload, token in (
            (self.LEAKS[0], "Ngwa"),
            (self.LEAKS[1], "Tabi"),
            (self.LEAKS[2], "Bernadette"),
            (self.LEAKS[3], "Mensah"),
        ):
            with self.subTest(payload=payload):
                out = redact_for_external_inference(payload)
                self.assertNotIn(token, out)
                self.assertIn("[redacted]", out)

    def test_the_label_survives_because_the_label_is_schema(self):
        # The migration classifier reads column NAMES to decide a domain. The
        # value is what identifies a child; the label is what identifies a
        # column. Scrubbing both would blind the feature this protects.
        out = redact_for_external_inference("{'full_name': 'Ngwa Divine Ache'}")
        self.assertIn("full_name", out)

    def test_redaction_is_idempotent(self):
        once = redact_for_external_inference("{'full_name': 'Ngwa Divine Ache'}")
        self.assertEqual(redact_for_external_inference(once), once)

    def test_an_already_redacted_payload_no_longer_denies(self):
        # Once nothing personal remains, the payload may go. Otherwise the
        # redactor's own output would be permanently un-sendable.
        self.assertFalse(contains_hard_pii("{'full_name': [redacted]}"))


class LegitimatePromptsMustStillReachTheModelTests(SimpleTestCase):
    """A gate that refuses true statements gets switched off.

    These are the real prompt shapes of the nine call sites that declare an
    allowlisted sensitivity class. Every one must stay allowed.
    """

    ALLOWED = (
        "{'score': 72, 'status': 'green', 'onboarding_percent': 40, 'student_count': 812}",
        "{'percent': 55}",
        "for a school named roughly: 'Gilead Technical High School'",
        "{'country': 'CM', 'primary_language': 'fr', 'connectivity_profile': 'low'}",
        "Health score ~72. Dominant task: Configure grading scale.",
        "{'status': 'amber', 'score': 61, 'has_report_schedules': True}",
        "seed_hex #4F46E5 mode=vivid tone=calm",
    )

    def test_none_of_them_are_refused(self):
        for prompt in self.ALLOWED:
            with self.subTest(prompt=prompt):
                self.assertFalse(
                    contains_hard_pii(prompt),
                    "an aggregate-only prompt must still reach the model",
                )

    def test_none_of_them_are_altered(self):
        for prompt in self.ALLOWED:
            with self.subTest(prompt=prompt):
                self.assertEqual(redact_for_external_inference(prompt), prompt.strip())


class ThingsNamedAfterThingsAreNotPeopleTests(SimpleTestCase):
    """`subject_name` is a subject. The exempt vocabulary already knew that."""

    NOT_PEOPLE = (
        "{'subject_name': 'Applied Mechanics'}",
        "{'school_name': 'Gilead Technical High School'}",
        "{'course_name': 'Plumbing', 'term_name': 'Term 2'}",
        "{'file_name': 'subjects_2026.xlsx'}",
        "{'column_name': 'title', 'table_name': 'sections'}",
        "{'role_name': 'BURSAR', 'plan_name': 'Standard'}",
    )

    def test_they_are_neither_refused_nor_scrubbed(self):
        for payload in self.NOT_PEOPLE:
            with self.subTest(payload=payload):
                self.assertFalse(contains_hard_pii(payload))
                self.assertNotIn("[redacted]", redact_for_external_inference(payload))

    def test_the_exempt_list_is_the_single_source_of_that_judgement(self):
        # Reusing the platform vocabulary rather than a second private list is
        # the point: one list cannot drift against itself.
        from services.inference import pii_metadata_exempt_fields, pii_metadata_fields

        self.assertIn("subject_name", pii_metadata_exempt_fields())
        self.assertIn("name", pii_metadata_fields())

    @override_settings(AI_PII_METADATA_FIELDS_EXEMPT=("mascot_name",))
    def test_a_deployment_can_extend_the_exemptions(self):
        self.assertFalse(contains_hard_pii("{'mascot_name': 'The Falcons'}"))

    @override_settings(AI_PII_METADATA_FIELDS=("codename",))
    def test_a_deployment_can_extend_the_personal_vocabulary(self):
        self.assertTrue(contains_hard_pii("{'codename': 'Bluebird'}"))


class TheShapeRulesStillWorkTests(SimpleTestCase):
    """The new rule runs first; it must not shadow the existing ones."""

    def test_a_bare_email_is_still_caught(self):
        self.assertTrue(contains_hard_pii("write to parent.ache@yahoo.fr today"))
        self.assertIn("[email redacted]", redact_for_external_inference("x parent.ache@yahoo.fr"))

    def test_a_labelled_email_is_redacted_whole_not_in_pieces(self):
        # The label rule runs before the email rule so the value is replaced
        # once, rather than the email rule rewriting its interior.
        out = redact_for_external_inference("{'guardian_email': 'parent.ache@yahoo.fr'}")
        self.assertIn("[redacted]", out)
        self.assertNotIn("yahoo.fr", out)

    def test_a_bare_date_still_does_not_make_a_payload_personal(self):
        # Deliberate pre-existing design: dates are SOFT. Preserved.
        self.assertFalse(contains_hard_pii("The term starts 2026-09-07."))


class TheExternalTierSurfaceIsPinnedTests(SimpleTestCase):
    """A census of everything that can reach a third-party model.

    ``test_ai_external_sensitivity_call_sites`` audits the sites it already
    knows about, and pins a hand-written list of sites that must stay denied.
    Neither notices a BRAND-NEW declaration: add
    ``"sensitivity_class": "internal"`` to a fresh view and both stay green
    while the surface that can send school data off-site quietly grows.

    This walks the tree instead. Adding a site is allowed — it just cannot be
    silent. Add it here with the reason it is safe, the way the nine below were
    each verified to project only aggregates, enums, or the tenant's own name.
    """

    #: (path, declared class) for every site that can open the external tier.
    PINNED = {
        ("apps/api/learning_institution_api.py", "internal"),
        ("apps/brand_experience/template_ai_recommender.py", "internal"),
        ("apps/platform_runtime/ai_system_layer.py", "internal"),
        ("apps/siteconfig/views_live_banner_studio.py", "internal"),
        ("apps/siteconfig/views_onboarding_coach.py", "internal"),
        ("services/ai_palette.py", "internal"),
    }
    #: Sites whose class is computed, so the value is not visible to a scan.
    #: Each must own the decision in code, and be covered by its own tests.
    PINNED_DYNAMIC = {
        "apps/migration_cloud/ai_bridge.py",       # _sensitivity_class_for
        "apps/platform_runtime/ai_providers.py",   # forwards a caller's kwarg
    }

    def _declarations(self):
        import ast
        import pathlib

        from services.ai_gateway import _external_sensitivity_allowlist

        allow = _external_sensitivity_allowlist()
        root = pathlib.Path(__file__).resolve().parents[2]
        static, dynamic = set(), set()
        for sub in ("apps", "services", "config"):
            for f in (root / sub).rglob("*.py"):
                rel = f.relative_to(root).as_posix()
                if "/tests/" in rel or "/migrations/" in rel or f.name.startswith("test_"):
                    continue
                try:
                    tree = ast.parse(f.read_text(encoding="utf-8", errors="replace"))
                except SyntaxError:
                    continue
                for node in ast.walk(tree):
                    value = None
                    if isinstance(node, ast.keyword) and node.arg == "sensitivity_class":
                        value = node.value
                    elif isinstance(node, ast.Dict):
                        for key, val in zip(node.keys, node.values):
                            if isinstance(key, ast.Constant) and key.value == "sensitivity_class":
                                value = val
                    elif isinstance(node, ast.Assign):
                        for target in node.targets:
                            if (
                                isinstance(target, ast.Subscript)
                                and isinstance(target.slice, ast.Constant)
                                and target.slice.value == "sensitivity_class"
                            ):
                                value = node.value
                    if value is None:
                        continue
                    if isinstance(value, ast.Constant):
                        declared = str(value.value).strip().lower()
                        if declared in allow:
                            static.add((rel, declared))
                    else:
                        dynamic.add(rel)
        return static, dynamic

    def test_no_new_site_may_reach_the_external_tier_unreviewed(self):
        static, _ = self._declarations()
        added = static - self.PINNED
        self.assertEqual(
            added,
            set(),
            "a NEW call site can now send data to a third-party model. Verify its "
            "prompt cannot reach a student, then add it to PINNED with that reason.",
        )

    def test_a_retired_site_is_removed_from_the_pin(self):
        static, _ = self._declarations()
        stale = self.PINNED - static
        self.assertEqual(
            stale, set(), "PINNED names a site that no longer declares a class"
        )

    def test_computed_declarations_stay_accounted_for(self):
        _, dynamic = self._declarations()
        self.assertEqual(
            dynamic - self.PINNED_DYNAMIC,
            set(),
            "a site now COMPUTES its sensitivity class, so no scan can read its "
            "value. It needs its own tests before it is pinned here.",
        )
