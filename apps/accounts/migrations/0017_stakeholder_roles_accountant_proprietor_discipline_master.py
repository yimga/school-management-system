# Stakeholder roles: ACCOUNTANT, PROPRIETOR, DISCIPLINE_MASTER (additive only; do not remove existing)

from django.db import migrations, models


# New permission codes to create (additive; do not remove existing Permission rows)
NEW_PERMISSIONS = [
    (
        "discipline.manage",
        "Discipline management",
        "Create/edit incidents, trigger parent alerts for discipline/absence.",
    ),
    (
        "accounting.view",
        "Accounting view",
        "View Bursar entries, expense reports, budget vs actual.",
    ),
    (
        "accounting.manage",
        "Accounting management",
        "Record expenditures, reconcile Bursar entries.",
    ),
    ("stock.view", "Stock view", "View inventory/stock."),
    ("stock.manage", "Stock management", "Manage stock/inventory."),
    (
        "strategic.report",
        "Strategic reporting",
        "Access strategic reporting and school roadmap view.",
    ),
    ("exam_registration.manage", "Exam registration", "GCE/Baccalauréat registration."),
]

# New AccessRoles only (additive; do not alter existing AccessRole rows)
NEW_ROLE_DEFINITIONS = {
    "ACCOUNTANT": {
        "name": "Accountant",
        "description": "Reporting and expense management; tracks Bursar entries; expenditures vs budget; stock control.",
        "permissions": [
            "accounting.view",
            "accounting.manage",
            "stock.view",
            "stock.manage",
            "finance.view",
        ],
    },
    "PROPRIETOR": {
        "name": "Proprietor",
        "description": "Strategic reporting, super user, global dashboards, enrollment data, report card printing.",
        "permissions": [
            "strategic.report",
            "reports.manage",
            "student.manage",
            "finance.view",
            "data.access",
        ],
    },
    "DISCIPLINE_MASTER": {
        "name": "Discipline Master",
        "description": "Disciplinary Dept.: incidents (tardiness, behavior), parent notifications for absences/discipline.",
        "permissions": ["discipline.manage", "attendance.manage", "student.manage"],
    },
}

# Existing roles to which we ADD new permissions only (never remove existing)
EXISTING_ROLE_PERMISSION_ADDITIONS = {
    "DEAN": ["exam_registration.manage"],
    "SECRETARY": ["exam_registration.manage", "student.manage"],
    "CENSOR": ["discipline.manage"],
    "BURSAR": ["student.manage"],
    "LEADERSHIP": ["strategic.report"],
    "ADMIN": ["strategic.report"],
}


def create_permissions_and_roles(apps, schema_editor):
    Permission = apps.get_model("accounts", "Permission")
    AccessRole = apps.get_model("accounts", "AccessRole")

    # 1. Create new Permission rows only (additive)
    perm_map = {p.code: p for p in Permission.objects.all()}
    for code, name, description in NEW_PERMISSIONS:
        if code not in perm_map:
            perm = Permission.objects.create(
                code=code, name=name, description=description
            )
            perm_map[code] = perm

    # 2. Create new AccessRole rows for ACCOUNTANT, PROPRIETOR, DISCIPLINE_MASTER only
    for code, data in NEW_ROLE_DEFINITIONS.items():
        role, created = AccessRole.objects.get_or_create(
            code=code,
            defaults={"name": data["name"], "description": data["description"]},
        )
        perms = [perm_map[p] for p in data["permissions"] if p in perm_map]
        if perms:
            role.permissions.set(perms)

    # 3. For existing roles: ADD new permissions only (do not remove any existing)
    for role_code, perm_codes in EXISTING_ROLE_PERMISSION_ADDITIONS.items():
        role = AccessRole.objects.filter(code=role_code).first()
        if not role:
            continue
        to_add = [perm_map[p] for p in perm_codes if p in perm_map]
        for perm in to_add:
            role.permissions.add(perm)


def noop(apps, schema_editor):
    pass


class Migration(migrations.Migration):
    dependencies = [
        ("accounts", "0016_add_delegation_and_action_log"),
    ]

    operations = [
        migrations.AlterField(
            model_name="user",
            name="role",
            field=models.CharField(
                choices=[
                    ("SUPERADMIN", "Super Administrator"),
                    ("ADMIN", "Administrator"),
                    ("LEADERSHIP", "Leadership"),
                    ("PRINCIPAL", "Principal"),
                    ("VICE_PRINCIPAL", "Vice Principal"),
                    ("DEAN", "Dean"),
                    ("CENSOR", "Censor"),
                    ("BURSAR", "Bursar"),
                    ("HOD", "Head of Department"),
                    ("DEPT_LEAD", "Department Lead"),
                    ("FINANCE_STAFF", "Finance Staff"),
                    ("ACADEMICS_STAFF", "Academics Staff"),
                    ("COMMS_STAFF", "Communications Staff"),
                    ("SECRETARY", "Secretary"),
                    ("EXECUTIVE_ASSISTANT", "Executive Assistant"),
                    ("VIRTUAL_ASSISTANT", "Virtual Assistant"),
                    ("TEACHER", "Teacher"),
                    ("IT_ADMIN", "IT Administrator"),
                    ("BOARDING_MANAGER", "Boarding Manager"),
                    ("ACCOUNTANT", "Accountant"),
                    ("PROPRIETOR", "Proprietor"),
                    ("DISCIPLINE_MASTER", "Discipline Master"),
                    ("PARENT", "Parent"),
                    ("STUDENT", "Student"),
                ],
                default="PARENT",
                max_length=20,
            ),
        ),
        migrations.RunPython(create_permissions_and_roles, noop),
    ]
