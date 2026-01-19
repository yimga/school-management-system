import re

from django.db import migrations, models


def populate_admission_numbers(apps, schema_editor):
    StudentProfile = apps.get_model("people", "StudentProfile")
    AcademicYear = apps.get_model("academics", "AcademicYear")
    Specialty = apps.get_model("academics", "Specialty")
    Classroom = apps.get_model("academics", "Classroom")
    SiteSettings = apps.get_model("siteconfig", "SiteSettings")

    settings_obj, _ = SiteSettings.objects.get_or_create(pk=1, defaults={"school_code": "GIL"})
    school_code = (settings_obj.school_code or "GIL").upper()

    # Cache related objects for efficiency
    years = {y.id: y for y in AcademicYear.objects.all()}
    specialties = {s.id: s for s in Specialty.objects.all()}
    classrooms = {c.id: c for c in Classroom.objects.all()}

    per_year_counts: dict[int, int] = {}

    def class_segment(classroom):
        if classroom and classroom.code:
            match = re.search(r"(\\d+)$", classroom.code)
            if match:
                return match.group(1)
            return classroom.code[:2].upper()
        return "00"

    for student in StudentProfile.objects.all().order_by("id"):
        if student.admission_number:
            continue

        ay = years.get(student.academic_year_id)
        spec = specialties.get(student.specialty_id)
        cls = classrooms.get(student.classroom_id)

        year_str = (ay.name or "")[:4] if ay else ""
        yy = year_str[-2:] if year_str and year_str[:4].isdigit() else "00"

        key = student.academic_year_id or 0
        per_year_counts[key] = per_year_counts.get(key, 0) + 1
        seq_str = f"{per_year_counts[key]:04d}"

        spec_segment = (spec.code or "XX").upper()[:6] if spec else "XX"
        cls_segment = class_segment(cls)

        admission = f"{yy}-{school_code}-{seq_str}-{spec_segment}-{cls_segment}"
        student.admission_number = admission
        if not student.student_code:
            student.student_code = admission
        student.save(update_fields=["admission_number", "student_code"])


class Migration(migrations.Migration):

    dependencies = [
        ("academics", "0001_initial"),
        ("siteconfig", "0006_sitesettings_school_code"),
        ("people", "0004_studentguardian_address_studentguardian_phone_and_more"),
    ]

    operations = [
        migrations.AddField(
            model_name="studentprofile",
            name="admission_number",
            field=models.CharField(blank=True, max_length=64, null=True, unique=True),
        ),
        migrations.AddField(
            model_name="studentprofile",
            name="date_of_birth",
            field=models.DateField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="studentprofile",
            name="gender",
            field=models.CharField(blank=True, max_length=10),
        ),
        migrations.AddField(
            model_name="studentprofile",
            name="joined_date",
            field=models.DateField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="studentprofile",
            name="joined_term",
            field=models.CharField(blank=True, max_length=20),
        ),
        migrations.AddField(
            model_name="studentprofile",
            name="parent_phone",
            field=models.CharField(blank=True, max_length=50),
        ),
        migrations.AddField(
            model_name="studentprofile",
            name="place_of_birth",
            field=models.CharField(blank=True, max_length=120),
        ),
        migrations.AddField(
            model_name="studentprofile",
            name="referral_code",
            field=models.CharField(blank=True, max_length=80),
        ),
        migrations.AddField(
            model_name="studentprofile",
            name="section",
            field=models.CharField(blank=True, max_length=80),
        ),
        migrations.AddField(
            model_name="studentprofile",
            name="status",
            field=models.CharField(blank=True, max_length=20),
        ),
        migrations.RunPython(populate_admission_numbers, migrations.RunPython.noop),
        migrations.AlterField(
            model_name="studentprofile",
            name="student_code",
            field=models.CharField(blank=True, max_length=50, unique=True),
        ),
    ]
