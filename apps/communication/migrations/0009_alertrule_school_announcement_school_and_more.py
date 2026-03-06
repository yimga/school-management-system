import django.db.models.deletion
from django.db import connection
from django.db import migrations, models

from apps.schools.rls import should_apply_rls


COMMUNICATION_TABLES = [
    "communication_alertrule",
    "communication_announcement",
    "communication_announcementauditlog",
    "communication_classannouncement",
    "communication_contactrequest",
    "communication_contactrequestattachment",
    "communication_directconversation",
    "communication_message",
    "communication_messagethread",
    "communication_threadmessage",
    "communication_threadreadstate",
]


def _user_school_id(user_id, *, membership_map, student_map, teacher_map):
    if not user_id:
        return None
    return student_map.get(user_id) or teacher_map.get(user_id) or membership_map.get(user_id)


def backfill_communication_school(apps, schema_editor):
    db_alias = schema_editor.connection.alias
    SchoolMembership = apps.get_model("schools", "SchoolMembership")
    StudentProfile = apps.get_model("people", "StudentProfile")
    TeacherProfile = apps.get_model("people", "TeacherProfile")
    Classroom = apps.get_model("academics", "Classroom")
    Department = apps.get_model("academics", "Department")
    ClassAnnouncement = apps.get_model("communication", "ClassAnnouncement")
    MessageThread = apps.get_model("communication", "MessageThread")
    ThreadMessage = apps.get_model("communication", "ThreadMessage")
    ThreadReadState = apps.get_model("communication", "ThreadReadState")
    Announcement = apps.get_model("communication", "Announcement")
    AnnouncementAuditLog = apps.get_model("communication", "AnnouncementAuditLog")
    ContactRequest = apps.get_model("communication", "ContactRequest")
    ContactRequestAttachment = apps.get_model("communication", "ContactRequestAttachment")
    Message = apps.get_model("communication", "Message")
    DirectConversation = apps.get_model("communication", "DirectConversation")
    AlertRule = apps.get_model("communication", "AlertRule")

    membership_map = {}
    for row in (
        SchoolMembership.objects.using(db_alias)
        .order_by("-is_primary", "id")
        .values_list("user_id", "school_id")
    ):
        membership_map.setdefault(row[0], row[1])
    student_map = {
        user_id: school_id
        for user_id, school_id in (
            StudentProfile.objects.using(db_alias)
            .exclude(user_id__isnull=True)
            .exclude(school_id__isnull=True)
            .values_list("user_id", "school_id")
        )
    }
    teacher_map = {
        user_id: school_id
        for user_id, school_id in (
            TeacherProfile.objects.using(db_alias)
            .exclude(user_id__isnull=True)
            .exclude(school_id__isnull=True)
            .values_list("user_id", "school_id")
        )
    }
    classroom_map = dict(
        Classroom.objects.using(db_alias)
        .exclude(school_id__isnull=True)
        .values_list("id", "school_id")
    )
    department_map = dict(
        Department.objects.using(db_alias)
        .exclude(school_id__isnull=True)
        .values_list("id", "school_id")
    )
    announcement_map = dict(
        Announcement.objects.using(db_alias)
        .exclude(school_id__isnull=True)
        .values_list("id", "school_id")
    )
    thread_map = dict(
        MessageThread.objects.using(db_alias)
        .exclude(school_id__isnull=True)
        .values_list("id", "school_id")
    )
    contact_request_map = dict(
        ContactRequest.objects.using(db_alias)
        .exclude(school_id__isnull=True)
        .values_list("id", "school_id")
    )

    for row in (
        ClassAnnouncement.objects.using(db_alias)
        .filter(school_id__isnull=True)
        .values("id", "classroom_id", "department_id", "created_by_id")
        .iterator()
    ):
        school_id = (
            classroom_map.get(row["classroom_id"])
            or department_map.get(row["department_id"])
            or _user_school_id(
                row["created_by_id"],
                membership_map=membership_map,
                student_map=student_map,
                teacher_map=teacher_map,
            )
        )
        if school_id:
            ClassAnnouncement.objects.using(db_alias).filter(pk=row["id"]).update(school_id=school_id)

    for row in (
        MessageThread.objects.using(db_alias)
        .filter(school_id__isnull=True)
        .values("id", "classroom_id", "department_id", "created_by_id")
        .iterator()
    ):
        school_id = (
            classroom_map.get(row["classroom_id"])
            or department_map.get(row["department_id"])
            or _user_school_id(
                row["created_by_id"],
                membership_map=membership_map,
                student_map=student_map,
                teacher_map=teacher_map,
            )
        )
        if school_id:
            MessageThread.objects.using(db_alias).filter(pk=row["id"]).update(school_id=school_id)
            thread_map[row["id"]] = school_id

    for row in (
        ThreadMessage.objects.using(db_alias)
        .filter(school_id__isnull=True)
        .values("id", "thread_id", "author_id")
        .iterator()
    ):
        school_id = thread_map.get(row["thread_id"]) or _user_school_id(
            row["author_id"],
            membership_map=membership_map,
            student_map=student_map,
            teacher_map=teacher_map,
        )
        if school_id:
            ThreadMessage.objects.using(db_alias).filter(pk=row["id"]).update(school_id=school_id)

    for row in (
        ThreadReadState.objects.using(db_alias)
        .filter(school_id__isnull=True)
        .values("id", "thread_id", "user_id")
        .iterator()
    ):
        school_id = thread_map.get(row["thread_id"]) or _user_school_id(
            row["user_id"],
            membership_map=membership_map,
            student_map=student_map,
            teacher_map=teacher_map,
        )
        if school_id:
            ThreadReadState.objects.using(db_alias).filter(pk=row["id"]).update(school_id=school_id)

    for row in (
        Announcement.objects.using(db_alias)
        .filter(school_id__isnull=True)
        .values("id", "created_by_id")
        .iterator()
    ):
        school_id = _user_school_id(
            row["created_by_id"],
            membership_map=membership_map,
            student_map=student_map,
            teacher_map=teacher_map,
        )
        if school_id:
            Announcement.objects.using(db_alias).filter(pk=row["id"]).update(school_id=school_id)
            announcement_map[row["id"]] = school_id

    for row in (
        AnnouncementAuditLog.objects.using(db_alias)
        .filter(school_id__isnull=True)
        .values("id", "announcement_id", "user_id")
        .iterator()
    ):
        school_id = announcement_map.get(row["announcement_id"]) or _user_school_id(
            row["user_id"],
            membership_map=membership_map,
            student_map=student_map,
            teacher_map=teacher_map,
        )
        if school_id:
            AnnouncementAuditLog.objects.using(db_alias).filter(pk=row["id"]).update(school_id=school_id)

    for row in (
        ContactRequest.objects.using(db_alias)
        .filter(school_id__isnull=True)
        .values("id", "student_id", "parent_id", "assigned_to_id", "triage_owner_id")
        .iterator()
    ):
        school_id = None
        if row["student_id"]:
            school_id = (
                StudentProfile.objects.using(db_alias)
                .filter(pk=row["student_id"])
                .values_list("school_id", flat=True)
                .first()
            )
        school_id = school_id or _user_school_id(
            row["parent_id"],
            membership_map=membership_map,
            student_map=student_map,
            teacher_map=teacher_map,
        )
        school_id = school_id or _user_school_id(
            row["assigned_to_id"],
            membership_map=membership_map,
            student_map=student_map,
            teacher_map=teacher_map,
        )
        school_id = school_id or _user_school_id(
            row["triage_owner_id"],
            membership_map=membership_map,
            student_map=student_map,
            teacher_map=teacher_map,
        )
        if school_id:
            ContactRequest.objects.using(db_alias).filter(pk=row["id"]).update(school_id=school_id)
            contact_request_map[row["id"]] = school_id

    for row in (
        ContactRequestAttachment.objects.using(db_alias)
        .filter(school_id__isnull=True)
        .values("id", "request_id", "uploaded_by_id")
        .iterator()
    ):
        school_id = contact_request_map.get(row["request_id"]) or _user_school_id(
            row["uploaded_by_id"],
            membership_map=membership_map,
            student_map=student_map,
            teacher_map=teacher_map,
        )
        if school_id:
            ContactRequestAttachment.objects.using(db_alias).filter(pk=row["id"]).update(school_id=school_id)

    for row in (
        Message.objects.using(db_alias)
        .filter(school_id__isnull=True)
        .values("id", "sender_id", "recipient_id")
        .iterator()
    ):
        school_id = _user_school_id(
            row["sender_id"],
            membership_map=membership_map,
            student_map=student_map,
            teacher_map=teacher_map,
        ) or _user_school_id(
            row["recipient_id"],
            membership_map=membership_map,
            student_map=student_map,
            teacher_map=teacher_map,
        )
        if school_id:
            Message.objects.using(db_alias).filter(pk=row["id"]).update(school_id=school_id)

    for row in (
        DirectConversation.objects.using(db_alias)
        .filter(school_id__isnull=True)
        .values("id", "user1_id", "user2_id")
        .iterator()
    ):
        school_id = _user_school_id(
            row["user1_id"],
            membership_map=membership_map,
            student_map=student_map,
            teacher_map=teacher_map,
        ) or _user_school_id(
            row["user2_id"],
            membership_map=membership_map,
            student_map=student_map,
            teacher_map=teacher_map,
        )
        if school_id:
            DirectConversation.objects.using(db_alias).filter(pk=row["id"]).update(school_id=school_id)

    for row in (
        AlertRule.objects.using(db_alias)
        .filter(school_id__isnull=True)
        .values("id", "user_id")
        .iterator()
    ):
        school_id = _user_school_id(
            row["user_id"],
            membership_map=membership_map,
            student_map=student_map,
            teacher_map=teacher_map,
        )
        if school_id:
            AlertRule.objects.using(db_alias).filter(pk=row["id"]).update(school_id=school_id)


