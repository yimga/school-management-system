# Generated merge migration to resolve multiple leaf nodes in people app

from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("people", "0005_alter_teacherprofile_pay_grade"),
        ("people", "0018_student_resource_return"),
    ]

    operations = []
