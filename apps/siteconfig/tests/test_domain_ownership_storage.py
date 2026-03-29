"""Registry gate parity with ``scripts/verify_domain_ownership_exact_storage.py``."""

from django.test import SimpleTestCase

from apps.platform_runtime.runtime_defaults_first_class import (
    RUNTIME_DEFAULTS_FIRST_CLASS_FIELD_NAMES,
)
from apps.siteconfig.domain_ownership import EXACT_FIELD_OWNERS
from apps.siteconfig.domain_ownership_storage import (
    VIRTUAL_ONLY_EXACT_FIELDS,
    collect_exact_field_storage_errors,
)


class DomainOwnershipStorageRegistryTests(SimpleTestCase):
    def test_exact_field_storage_registry_has_no_errors(self):
        errors = collect_exact_field_storage_errors(
            exact_field_owners=dict(EXACT_FIELD_OWNERS),
            first_class_field_names=frozenset(RUNTIME_DEFAULTS_FIRST_CLASS_FIELD_NAMES),
            virtual_only_exact=VIRTUAL_ONLY_EXACT_FIELDS,
        )
        self.assertEqual(
            errors,
            [],
            msg="; ".join(errors) if errors else "",
        )

    def test_first_class_columns_all_have_exact_owner_rows(self):
        exact_keys = frozenset(EXACT_FIELD_OWNERS.keys())
        missing = [
            name
            for name in RUNTIME_DEFAULTS_FIRST_CLASS_FIELD_NAMES
            if name not in exact_keys
        ]
        self.assertEqual(
            missing,
            [],
            msg=f"Add to EXACT_FIELD_OWNERS: {missing!r}",
        )
