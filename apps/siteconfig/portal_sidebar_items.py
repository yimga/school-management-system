"""
Build portal sidebar nav items for the current user.
Optionally sorted by SiteSettings.portal_sidebar_order when present.
Used by context processor to pass PORTAL_SIDEBAR_ITEMS to templates.
"""
from django.urls import reverse, NoReverseMatch


# Item id -> (section, label, url_name, icon, roles that can see it)
# roles: None = all authenticated, or list e.g. ['TEACHER'], ['PARENT'], ['ADMIN', 'staff']
SIDEBAR_ITEM_SPECS = [
    ("dashboard", "Home", "Dashboard", "accounts:redirect", "bi-speedometer2", None),
    ("profile", "Account", "My Profile", "accounts:user_profile", "bi-person", None),
    ("preferences", "Account", "Preferences", "siteconfig:user_preferences", "bi-sliders", None),
    ("notifications", "Account", "Notifications", "accounts:user_notifications", "bi-bell", None),
    ("kb", "Account", "Knowledge Base", "kb:kb_home", "bi-journal-text", None),
    # Communication - teacher
    ("messages", "Communication", "Messages", "accounts:user_messages", "bi-chat-dots", ["TEACHER", "ADMIN", "staff"]),
    ("message_groups", "Communication", "Message Groups", "communication:group_list", "bi-people", ["TEACHER", "ADMIN", "staff"]),
    # Communication - parent
    ("contact_school", "Communication", "Contact School", "portal:parent_contact_school", "bi-envelope-paper", ["PARENT"]),
    # Communication - admin
    ("announcements", "Communication", "Announcements", "communication:announcement_create", "bi-megaphone", ["ADMIN", "staff"]),
    # Teacher workflow
    ("teacher_workflow", "My Workflow", "My Workflow", "portal:teacher_workflow", "bi-diagram-3", ["TEACHER"]),
    ("marks_entry", "Learning Management", "Enter Marks", "evals:teacher_marks_entry", "bi-pencil-square", ["TEACHER"]),
    ("marks_list", "Learning Management", "Marks History", "evals:teacher_marks_list", "bi-table", ["TEACHER"]),
    ("attendance", "Learning Management", "Attendance", "portal:teacher_attendance", "bi-clipboard-check", ["TEACHER"]),
    ("payslips", "Human Resources", "Payslips", "payroll:employee_payslips", "bi-wallet2", ["TEACHER"]),
    ("leave", "Human Resources", "Leave Requests", "payroll:employee_leave", "bi-calendar-check", ["TEACHER"]),
    ("pay_history", "Human Resources", "Pay History", "payroll:employee_payslips", "bi-receipt", ["TEACHER"]),
    # Parent workflow
    ("parent_workflow", "My Workflow", "My Workflow", "portal:parent_workflow", "bi-diagram-3", ["PARENT"]),
    ("my_children", "Children & Learning", "My Children", "portal:parent_dashboard", "bi-people", ["PARENT"]),
    ("finance", "Children & Learning", "Finance & Fees", "portal:parent_finance", "bi-cash-coin", ["PARENT"]),
    ("link_child", "Children & Learning", "Link Child", "portal:link_child", "bi-person-plus", ["PARENT"]),
    ("claim_invite", "Children & Learning", "Claim Invite", "portal:claim_invite", "bi-ticket", ["PARENT"]),
    ("portal_stats", "Performance Tracking", "Academic Stats", "portal:portal_stats", "bi-graph-up", ["PARENT"]),
    # Staff / admin
    ("backend", "Admin Panel", "Backend Console", "accounts:backend_dashboard", "bi-gear-fill", ["ADMIN", "staff"]),
    ("workflow_center", "Admin Panel", "Workflow Center", "accounts:workflow_center", "bi-diagram-3", ["ADMIN", "staff"]),
    ("students", "People & Access", "Student Profiles", "admin:people_studentprofile_changelist", "bi-person-lines-fill", ["ADMIN", "staff"]),
    ("guardians", "People & Access", "Student Guardians", "admin:people_studentguardian_changelist", "bi-people-fill", ["ADMIN", "staff"]),
    ("auth_groups", "People & Access", "Authentication Groups", "admin:auth_group_changelist", "bi-unlock", ["ADMIN", "staff"]),
    ("rbac", "People & Access", "RBAC & Access Control", "accounts:rbac", "bi-diagram-3", ["ADMIN", "staff"]),
    ("eval_admin", "Academic Management", "Evaluation Admin", "evals:evaluation_admin", "bi-clipboard-data", ["ADMIN", "staff"]),
    ("class_ranking", "Academic Management", "Class Ranking", "evals:class_ranking", "bi-trophy", ["ADMIN", "staff"]),
    ("school_ranking", "Academic Management", "School Ranking", "evals:school_ranking", "bi-bar-chart-line", ["ADMIN", "staff"]),
    ("publish_results", "Academic Management", "Publish Results", "reports:publish_term_results", "bi-megaphone", ["ADMIN", "staff"]),
    ("finance_dashboard", "Financial Management", "Finance Dashboard", "finance:dashboard", "bi-currency-exchange", ["ADMIN", "staff"]),
    ("payroll", "Financial Management", "Payroll", "payroll:dashboard", "bi-cash-stack", ["ADMIN", "staff"]),
    ("analytics", "Analytics & Reports", "Analytics", "analytics:dashboard", "bi-graph-up-arrow", ["ADMIN", "staff"]),
    ("report_library", "Analytics & Reports", "Report Library", "siteconfig:report_library", "bi-journal-text", ["ADMIN", "staff"]),
    ("reportcard_builder", "Analytics & Reports", "Report Card Builder", "siteconfig:reportcard_builder", "bi-file-earmark-richtext", ["ADMIN", "staff"]),
]


def build_portal_sidebar_items(request, site):
    """
    Build ordered list of sidebar items for the current user.
    If site.portal_sidebar_order is set (list of item ids), sort by that order;
    otherwise use default order. Only includes items the user's role can see.
    """
    if not getattr(request, "user", None) or not request.user.is_authenticated:
        return []

    user = request.user
    role = (getattr(user, "role", "") or "").upper()
    is_staff = getattr(user, "is_staff", False)
    is_superuser = getattr(user, "is_superuser", False)
    staff_like = is_staff or is_superuser or role == "ADMIN"

    def can_see(roles):
        if roles is None:
            return True
        if "staff" in roles and staff_like:
            return True
        if role in roles:
            return True
        return False

    items_with_urls = []
    for item_id, section, label, url_name, icon, roles in SIDEBAR_ITEM_SPECS:
        if not can_see(roles):
            continue
        try:
            url = reverse(url_name)
        except NoReverseMatch:
            continue
        badge = None
        if url_name == "accounts:user_messages" and getattr(request, "messages_unread_count", None):
            badge = request.messages_unread_count
        items_with_urls.append({
            "id": item_id,
            "section": section,
            "label": label,
            "url": url,
            "icon": icon,
            "badge": badge,
        })

    order = getattr(site, "portal_sidebar_order", None) or []
    if isinstance(order, list) and order:
        id_to_item = {item["id"]: item for item in items_with_urls}
        ordered = []
        for id_ in order:
            if id_ in id_to_item:
                ordered.append(id_to_item.pop(id_))
        for item in items_with_urls:
            if item["id"] in id_to_item:
                ordered.append(item)
        return ordered
    return items_with_urls
