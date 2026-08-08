"""EPHEMERAL fast-test settings. Delete after use."""
from config.settings_test import *  # noqa: F401,F403


class _DisableMigrations:
    def __contains__(self, item):
        return True

    def __getitem__(self, item):
        return None


MIGRATION_MODULES = _DisableMigrations()
TEST_RUNNER = "config.fast_test_runner.FastRunner"
