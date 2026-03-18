# Part 4.6: PostgreSQL triggers → tenant audit_log. Run per tenant schema.
# PII: sensitive keys stripped before insert (see REDACT_KEYS below).

from django.db import migrations, connection


# Keys to strip from old_values/new_values (never log in audit).
REDACT_KEYS = [
    "password",
    "password_hash",
    "secret",
    "token",
    "api_key",
    "card_last4",
    "card_number",
    "ssn",
    "social_security",
]


def apply_audit_triggers(apps, schema_editor):
    if connection.vendor != "postgresql":
        return
    # Keys stripped from old_values/new_values (PII/sensitive — plan 4.6).
    redact_keys_sql = "ARRAY[" + ", ".join(repr(k) for k in REDACT_KEYS) + "]::text[]"
    with connection.cursor() as cursor:
        # Create trigger function (idempotent). Supports any table with "id" column (bigint or UUID).
        cursor.execute(
            """
            CREATE OR REPLACE FUNCTION audit_trigger_fn()
            RETURNS TRIGGER AS $$
            DECLARE
              old_json jsonb;
              new_json jsonb;
              action text;
              tbl text;
              rec_id text;
              redact_keys text[] := """
            + redact_keys_sql
            + """;
            BEGIN
              tbl := TG_TABLE_NAME;
              action := TG_OP;
              IF TG_OP = 'DELETE' THEN
                old_json := to_jsonb(OLD) - redact_keys;
                new_json := NULL;
                rec_id := (OLD).id::text;
              ELSIF TG_OP = 'UPDATE' THEN
                old_json := to_jsonb(OLD) - redact_keys;
                new_json := to_jsonb(NEW) - redact_keys;
                rec_id := (NEW).id::text;
              ELSE
                old_json := NULL;
                new_json := to_jsonb(NEW) - redact_keys;
                rec_id := (NEW).id::text;
              END IF;
              INSERT INTO audit_log (table_name, record_id, action, old_values, new_values, changed_at)
              VALUES (tbl, rec_id, action, old_json, new_json, now());
              IF TG_OP = 'DELETE' THEN RETURN OLD; ELSE RETURN NEW; END IF;
            END;
            $$ LANGUAGE plpgsql;
            """
        )

        # Attach to people_studentprofile (drop if exists for idempotency)
        cursor.execute(
            "DROP TRIGGER IF EXISTS audit_people_studentprofile ON people_studentprofile;"
        )
        cursor.execute("""
            CREATE TRIGGER audit_people_studentprofile
            AFTER INSERT OR UPDATE OR DELETE ON people_studentprofile
            FOR EACH ROW EXECUTE PROCEDURE audit_trigger_fn();
        """)

        # Attach to people_teacherprofile
        cursor.execute(
            "DROP TRIGGER IF EXISTS audit_people_teacherprofile ON people_teacherprofile;"
        )
        cursor.execute("""
            CREATE TRIGGER audit_people_teacherprofile
            AFTER INSERT OR UPDATE OR DELETE ON people_teacherprofile
            FOR EACH ROW EXECUTE PROCEDURE audit_trigger_fn();
        """)


def reverse_audit_triggers(apps, schema_editor):
    if connection.vendor != "postgresql":
        return
    with connection.cursor() as cursor:
        cursor.execute(
            "DROP TRIGGER IF EXISTS audit_people_studentprofile ON people_studentprofile;"
        )
        cursor.execute(
            "DROP TRIGGER IF EXISTS audit_people_teacherprofile ON people_teacherprofile;"
        )
        cursor.execute("DROP FUNCTION IF EXISTS audit_trigger_fn();")


class Migration(migrations.Migration):
    dependencies = [
        ("people", "0036_add_tenant_audit_log"),
    ]

    operations = [
        migrations.RunPython(apply_audit_triggers, reverse_audit_triggers),
    ]