def enable_communication_rls(apps, schema_editor):
    if not should_apply_rls(connection):
        return
    with connection.cursor() as cursor:
        for table in COMMUNICATION_TABLES:
            policy_name = f"{table}_tenant_isolation"
            cursor.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY;")
            cursor.execute(f"DROP POLICY IF EXISTS {policy_name} ON {table};")
            cursor.execute(
                f"""
                CREATE POLICY {policy_name} ON {table}
                FOR ALL
                USING (
                    current_setting('app.current_school_id', true) IS NULL
                    OR school_id::text = current_setting('app.current_school_id', true)
                )
                WITH CHECK (
                    current_setting('app.current_school_id', true) IS NULL
                    OR school_id::text = current_setting('app.current_school_id', true)
                );
                """
            )


def disable_communication_rls(apps, schema_editor):
    if not should_apply_rls(connection):
        return
    with connection.cursor() as cursor:
        for table in COMMUNICATION_TABLES:
            policy_name = f"{table}_tenant_isolation"
            cursor.execute(f"DROP POLICY IF EXISTS {policy_name} ON {table};")
            cursor.execute(f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY;")


def add_school_id_to_communication_tables(apps, schema_editor):
    """Add school_id to all communication tables; idempotent (duplicate_column)."""
    from django.db import connection
    tables = [
        "communication_alertrule",
        "communication_announcement",
        "communication_announcementauditlog",
        "communication_classannouncement",
        "communication_contactrequest",
        "communication_contactrequestattachment",
        "communication_directconversation",
        "communication_message",
        "communication_messagethread",
        "communication_threadmessage",
        "communication_threadreadstate",
    ]
    with connection.cursor() as cursor:
        if connection.vendor == "postgresql":
            for table in tables:
                cursor.execute(f"""
                    DO $$
                    BEGIN
                        ALTER TABLE {table} ADD COLUMN school_id uuid NULL REFERENCES schools_school(id) ON DELETE CASCADE;
                    EXCEPTION WHEN duplicate_column THEN NULL;
                    END $$;
                """)
                cursor.execute(f"CREATE INDEX IF NOT EXISTS {table}_school_id_idx ON {table} (school_id)")
        else:
            for table in tables:
                cursor.execute(f"PRAGMA table_info({table})")
                cols = [row[1] for row in cursor.fetchall()]
                if "school_id" not in cols:
                    cursor.execute(f"ALTER TABLE {table} ADD COLUMN school_id integer NULL REFERENCES schools_school(id) ON DELETE CASCADE")


def noop_school_id(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('communication', '0008_announcement_audit_log'),
        ('academics', '0031_incident_school_tenant_scope'),
        ('people', '0028_merge_people_conflicting_leaves'),
        ('schools', '0002_enable_rls_postgresql'),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            state_operations=[
                migrations.AddField(
                    model_name='alertrule',
                    name='school',
                    field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name='alert_rules', to='schools.school'),
                ),
                migrations.AddField(
                    model_name='announcement',
                    name='school',
                    field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name='announcements', to='schools.school'),
                ),
                migrations.AddField(
                    model_name='announcementauditlog',
                    name='school',
                    field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name='announcement_audit_logs', to='schools.school'),
                ),
                migrations.AddField(
                    model_name='classannouncement',
                    name='school',
                    field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name='class_announcements', to='schools.school'),
                ),
                migrations.AddField(
                    model_name='contactrequest',
                    name='school',
                    field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name='contact_requests', to='schools.school'),
                ),
                migrations.AddField(
                    model_name='contactrequestattachment',
                    name='school',
                    field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name='contact_request_attachments', to='schools.school'),
                ),
                migrations.AddField(
                    model_name='directconversation',
                    name='school',
                    field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name='direct_conversations', to='schools.school'),
                ),
                migrations.AddField(
                    model_name='message',
                    name='school',
                    field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name='messages', to='schools.school'),
                ),
                migrations.AddField(
                    model_name='messagethread',
                    name='school',
                    field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name='message_threads', to='schools.school'),
                ),
                migrations.AddField(
                    model_name='threadmessage',
                    name='school',
                    field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name='thread_messages', to='schools.school'),
                ),
                migrations.AddField(
                    model_name='threadreadstate',
                    name='school',
                    field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name='thread_read_states', to='schools.school'),
                ),
            ],
            database_operations=[migrations.RunPython(add_school_id_to_communication_tables, noop_school_id)],
        ),
        migrations.RunPython(backfill_communication_school, migrations.RunPython.noop),
        migrations.RunPython(enable_communication_rls, disable_communication_rls),
    ]
