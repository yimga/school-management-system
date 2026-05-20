# Generated for batches 1331/1336/1337 help-center graft

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("feedback", "0003_alter_feedbackattachment_file"),
    ]

    operations = [
        migrations.CreateModel(
            name="SupportDeflectionEvent",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("surface", models.CharField(db_index=True, default="support_ticket", max_length=64)),
                ("outcome", models.CharField(choices=[("suggested", "Articles suggested"), ("opened", "User opened article"), ("dismissed", "User dismissed gate"), ("submitted", "Ticket submitted anyway")], db_index=True, max_length=32)),
                ("top_score", models.FloatField(default=0)),
                ("article_slug", models.CharField(blank=True, max_length=120)),
                ("query_fingerprint", models.CharField(blank=True, db_index=True, max_length=64)),
                ("is_operator", models.BooleanField(default=False)),
                ("created_at", models.DateTimeField(auto_now_add=True, db_index=True)),
                ("school", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name="support_deflection_events", to="schools.school")),
                ("user", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="support_deflection_events", to=settings.AUTH_USER_MODEL)),
            ],
            options={"ordering": ["-created_at"]},
        ),
        migrations.CreateModel(
            name="HelpSearchQueryLog",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("query_fingerprint", models.CharField(db_index=True, max_length=64)),
                ("result_count", models.PositiveSmallIntegerField(default=0)),
                ("is_operator", models.BooleanField(default=False)),
                ("locale", models.CharField(blank=True, db_index=True, max_length=12)),
                ("created_at", models.DateTimeField(auto_now_add=True, db_index=True)),
                ("school", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name="help_search_logs", to="schools.school")),
            ],
            options={"ordering": ["-created_at"]},
        ),
        migrations.CreateModel(
            name="SupportAIInteractionReview",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("query_fingerprint", models.CharField(blank=True, db_index=True, max_length=64)),
                ("active_url", models.CharField(blank=True, max_length=500)),
                ("outcome", models.CharField(blank=True, max_length=64)),
                ("thumbs", models.CharField(blank=True, max_length=16)),
                ("language", models.CharField(blank=True, max_length=12)),
                ("status", models.CharField(choices=[("pending", "Pending review"), ("resolved", "Resolved"), ("dismissed", "Dismissed")], db_index=True, default="pending", max_length=16)),
                ("is_operator", models.BooleanField(default=False)),
                ("created_at", models.DateTimeField(auto_now_add=True, db_index=True)),
                ("resolved_at", models.DateTimeField(blank=True, null=True)),
                ("school", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name="support_ai_reviews", to="schools.school")),
                ("user", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="support_ai_reviews", to=settings.AUTH_USER_MODEL)),
            ],
            options={"ordering": ["-created_at"]},
        ),
        migrations.AddIndex(
            model_name="supportdeflectionevent",
            index=models.Index(fields=["surface", "-created_at"], name="feedback_sd_surface_idx"),
        ),
        migrations.AddIndex(
            model_name="supportdeflectionevent",
            index=models.Index(fields=["outcome", "-created_at"], name="feedback_sd_outcome_idx"),
        ),
    ]
