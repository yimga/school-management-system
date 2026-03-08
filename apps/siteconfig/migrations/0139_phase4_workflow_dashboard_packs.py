# Phase 4: WorkflowPack, DashboardPack and assignments

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("schools", "0025_add_school_type"),
        ("siteconfig", "0138_add_super_admin_dashboard_preference"),
    ]

    operations = [
        migrations.CreateModel(
            name="WorkflowPack",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("code", models.CharField(max_length=80, unique=True)),
                ("name", models.CharField(max_length=120)),
                ("description", models.TextField(blank=True)),
                ("family", models.CharField(blank=True, db_index=True, max_length=64)),
                ("version", models.CharField(default="1.0", max_length=32)),
                ("is_active", models.BooleanField(db_index=True, default=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
            options={"verbose_name": "Workflow Pack", "verbose_name_plural": "Workflow Packs", "ordering": ["family", "name"]},
        ),
        migrations.CreateModel(
            name="WorkflowPackAssignment",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("module_slug", models.CharField(db_index=True, help_text="e.g. admissions, fee_approval, grade_publish", max_length=80)),
                ("is_active", models.BooleanField(default=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("school", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="workflow_pack_assignments", to="schools.school")),
                ("workflow_pack", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="assignments", to="siteconfig.workflowpack")),
            ],
            options={"verbose_name": "Workflow pack assignment", "verbose_name_plural": "Workflow pack assignments", "ordering": ["school", "module_slug"], "unique_together": {("school", "module_slug")}},
        ),
        migrations.AddField(
            model_name="workflowtemplate",
            name="workflow_pack",
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="templates", to="siteconfig.workflowpack"),
        ),
        migrations.CreateModel(
            name="DashboardPack",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("code", models.CharField(max_length=80, unique=True)),
                ("name", models.CharField(max_length=120)),
                ("description", models.TextField(blank=True)),
                ("family", models.CharField(blank=True, db_index=True, max_length=64)),
                ("version", models.CharField(default="1.0", max_length=32)),
                ("is_active", models.BooleanField(db_index=True, default=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
            options={"verbose_name": "Dashboard Pack", "verbose_name_plural": "Dashboard Packs", "ordering": ["family", "name"]},
        ),
        migrations.CreateModel(
            name="DashboardPackAssignment",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("role", models.CharField(db_index=True, help_text="e.g. admin, teacher, parent", max_length=20)),
                ("is_active", models.BooleanField(default=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("dashboard_pack", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="assignments", to="siteconfig.dashboardpack")),
                ("school", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="dashboard_pack_assignments", to="schools.school")),
            ],
            options={"verbose_name": "Dashboard pack assignment", "verbose_name_plural": "Dashboard pack assignments", "ordering": ["school", "role"], "unique_together": {("school", "role")}},
        ),
        migrations.AddField(
            model_name="dashboardtemplate",
            name="dashboard_pack",
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="templates", to="siteconfig.dashboardpack"),
        ),
    ]
