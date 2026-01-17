# Generated manually (Release 1): evaluation models
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    initial = True

    dependencies = [
        ("academics", "0001_initial"),
        ("people", "0001_initial"),
    ]

    operations = [
        migrations.CreateModel(
            name="AssessmentWeights",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("seq1_weight", models.PositiveSmallIntegerField(default=20)),
                ("seq2_weight", models.PositiveSmallIntegerField(default=20)),
                ("exam_weight", models.PositiveSmallIntegerField(default=60)),
                ("mock_weight", models.PositiveSmallIntegerField(default=0)),
                ("practical_weight", models.PositiveSmallIntegerField(default=0)),
                ("score_scale", models.PositiveSmallIntegerField(default=20)),
                ("academic_year", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="assessment_weights", to="academics.academicyear")),
                ("classroom", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name="assessment_weights", to="academics.classroom")),
            ],
            options={"verbose_name_plural": "Assessment Weights"},
        ),
        migrations.CreateModel(
            name="TeacherAssignment",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("academic_year", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to="academics.academicyear")),
                ("term", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to="academics.term")),
                ("subject_assignment", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to="academics.subjectassignment")),
                ("teacher", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to="people.teacherprofile")),
            ],
            options={"constraints": [models.UniqueConstraint(fields=("academic_year", "term", "subject_assignment", "teacher"), name="uniq_teacher_assignment")]} ,
        ),
        migrations.CreateModel(
            name="Evaluation",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("test1", models.DecimalField(blank=True, decimal_places=2, max_digits=5, null=True)),
                ("test2", models.DecimalField(blank=True, decimal_places=2, max_digits=5, null=True)),
                ("seq1_score", models.DecimalField(blank=True, decimal_places=2, max_digits=5, null=True)),
                ("seq2_score", models.DecimalField(blank=True, decimal_places=2, max_digits=5, null=True)),
                ("exam_score", models.DecimalField(blank=True, decimal_places=2, max_digits=5, null=True)),
                ("mock_score", models.DecimalField(blank=True, decimal_places=2, max_digits=5, null=True)),
                ("practical_score", models.DecimalField(blank=True, decimal_places=2, max_digits=5, null=True)),
                ("remarks", models.CharField(blank=True, max_length=255)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("academic_year", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to="academics.academicyear")),
                ("specialty", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to="academics.specialty")),
                ("student", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to="people.studentprofile")),
                ("subject_assignment", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to="academics.subjectassignment")),
                ("teacher", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, to="people.teacherprofile")),
                ("term", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to="academics.term")),
            ],
            options={"constraints": [models.UniqueConstraint(fields=("academic_year", "term", "subject_assignment", "student"), name="uniq_evaluation")]} ,
        ),
        migrations.AddConstraint(
            model_name="assessmentweights",
            constraint=models.UniqueConstraint(fields=("academic_year", "classroom"), name="uniq_assessment_weights_per_year_classroom"),
        ),
    ]
