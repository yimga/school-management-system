#!/usr/bin/env python3
"""
Run support-pipeline Django tests against a pre-migrated SQLite file (no test DB recreate).

Use when ``manage.py test`` hangs on Windows DB teardown. Requires
``.django_test_dbs/rmc_sqlite_test_runner.sqlite3`` (or copy) with portal 0033 applied.
"""
from __future__ import annotations

import os
import shutil
import sys
import time
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def main() -> int:
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))
    src = ROOT / ".django_test_dbs" / "rmc_sqlite_test_runner.sqlite3"
    dst = ROOT / ".django_test_dbs" / f"support_pipeline_direct_{os.getpid()}_{int(time.time() * 1000)}.sqlite3"
    if not src.is_file():
        print(f"Missing migrated seed DB: {src}", file=sys.stderr)
        return 1
    if dst.is_file():
        dst.unlink()
    shutil.copy2(src, dst)

    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
    os.environ["DB_FILE"] = str(dst)
    os.environ["RMC_SQLITE_TEST_MEMORY"] = "1"
    os.environ["DJANGO_TEST_DB_FILE"] = str(dst)
    # settings.RUNNING_TESTS gates session backend + SQLite test tuning.
    if "test" not in sys.argv:
        sys.argv.append("test")

    import django

    django.setup()

    # Seed DBs may omit django_session; cache backend avoids full migrate on a copy.
    from django.conf import settings

    settings.SESSION_ENGINE = "django.contrib.sessions.backends.cache"
    db_opts = settings.DATABASES.get("default", {}).setdefault("OPTIONS", {})
    db_opts.setdefault("timeout", 60)

    from apps.portal.tests import test_kb_context_unit, test_kb_embeddings
    from apps.portal.tests import test_support_ingest
    from services.ai.tests import (
        test_code_index_role_fence,
        test_code_oracle,
        test_multitenant_isolation,
        test_support_intent_router,
        test_support_sanitize_intent,
        test_support_sse,
        test_support_stream_language,
    )

    loader = unittest.TestLoader()
    suite = unittest.TestSuite()
    suite.addTests(loader.loadTestsFromModule(test_code_oracle))
    suite.addTests(loader.loadTestsFromModule(test_multitenant_isolation))
    suite.addTests(loader.loadTestsFromModule(test_support_sse))
    suite.addTests(loader.loadTestsFromModule(test_kb_embeddings))
    suite.addTests(loader.loadTestsFromModule(test_kb_context_unit))
    suite.addTests(loader.loadTestsFromModule(test_support_sanitize_intent))
    suite.addTests(loader.loadTestsFromModule(test_support_intent_router))
    suite.addTests(loader.loadTestsFromModule(test_support_stream_language))
    suite.addTests(loader.loadTestsFromModule(test_code_index_role_fence))
    suite.addTests(loader.loadTestsFromModule(test_support_ingest))

    result = unittest.TextTestRunner(verbosity=2).run(suite)
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    raise SystemExit(main())
