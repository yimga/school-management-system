from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("communication", "0018_message_locale_target"),
        # Pin to the latest schools migration so this table is created
        # AFTER the RLS owner-role binding from 0048, not before.
        ("schools", "0048_force_rls_on_all_enabled_tables"),
    ]

    operations = [
        migrations.CreateModel(
            name="CommunicationTemplate",
            fields=[
                ("id", models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("key", models.CharField(db_index=True, help_text="Catalog key (e.g. 'attendance.absent_today'). Must match COMMUNICATION_TEMPLATES.", max_length=120)),
                ("subject_template", models.CharField(blank=True, max_length=200)),
                ("body_template", models.TextField()),
                ("channels", models.JSONField(blank=True, default=list, help_text="List of channel codes this override applies to. Empty = all channels declared by the catalog entry.")),
                ("audience", models.CharField(blank=True, max_length=40)),
                ("sensitivity", models.CharField(choices=[("low", "Low"), ("medium", "Medium"), ("high", "High")], default="medium", max_length=10)),
                ("is_active", models.BooleanField(default=True)),
                ("locale", models.CharField(blank=True, help_text="Optional BCP-47 locale (e.g. 'fr-CM'). Empty = applies to all locales.", max_length=20)),
                ("notes", models.TextField(blank=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("school", models.ForeignKey(
                    blank=True,
                    null=True,
                    help_text="Null = platform-wide override; otherwise scoped to the tenant.",
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name="communication_templates",
                    to="schools.school",
                )),
            ],
            options={
                "verbose_name": "Communication template override",
                "verbose_name_plural": "Communication template overrides",
            },
        ),
        migrations.AddIndex(
            model_name="communicationtemplate",
            index=models.Index(fields=["school", "key", "is_active"], name="comm_tmpl_school_key_active_idx"),
        ),
        migrations.AddIndex(
            model_name="communicationtemplate",
            index=models.Index(fields=["key", "locale", "is_active"], name="comm_tmpl_key_locale_active_idx"),
        ),
        migrations.AddConstraint(
            model_name="communicationtemplate",
            constraint=models.UniqueConstraint(fields=("school", "key", "locale"), name="comm_tmpl_school_key_locale_uniq"),
        ),
    ]
