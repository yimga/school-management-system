from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("siteconfig", "0021_seed_dashboard_widgets"),
    ]

    operations = [
        migrations.AddField(
            model_name="sitesettings",
            name="admin_sidebar_bg_color",
            field=models.CharField(
                default="#0b0f14",
                help_text="Base sidebar background color (hex).",
                max_length=20,
            ),
        ),
        migrations.AddField(
            model_name="sitesettings",
            name="admin_sidebar_surface_color",
            field=models.CharField(
                default="#111827",
                help_text="Sidebar surface/surface overlay color.",
                max_length=20,
            ),
        ),
        migrations.AddField(
            model_name="sitesettings",
            name="admin_sidebar_border_color",
            field=models.CharField(
                default="#1f2937",
                help_text="Sidebar border color.",
                max_length=20,
            ),
        ),
        migrations.AddField(
            model_name="sitesettings",
            name="admin_sidebar_text_color",
            field=models.CharField(
                default="#e2e8f0",
                help_text="Primary sidebar text color.",
                max_length=20,
            ),
        ),
        migrations.AddField(
            model_name="sitesettings",
            name="admin_sidebar_text_muted_color",
            field=models.CharField(
                default="#94a3b8",
                help_text="Muted sidebar text color.",
                max_length=20,
            ),
        ),
        migrations.AddField(
            model_name="sitesettings",
            name="admin_sidebar_hover_color",
            field=models.CharField(
                default="#0f172a",
                help_text="Sidebar hover color.",
                max_length=20,
            ),
        ),
        migrations.AddField(
            model_name="sitesettings",
            name="admin_sidebar_active_color",
            field=models.CharField(
                default="#0f172a",
                help_text="Sidebar active background color.",
                max_length=20,
            ),
        ),
        migrations.AddField(
            model_name="sitesettings",
            name="admin_sidebar_active_border_color",
            field=models.CharField(
                default="#38bdf8",
                help_text="Sidebar active border color.",
                max_length=20,
            ),
        ),
        migrations.AddField(
            model_name="sitesettings",
            name="admin_sidebar_badge_bg_color",
            field=models.CharField(
                default="#1f2937",
                help_text="Sidebar badge background color.",
                max_length=20,
            ),
        ),
        migrations.AddField(
            model_name="sitesettings",
            name="admin_sidebar_badge_text_color",
            field=models.CharField(
                default="#e2e8f0",
                help_text="Sidebar badge text color.",
                max_length=20,
            ),
        ),
        migrations.AddField(
            model_name="sitesettings",
            name="admin_sidebar_child_bg_start",
            field=models.CharField(
                default="#0b1224",
                help_text="Gradient start color for sidebar child rows.",
                max_length=20,
            ),
        ),
        migrations.AddField(
            model_name="sitesettings",
            name="admin_sidebar_child_bg_end",
            field=models.CharField(
                default="#131b33",
                help_text="Gradient end color for sidebar child rows.",
                max_length=20,
            ),
        ),
        migrations.AddField(
            model_name="sitesettings",
            name="admin_sidebar_child_border_color",
            field=models.CharField(
                default="#e2e8f0",
                help_text="Border color used for sidebar child cards.",
                max_length=20,
            ),
        ),
        migrations.AddField(
            model_name="sitesettings",
            name="admin_sidebar_child_hover_color",
            field=models.CharField(
                default="#1d4ed8",
                help_text="Hover color for sidebar child cards.",
                max_length=20,
            ),
        ),
        migrations.AddField(
            model_name="sitesettings",
            name="admin_sidebar_child_active_color",
            field=models.CharField(
                default="#0f172a",
                help_text="Active color for sidebar child cards.",
                max_length=20,
            ),
        ),
    ]
