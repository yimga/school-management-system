# Repair AccessRole.permission M2M when roles exist but permissions were never linked
# (e.g. empty DB after partial seed). Idempotent: mirrors 0004 + 0008 + 0014 + 0017 data steps.

from django.db import migrations


def forwards(apps, schema_editor):
    Permission = apps.get_model("accounts", "Permission")
    AccessRole = apps.get_model("accounts", "AccessRole")

    # --- From 0004_expand_role_templates (permissions + core roles) ---
    permission_definitions = [
        ("attendance.view", "Attendance dashboards", "View attendance dashboards and logs."),
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

    role_definitions = {
        "ADMIN": {
            "name": "Administrator",
            "description": "Full access to analytics, finance, attendance, reports, and settings.",
            "permissions": [c for c, _, _ in permission_definitions],
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

    perm_map = {}
    for code, name, description in permission_definitions:
        perm, _ = Permission.objects.get_or_create(
            code=code,
            defaults={"name": name, "description": description},
        )
        perm_map[code] = perm

    for role_code, data in role_definitions.items():
        role, _ = AccessRole.objects.get_or_create(
            code=role_code,
            defaults={"name": data["name"], "description": data["description"]},
        )
        perms = [
            perm_map[c] for c in data["permissions"] if c in perm_map
        ]
        role.permissions.set(perms)

    # --- From 0008_extended_roles_permissions ---
    perm_map = {p.code: p for p in Permission.objects.all()}
    all_codes = list(perm_map.keys())
    extended = {
        "SUPERADMIN": {
            "name": "Super Administrator",
            "description": "Full control over all modules and settings.",
            "permissions": all_codes,
        },
        "DEPT_LEAD": {
            "name": "Department Lead",
            "description": "Oversees department academics and reporting.",
            "permissions": [
                "reports.manage",
                "attendance.manage",
                "portal.manage",
                "data.access",
            ],
        },
        "FINANCE_STAFF": {
            "name": "Finance Staff",
            "description": "Handles finance dashboards, invoices, and payments.",
            "permissions": [
                "finance.view",
                "finance.manage",
                "reports.manage",
                "data.access",
            ],
        },
        "ACADEMICS_STAFF": {
            "name": "Academics Staff",
            "description": "Supports academics, attendance, and reporting.",
            "permissions": [
                "reports.manage",
                "attendance.manage",
                "portal.manage",
                "data.access",
            ],
        },
        "COMMS_STAFF": {
            "name": "Communications Staff",
            "description": "Manages announcements and portal communications.",
            "permissions": ["communication.manage", "portal.manage"],
        },
    }
    for code, data in extended.items():
        role, _ = AccessRole.objects.get_or_create(
            code=code,
            defaults={"name": data["name"], "description": data["description"]},
        )
        perms = [perm_map[p] for p in data["permissions"] if p in perm_map]
        if perms:
            role.permissions.set(perms)

    # --- From 0014_secretary_ea_va_roles ---
    sec_roles = {
        "SECRETARY": {
            "name": "Secretary",
            "description": "Front office, communications, and portal support.",
            "permissions": ["portal.manage", "communication.manage", "reports.manage"],
        },
        "EXECUTIVE_ASSISTANT": {
            "name": "Executive Assistant",
            "description": "Supports leadership with communications and portal access.",
            "permissions": ["portal.manage", "communication.manage", "reports.manage"],
        },
        "VIRTUAL_ASSISTANT": {
            "name": "Virtual Assistant",
            "description": "Remote support for communications and portal.",
            "permissions": ["portal.manage", "communication.manage", "reports.manage"],
        },
    }
    perm_map = {p.code: p for p in Permission.objects.all()}
    for code, data in sec_roles.items():
        role, _ = AccessRole.objects.get_or_create(
            code=code,
            defaults={"name": data["name"], "description": data["description"]},
        )
        perms = [perm_map[p] for p in data["permissions"] if p in perm_map]
        if perms:
            role.permissions.set(perms)

    # --- From 0017 (new permissions + roles + additions) ---
    new_permissions = [
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
    perm_map = {p.code: p for p in Permission.objects.all()}
    for code, name, description in new_permissions:
        if code not in perm_map:
            perm = Permission.objects.create(
                code=code, name=name, description=description
            )
            perm_map[code] = perm

    new_role_definitions = {
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
    for code, data in new_role_definitions.items():
        role, _ = AccessRole.objects.get_or_create(
            code=code,
            defaults={"name": data["name"], "description": data["description"]},
        )
        perms = [perm_map[p] for p in data["permissions"] if p in perm_map]
        if perms:
            role.permissions.set(perms)

    additions = {
        "DEAN": ["exam_registration.manage"],
        "SECRETARY": ["exam_registration.manage", "student.manage"],
        "CENSOR": ["discipline.manage"],
        "BURSAR": ["student.manage"],
        "LEADERSHIP": ["strategic.report"],
        "ADMIN": ["strategic.report"],
    }
    for role_code, perm_codes in additions.items():
        role = AccessRole.objects.filter(code=role_code).first()
        if not role:
            continue
        for pc in perm_codes:
            p = perm_map.get(pc)
            if p:
                role.permissions.add(p)


class Migration(migrations.Migration):
    dependencies = [
        ("accounts", "0029_ensure_access_roles_for_templates"),
    ]

    operations = [
        migrations.RunPython(forwards, migrations.RunPython.noop),
    ]
