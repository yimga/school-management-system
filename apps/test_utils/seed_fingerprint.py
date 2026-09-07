"""Refuse to run against a test database whose seeded catalogs were truncated.

``RestoresSeedCatalogMixin`` stops a flushing test from truncating the seed
catalogs, and ``scan_unrestored_flush_testcase`` stops a new flusher landing.
Neither helps a ``--keepdb`` file that was ALREADY damaged: the damage is
permanent, because a data migration is recorded as applied and never re-runs.
The cost is measured and large -- five known-red files reported **21 failures on
a damaged database, 4 on a healthy one**, and every one of the 17 read as a code
regression. Three sessions produced three different failure counts for this repo
in one day, on three contamination states of the same file.

So the last gap is not prevention, it is that nobody can TELL. This closes it:
the database reports its own damage at session start, before a single test runs.

WHY A FINGERPRINT AND NOT A CHECKLIST
-------------------------------------
The obvious implementation asserts the catalogs we know about -- AccessRole,
Permission, CountryGradingProfile, ThemePack. That is exactly the shape that has
already failed twice here: two catalogs were found on 2026-09-06 and a third was
suspected within the hour, and a checklist is silent on the one nobody has found
yet. So this records what the database looked like when it was BUILT and
compares against that. It needs no knowledge of which catalogs exist, and a
catalog added next year is covered on the day it lands.

WHAT COUNTS AS DAMAGE
---------------------
A table that held rows at build time and holds none now. Deliberately narrow:
a partial delete is ordinary test residue, while a seeded table at exactly zero
is the flush signature. ``flush`` re-emits ``post_migrate``, so self-healing
tables (contenttypes, the lone SUPERADMIN AccessRole) come back non-empty and
are correctly not reported -- which is also why counting rows rather than
checking emptiness would produce noise nobody would act on.
"""

from __future__ import annotations

import json
import os
import re
from pathlib import Path

#: Set to 1 to run anyway. The guard reports and refuses; it does not trap
#: anyone who has a reason to proceed.
ESCAPE_ENV = "RMC_ALLOW_DAMAGED_TEST_DB"

SIDECAR_SUFFIX = ".seed-fingerprint.json"

#: Tables whose emptiness is never evidence: Django's own bookkeeping, and
#: anything a session writes and clears as a matter of course.
IGNORED = frozenset(
    {
        "django_migrations",
        "django_session",
        "django_admin_log",
    }
)

_SAFE_TABLE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def _sidecar_path(connection) -> Path | None:
    """Where this database's fingerprint lives, or None if we cannot place one."""
    name = connection.settings_dict.get("NAME")
    if not name:
        return None
    if "sqlite" in str(connection.settings_dict.get("ENGINE", "")):
        return Path(str(name) + SIDECAR_SUFFIX)
    # A non-file backend still deserves the guard; park the sidecar beside the
    # sqlite ones so the directory stays the single place to look.
    root = Path(__file__).resolve().parents[2] / ".django_test_dbs"
    try:
        root.mkdir(parents=True, exist_ok=True)
    except OSError:
        return None
    safe = re.sub(r"[^A-Za-z0-9_.-]", "_", "%s-%s" % (connection.alias, name))
    return root / (safe + SIDECAR_SUFFIX)


def _table_names(connection) -> list[str]:
    with connection.cursor() as cursor:
        names = connection.introspection.table_names(cursor)
    # Introspected names are interpolated into COUNT queries below, so anything
    # that is not a plain identifier is dropped rather than quoted-and-hoped.
    return [n for n in names if n not in IGNORED and _SAFE_TABLE.match(n)]


def record(connection) -> Path | None:
    """Snapshot the non-empty tables of a freshly built database.

    Only ever called for a database this session CREATED, so the recorded state
    is known-good by construction.
    """
    path = _sidecar_path(connection)
    if path is None:
        return None
    counts: dict[str, int] = {}
    with connection.cursor() as cursor:
        for table in _table_names(connection):
            try:
                # Introspects the TEST database only: counts rows in every table to
                # detect flush damage. There is no tenant context at session
                # start, and a school scope would defeat the check outright.
                # rls-bypass-allow: test-DB introspection, unscoped by design
                cursor.execute('SELECT COUNT(*) FROM "%s"' % table)
                n = cursor.fetchone()[0]
            except Exception:
                continue
            if n:
                counts[table] = n
    payload = {"version": 1, "alias": connection.alias, "seeded_tables": counts}
    try:
        path.write_text(json.dumps(payload, indent=1, sort_keys=True), encoding="utf-8")
    except OSError:
        return None
    return path


def damaged_tables(connection) -> list[str] | None:
    """Tables that were seeded at build time and are empty now.

    Returns None when there is no fingerprint to compare against -- "unknown" and
    "clean" are different answers and the caller must not conflate them.
    """
    path = _sidecar_path(connection)
    if path is None or not path.exists():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        seeded = payload["seeded_tables"]
    except (OSError, ValueError, KeyError):
        return None

    live = set(_table_names(connection))
    empty: list[str] = []
    with connection.cursor() as cursor:
        for table in sorted(seeded):
            if table not in live:
                continue
            try:
                # EXISTS, not COUNT: the question is "any row at all", and on a
                # large table COUNT would make this guard cost real time.
                # Introspects the TEST database only: counts rows in every table to
                # detect flush damage. There is no tenant context at session
                # start, and a school scope would defeat the check outright.
                # rls-bypass-allow: test-DB introspection, unscoped by design
                cursor.execute('SELECT EXISTS(SELECT 1 FROM "%s")' % table)
                if not cursor.fetchone()[0]:
                    empty.append(table)
            except Exception:
                continue
    return empty


def report(tables: list[str], db_name: str) -> str:
    listed = "\n".join("    %s" % t for t in tables[:15])
    more = "\n    ... and %d more" % (len(tables) - 15) if len(tables) > 15 else ""
    return (
        "\n"
        + "=" * 72
        + "\nTEST DATABASE IS DAMAGED -- refusing to run.\n"
        + "=" * 72
        + "\n%d table(s) held seeded rows when this database was built and are\n"
        "empty now. A TransactionTestCase flush truncates every table and is not\n"
        "rolled back, and a data migration recorded as applied never re-seeds.\n"
        "Results from this database are not attributable: failures will look\n"
        "like code regressions, and some tests will PASS only because a request\n"
        "was refused before reaching its assertion.\n\n%s%s\n\n"
        "  database: %s\n\n"
        "FIX -- rebuild it (no need to know which catalog was hit):\n"
        "  1. delete the .sqlite3 AND its -wal and -shm sidecars\n"
        "     (a stale sidecar against a fresh main file is a database that is\n"
        "      wrong and reports nothing)\n"
        "  2. re-run; the next session rebuilds and re-fingerprints it\n\n"
        "To run anyway, knowing the results are not attributable:\n"
        "  set %s=1\n" % (len(tables), listed, more, db_name, ESCAPE_ENV)
        + "=" * 72
        + "\n"
    )


def escape_hatch_engaged() -> bool:
    return os.environ.get(ESCAPE_ENV, "").strip().lower() in ("1", "true", "yes", "on")
