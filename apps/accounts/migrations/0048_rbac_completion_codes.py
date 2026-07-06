# Platform-wide RBAC completion (2026-07-05): seed the granular Permission codes that
# previously had no grantable equivalent, so every feature/config/settings surface can be
# gated on a code (additive gate) instead of a bare admin-tier / role-hardcoded check.
#
# Codes added here (payroll.*, grades.*, compliance.*, analytics.view) are granted to
# exactly the roles that already reach those surfaces today, so gating the surface on the
# code reproduces current access AND lets an owner grant the code to a custom role (a
# dedicated bursar/HR/registrar) who is not an ADMIN. Idempotent: get_or_create + additive
# .add() (never .set(), so existing role grants are preserved). Mirrors the 0030 pattern.

from django.db import migrations


NEW_PERMISSIONS = [
    ("payroll.view", "Payroll access", "View payroll runs, payslips, and staff compensation."),
    ("payroll.manage", "Payroll management", "Run payroll cycles, edit compensation, approve payslips."),
    ("grades.enter", "Grade entry", "Enter/edit marks and gradebook results for assigned classes."),
    ("grades.manage", "Grade & exam management", "Configure exam workflows, publish results, manage grade scales."),
    ("analytics.view", "Analytics dashboards", "View analytics / at-risk / performance dashboards."),
    ("compliance.view", "Compliance access", "View compliance, audit-trail, and data-rights dashboards."),
    ("compliance.manage", "Compliance management", "Manage data-rights requests, FERPA/GDPR workflows, retention."),
]

# role_code -> list of new codes to ADD (additive; existing grants untouched). Each list is
# the set of roles that already reach the corresponding surface, so access is preserved.
ROLE_GRANTS = {
    # Payroll: the finance cluster + leadership tier (mirrors MODULE_ACCESS_DEFAULTS["payroll"]).
    "FINANCE_STAFF": ["payroll.view", "payroll.manage", "analytics.view"],
    "BURSAR": ["payroll.view", "payroll.manage", "analytics.view"],
    "ACCOUNTANT": ["payroll.view", "analytics.view"],
    # Grade entry: teachers + academic supervision. Grade/exam management: academic leadership.
    "TEACHER": ["grades.enter", "analytics.view"],
    "HOD": ["grades.enter", "grades.manage", "analytics.view"],
    "DEPT_LEAD": ["grades.enter", "analytics.view"],
    "ACADEMICS_STAFF": ["grades.enter", "analytics.view"],
    "DEAN": ["grades.enter", "grades.manage", "analytics.view"],
    "CENSOR": ["grades.enter"],
    "VICE_PRINCIPAL": [
        "grades.enter", "grades.manage", "analytics.view",
        "compliance.view", "payroll.view",
    ],
    "PRINCIPAL": [
        "payroll.view", "payroll.manage", "grades.enter", "grades.manage",
        "analytics.view", "compliance.view",
    ],
    "LEADERSHIP": [
        "payroll.view", "payroll.manage", "grades.manage",
        "analytics.view", "compliance.view",
    ],
    "PROPRIETOR": ["payroll.view", "analytics.view", "compliance.view"],
    # Data protection officer owns the compliance surface.
    "DPO": ["compliance.view", "compliance.manage"],
    "IT_ADMIN": ["compliance.view", "compliance.manage", "analytics.view"],
    # Administrators / super get every new code.
    "ADMIN": [c for c, _, _ in NEW_PERMISSIONS],
    "SUPERADMIN": [c for c, _, _ in NEW_PERMISSIONS],
}


def forwards(apps, schema_editor):
    Permission = apps.get_model("accounts", "Permission")
    AccessRole = apps.get_model("accounts", "AccessRole")

    perm_map = {p.code: p for p in Permission.objects.all()}
    for code, name, description in NEW_PERMISSIONS:
        if code not in perm_map:
            perm_map[code] = Permission.objects.create(
                code=code, name=name, description=description
            )

    for role_code, codes in ROLE_GRANTS.items():
        # There may be BOTH a global template row (school__isnull=True) and per-school
        # catalog rows for a role code; grant to all of them.
        for role in AccessRole.objects.filter(code=role_code):
            for c in codes:
                perm = perm_map.get(c)
                if perm is not None:
                    role.permissions.add(perm)


class Migration(migrations.Migration):
    dependencies = [
        ("accounts", "0047_rolegroup"),
    ]

    operations = [
        migrations.RunPython(forwards, migrations.RunPython.noop),
    ]
