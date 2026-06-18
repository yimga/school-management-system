# PostgreSQL RLS for metadata EAV tenant isolation (shared schema).

from django.db import migrations


RLS_UP = """
ALTER TABLE metadata_dynamicfieldvalue ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS metadata_dfv_school_scope ON metadata_dynamicfieldvalue;
CREATE POLICY metadata_dfv_school_scope ON metadata_dynamicfieldvalue
  USING (
    school_id IS NULL
    OR school_id::text = current_setting('app.current_school_id', true)
    OR current_setting('app.current_school_id', true) = ''
  );
ALTER TABLE metadata_dynamicfielddefinition ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS metadata_dfd_school_scope ON metadata_dynamicfielddefinition;
CREATE POLICY metadata_dfd_school_scope ON metadata_dynamicfielddefinition
  USING (
    school_id IS NULL
    OR school_id::text = current_setting('app.current_school_id', true)
    OR current_setting('app.current_school_id', true) = ''
  );
"""

RLS_DOWN = """
DROP POLICY IF EXISTS metadata_dfv_school_scope ON metadata_dynamicfieldvalue;
ALTER TABLE metadata_dynamicfieldvalue DISABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS metadata_dfd_school_scope ON metadata_dynamicfielddefinition;
ALTER TABLE metadata_dynamicfielddefinition DISABLE ROW LEVEL SECURITY;
"""


def _apply_rls(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    schema_editor.execute(RLS_UP)


def _revert_rls(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    schema_editor.execute(RLS_DOWN)


class Migration(migrations.Migration):

    dependencies = [
        ("metadata", "0011_fieldcatalogentry_compliance_tags_and_more"),
    ]

    operations = [
        migrations.RunPython(_apply_rls, _revert_rls),
    ]
