from django.db import migrations


PERMISSION_DEFINITIONS = [
    (
        "attendance.view",
        "Attendance dashboards",
        "View attendance dashboards and logs.",
    ),
    (
        "attendance.manage",
        "Attendance management",
        "Create/dismiss attendance records and discipline logs.",
    ),
    (
        "finance.view",
        "Finance access",
        "View finance dashboards, invoices, and payments.",
    ),
    (
        "finance.manage",
        "Finance management",
        "Manage invoices, payments, and debtors lists.",
    ),
    (
        "reports.manage",
        "Reports & exports",
        "Generate reports/exports (PDF/CSV) and promotion data.",
    ),
    ("data.access", "Data exports", "Export student/staff data across portals."),
    (
        "settings.manage",
        "Backend configuration",
        "Manage site-wide settings, customizer, and RBAC.",
    ),
    (
        "portal.manage",
        "Portal features",
        "Control portal modules, invites, and communication assets.",
    ),
    (
        "student.manage",
        "Student control",
        "Manage student profiles, referrals, and dashboards.",
    ),
    (
        "communication.manage",
        "Communication center",
        "Send broadcasts, owner notifications, and reminders.",
    ),
]

ROLE_DEFINITIONS = {
    "ADMIN": {
        "name": "Administrator",
        "description": "Full access to analytics, finance, attendance, reports, and settings.",
        "permissions": [perm_code for perm_code, _, _ in PERMISSION_DEFINITIONS],
    },
    "PRINCIPAL": {
        "name": "Principal",
        "description": "Ultimate authority; approves reports, controls finance, and monitors attendance.",
        "permissions": [
            "attendance.manage",
            "finance.manage",
            "reports.manage",
            "data.access",
            "settings.manage",
            "portal.manage",
        ],
    },
    "VICE_PRINCIPAL": {
        "name": "Vice Principal",
        "description": "Oversees daily operations and staff, plus performance reports.",
        "permissions": ["attendance.manage", "reports.manage", "portal.manage"],
    },
    "DEAN": {
        "name": "Dean",
        "description": "Curriculum oversight and exam coordination.",
        "permissions": ["attendance.manage", "reports.manage"],
    },
    "CENSOR": {
        "name": "Censor",
        "description": "Discipline and attendance records, emergency contact access.",
        "permissions": ["attendance.manage", "student.manage"],
    },
    "BURSAR": {
        "name": "Bursar",
        "description": "Financial oversight and invoicing.",
        "permissions": ["finance.view", "finance.manage", "reports.manage"],
    },
    "HOD": {
        "name": "Head of Department",
        "description": "Departmental supervision and marks validation.",
        "permissions": ["reports.manage", "data.access"],
    },
    "TEACHER": {
        "name": "Teacher",
        "description": "Classroom delivery, assessment entry, and attendance insights.",
        "permissions": ["attendance.manage", "reports.manage", "portal.manage"],
    },
    "IT_ADMIN": {
        "name": "IT Administrator",
        "description": "Manages system configuration, backups, and privacy settings.",
        "permissions": [
            "settings.manage",
            "portal.manage",
            "data.access",
            "communication.manage",
        ],
    },
    "BOARDING_MANAGER": {
        "name": "Boarding Manager",
        "description": "Dormitory logistics, health logs, and non-academic attendance.",
        "permissions": ["attendance.manage", "communication.manage", "portal.manage"],
    },
    "PARENT": {
        "name": "Parent",
        "description": "Access to finance, reports, and portal alerts for linked students.",
        "permissions": ["finance.view", "reports.manage", "portal.manage"],
    },
    "STUDENT": {
        "name": "Student",
        "description": "Personal dashboard, limited results, and assignment submissions.",
        "permissions": ["reports.manage"],
    },
    "LEADERSHIP": {
        "name": "Leadership",
        "description": "Strategic dashboards for finance, attendance, and reports.",
        "permissions": [
            "attendance.manage",
            "finance.manage",
            "reports.manage",
            "data.access",
        ],
    },
}


def create_roles(apps, schema_editor):
    Permission = apps.get_model("accounts", "Permission")
    AccessRole = apps.get_model("accounts", "AccessRole")

    perm_map = {}
    for code, name, description in PERMISSION_DEFINITIONS:
        perm, _ = Permission.objects.get_or_create(
            code=code,
            defaults={"name": name, "description": description},
        )
        perm_map[code] = perm

    for role_code, data in ROLE_DEFINITIONS.items():
        role, _ = AccessRole.objects.get_or_create(
            code=role_code,
            defaults={"name": data["name"], "description": data["description"]},
        )
        perms = [
            perm_map[perm_code]
            for perm_code in data["permissions"]
            if perm_code in perm_map
        ]
        role.permissions.set(perms)


class Migration(migrations.Migration):
    dependencies = [
        ("accounts", "0003_default_roles_permissions"),
    ]

    operations = [migrations.RunPython(create_roles, migrations.RunPython.noop)]
