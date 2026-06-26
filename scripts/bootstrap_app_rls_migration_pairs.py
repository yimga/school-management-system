#!/usr/bin/env python3
"""Bootstrap enable_rls + rls_policy_default_deny migration pairs for apps missing RLS."""

from __future__ import annotations

import os
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

USING_CLAUSE = """(
    current_setting('app.rls_bypass', true) = 'on'
    OR (
        current_setting('app.current_school_id', true) IS NOT NULL
        AND school_id::text = current_setting('app.current_school_id', true)
    )
)"""


def _latest_migration(app_label: str) -> tuple[int, str]:
    mig_dir = REPO / "apps" / app_label / "migrations"
    best_num = 0
    best_name = ""
    for path in mig_dir.glob("*.py"):
        if path.name == "__init__.py":
            continue
        m = re.match(r"(\d{4})_(.+)\.py$", path.name)
        if not m:
            continue
        num = int(m.group(1))
        if num >= best_num:
            best_num = num
            best_name = path.stem
    return best_num, best_name


def _tenant_tables(app_label: str) -> list[str]:
    from django.apps import apps as django_apps

    config = django_apps.get_app_config(app_label)
    tables: list[str] = []
    for model in config.get_models():
        field_names = {f.name for f in model._meta.fields}
        if "school" in field_names or "school_id" in field_names:
            tables.append(model._meta.db_table)
    return sorted(set(tables))


def _write_enable(app_label: str, tables: list[str], dep: str, path: Path) -> None:
    path.write_text(
        f'''# RLS enable for tenant-scoped {app_label} tables (PostgreSQL only).

from django.db import connection, migrations

from apps.schools.rls import should_apply_rls

TABLES = {tables!r}


def enable_rls(apps, schema_editor):
    if not should_apply_rls(connection):
        return
    with connection.cursor() as cursor:
        for table in TABLES:
            cursor.execute(f"ALTER TABLE {{table}} ENABLE ROW LEVEL SECURITY;")


def disable_rls(apps, schema_editor):
    if not should_apply_rls(connection):
        return
    with connection.cursor() as cursor:
        for table in TABLES:
            cursor.execute(f"ALTER TABLE {{table}} DISABLE ROW LEVEL SECURITY;")


class Migration(migrations.Migration):
    dependencies = [
        ("{app_label}", "{dep}"),
    ]

    operations = [
        migrations.RunPython(enable_rls, disable_rls),
    ]
''',
        encoding="utf-8",
    )


def _write_deny(app_label: str, tables: list[str], enable_stem: str, path: Path) -> None:
    path.write_text(
        f'''# RLS default-deny for tenant-scoped {app_label} tables.

from django.db import connection, migrations

from apps.schools.rls import should_apply_rls

TABLES = {tables!r}
USING_CLAUSE = """{USING_CLAUSE}"""


def apply_default_deny(apps, schema_editor):
    if not should_apply_rls(connection):
        return
    with connection.cursor() as cursor:
        for table in TABLES:
            short = table.replace("{app_label}_", "", 1)
            policy_name = f"{app_label}_tenant_{{short}}"
            cursor.execute(f"DROP POLICY IF EXISTS {{policy_name}} ON {{table}};")
            cursor.execute(
                f"""
                CREATE POLICY {{policy_name}} ON {{table}}
                FOR ALL
                USING {{USING_CLAUSE}}
                WITH CHECK {{USING_CLAUSE}};
                """
            )


def reverse_default_deny(apps, schema_editor):
    if not should_apply_rls(connection):
        return
    with connection.cursor() as cursor:
        for table in TABLES:
            short = table.replace("{app_label}_", "", 1)
            policy_name = f"{app_label}_tenant_{{short}}"
            cursor.execute(f"DROP POLICY IF EXISTS {{policy_name}} ON {{table}};")


class Migration(migrations.Migration):
    dependencies = [
        ("{app_label}", "{enable_stem}"),
    ]

    operations = [
        migrations.RunPython(apply_default_deny, reverse_default_deny),
    ]
''',
        encoding="utf-8",
    )


def main() -> int:
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
    import django

    django.setup()

    from scripts.scan_rls_force_coverage import _app_has_rls_migrations, _scan

    apps_needed = sorted({f["model"].split(".")[0] for f in _scan()})
    written = 0
    for app_label in apps_needed:
        app_dir = REPO / "apps" / app_label
        has_enable, has_deny = _app_has_rls_migrations(app_dir)
        if has_enable and has_deny:
            continue
        tables = _tenant_tables(app_label)
        if not tables:
            print(f"skip {app_label}: no tenant tables")
            continue
        latest_num, latest_stem = _latest_migration(app_label)
        if not latest_stem:
            print(f"skip {app_label}: no migrations")
            continue
        mig_dir = app_dir / "migrations"
        enable_num = latest_num + 1
        deny_num = latest_num + 2
        enable_stem = f"{enable_num:04d}_enable_rls_postgresql"
        deny_stem = f"{deny_num:04d}_rls_policy_default_deny"
        enable_path = mig_dir / f"{enable_stem}.py"
        deny_path = mig_dir / f"{deny_stem}.py"
        if not has_enable and not enable_path.exists():
            _write_enable(app_label, tables, latest_stem, enable_path)
            written += 1
            print(f"wrote {enable_path.relative_to(REPO)} ({len(tables)} tables)")
        if not has_deny and not deny_path.exists():
            dep_stem = enable_stem if enable_path.exists() else latest_stem
            if not enable_path.exists() and not has_enable:
                dep_stem = enable_stem
            elif has_enable:
                dep_stem = next(p.stem for p in mig_dir.glob("*enable_rls*.py"))
            else:
                dep_stem = enable_stem
            _write_deny(app_label, tables, dep_stem, deny_path)
            written += 1
            print(f"wrote {deny_path.relative_to(REPO)}")
    print(f"bootstrap_app_rls: {written} migration file(s) written")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
