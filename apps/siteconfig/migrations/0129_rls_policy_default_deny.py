# RLS default-deny: officialreporttemplate + featuretogglestate. No-op when USE_DJANGO_TENANTS=True.

from django.db import connection, migrations

from apps.schools.rls import should_apply_rls

USING = "current_setting('app.rls_bypass', true) = 'on' OR (current_setting('app.current_school_id', true) IS NOT NULL AND school_id::text = current_setting('app.current_school_id', true))"
USING_FT = "current_setting('app.rls_bypass', true) = 'on' OR school_id IS NULL OR (current_setting('app.current_school_id', true) IS NOT NULL AND school_id::text = current_setting('app.current_school_id', true))"


def apply_policy(apps, schema_editor):
    if not should_apply_rls(connection):
        return
    c = connection.cursor()
    c.execute("DROP POLICY IF EXISTS siteconfig_officialreporttemplate_tenant_isolation ON siteconfig_officialreporttemplate")
    c.execute("CREATE POLICY siteconfig_officialreporttemplate_tenant_isolation ON siteconfig_officialreporttemplate FOR ALL USING (" + USING + ") WITH CHECK (" + USING + ")")
    c.execute("DROP POLICY IF EXISTS siteconfig_featuretogglestate_tenant_isolation ON siteconfig_featuretogglestate")
    c.execute("CREATE POLICY siteconfig_featuretogglestate_tenant_isolation ON siteconfig_featuretogglestate FOR ALL USING (" + USING_FT + ") WITH CHECK (" + USING_FT + ")")


def reverse_policy(apps, schema_editor):
    if not should_apply_rls(connection):
        return
    old = "current_setting('app.current_school_id', true) IS NULL OR school_id::text = current_setting('app.current_school_id', true)"
    old_ft = "current_setting('app.current_school_id', true) IS NULL OR school_id IS NULL OR school_id::text = current_setting('app.current_school_id', true)"
    c = connection.cursor()
    c.execute("DROP POLICY IF EXISTS siteconfig_officialreporttemplate_tenant_isolation ON siteconfig_officialreporttemplate")
    c.execute("CREATE POLICY siteconfig_officialreporttemplate_tenant_isolation ON siteconfig_officialreporttemplate FOR ALL USING (" + old + ") WITH CHECK (" + old + ")")
    c.execute("DROP POLICY IF EXISTS siteconfig_featuretogglestate_tenant_isolation ON siteconfig_featuretogglestate")
    c.execute("CREATE POLICY siteconfig_featuretogglestate_tenant_isolation ON siteconfig_featuretogglestate FOR ALL USING (" + old_ft + ") WITH CHECK (" + old_ft + ")")


class Migration(migrations.Migration):
    dependencies = [("siteconfig", "0128_marketing_content_and_blog_post")]
    operations = [migrations.RunPython(apply_policy, reverse_policy)]
