"""
Build portal sidebar nav items for the current user, optionally sorted by SiteSettings.portal_sidebar_order.
"""
from django.urls import reverse
from django.contrib.auth import get_user_model

User = get_user_model()


def _safe_reverse(url_name, kwargs=None, default=None):
    try:
        return reverse(url_name, kwargs=kwargs or {})
    except Exception:
        return default


def build_portal_sidebar_items(request, site):
    """
    Return a list of sidebar items {id, label, url, icon, section, badge} for the current user.
    If site.portal_sidebar_order is non-empty, sort items so that IDs in that list come first in that order,
    then append any remaining items in their original order.
    """
    if not request or not request.user.is_authenticated:
        return []
    user = request.user
    role = (getattr(user, "role", "") or "").upper()
    is_staff = getattr(user, "is_staff", False)
    is_superuser = getattr(user, "is_superuser", False)
    messages_unread_count = getattr(request, "messages_unread_count", None)

    items = []

    # --- Home ---
    items.append({"id": "dashboard", "label": "Dashboard", "url": _safe_reverse("accounts:redirect"), "icon": "bi-speedometer2", "section": "Home", "badge": None})
    # --- Account ---
    items.append({"id": "profile", "label": "My Profile", "url": _safe_reverse("accounts:user_profile"), "icon": "bi-person", "section": "Account", "badge": None})
    items.append({"id": "preferences", "label": "Preferences", "url": _safe_reverse("siteconfig:user_preferences"), "icon": "bi-sliders", "section": "Account", "badge": None})
    items.append({"id": "notifications", "label": "Notifications", "url": _safe_reverse("accounts:user_notifications"), "icon": "bi-bell", "section": "Account", "badge": None})
    items.append({"id": "kb", "label": "Knowledge Base", "url": _safe_reverse("kb:kb_home"), "icon": "bi-journal-text", "section": "Account", "badge": None})

    # --- Communication (role-dependent) ---
    if role == "TEACHER":
        items.append({"id": "messages", "label": "Messages", "url": _safe_reverse("accounts:user_messages"), "icon": "bi-chat-dots", "section": "Communication", "badge": messages_unread_count})
        items.append({"id": "message_groups", "label": "Message Groups", "url": _safe_reverse("communication:group_list"), "icon": "bi-people", "section": "Communication", "badge": None})
    elif role == "PARENT":
        items.append({"id": "contact_school", "label": "Contact School", "url": _safe_reverse("portal:parent_contact_school"), "icon": "bi-envelope-paper", "section": "Communication", "badge": None})
    elif is_staff or is_superuser or role in ("ADMIN", "LEADERSHIP", "IT_ADMIN"):
        items.append({"id": "messages", "label": "Messages", "url": _safe_reverse("accounts:user_messages"), "icon": "bi-chat-dots", "section": "Communication", "badge": messages_unread_count})
        items.append({"id": "message_groups", "label": "Message Groups", "url": _safe_reverse("communication:group_list"), "icon": "bi-people", "section": "Communication", "badge": None})
        items.append({"id": "announcements", "label": "Announcements", "url": _safe_reverse("communication:announcement_create"), "icon": "bi-megaphone", "section": "Communication", "badge": None})

    # --- Teacher ---
    if role == "TEACHER":
        items.append({"id": "teacher_workflow", "label": "My Workflow", "url": _safe_reverse("portal:teacher_workflow"), "icon": "bi-diagram-3", "section": "My Workflow", "badge": None})
        items.append({"id": "marks_entry", "label": "Enter Marks", "url": _safe_reverse("evals:teacher_marks_entry"), "icon": "bi-pencil-square", "section": "Learning Management", "badge": None})
        items.append({"id": "marks_list", "label": "Marks History", "url": _safe_reverse("evals:teacher_marks_list"), "icon": "bi-table", "section": "Learning Management", "badge": None})
        items.append({"id": "attendance", "label": "Attendance", "url": _safe_reverse("portal:teacher_attendance"), "icon": "bi-clipboard-check", "section": "Learning Management", "badge": None})
        items.append({"id": "payslips", "label": "Payslips", "url": _safe_reverse("payroll:employee_payslips"), "icon": "bi-wallet2", "section": "Human Resources", "badge": None})
        items.append({"id": "leave", "label": "Leave Requests", "url": _safe_reverse("payroll:employee_leave"), "icon": "bi-calendar-check", "section": "Human Resources", "badge": None})
        items.append({"id": "pay_history", "label": "Pay History", "url": _safe_reverse("payroll:employee_payslips"), "icon": "bi-receipt", "section": "Human Resources", "badge": None})

    # --- Parent ---
    if role == "PARENT":
        items.append({"id": "parent_workflow", "label": "My Workflow", "url": _safe_reverse("portal:parent_workflow"), "icon": "bi-diagram-3", "section": "My Workflow", "badge": None})
        items.append({"id": "my_children", "label": "My Children", "url": _safe_reverse("portal:parent_dashboard"), "icon": "bi-people", "section": "Children & Learning", "badge": None})
        items.append({"id": "finance", "label": "Finance & Fees", "url": _safe_reverse("portal:parent_finance"), "icon": "bi-cash-coin", "section": "Children & Learning", "badge": None})
        items.append({"id": "link_child", "label": "Link Child", "url": _safe_reverse("portal:link_child"), "icon": "bi-person-plus", "section": "Children & Learning", "badge": None})
        items.append({"id": "claim_invite", "label": "Claim Invite", "url": _safe_reverse("portal:claim_invite"), "icon": "bi-ticket", "section": "Children & Learning", "badge": None})
        items.append({"id": "academic_stats", "label": "Academic Stats", "url": _safe_reverse("portal:portal_stats"), "icon": "bi-graph-up", "section": "Performance Tracking", "badge": None})

    # --- Admin / Staff ---
    if is_staff or is_superuser or role in ("ADMIN", "LEADERSHIP", "IT_ADMIN"):
        items.append({"id": "backend", "label": "Backend Console", "url": _safe_reverse("accounts:backend_dashboard"), "icon": "bi-gear-fill", "section": "Admin Panel", "badge": None})
        items.append({"id": "workflow_center", "label": "Workflow Center", "url": _safe_reverse("accounts:workflow_center"), "icon": "bi-diagram-3", "section": "Admin Panel", "badge": None})
        items.append({"id": "students", "label": "Student Profiles", "url": _safe_reverse("admin:people_studentprofile_changelist"), "icon": "bi-person-lines-fill", "section": "People & Access", "badge": None})
        items.append({"id": "guardians", "label": "Student Guardians", "url": _safe_reverse("admin:people_studentguardian_changelist"), "icon": "bi-people-fill", "section": "People & Access", "badge": None})
        items.append({"id": "groups", "label": "Authentication Groups", "url": _safe_reverse("admin:auth_group_changelist"), "icon": "bi-unlock", "section": "People & Access", "badge": None})
        items.append({"id": "rbac", "label": "RBAC & Access Control", "url": _safe_reverse("accounts:rbac"), "icon": "bi-diagram-3", "section": "People & Access", "badge": None})
        items.append({"id": "eval_admin", "label": "Evaluation Admin", "url": _safe_reverse("evals:evaluation_admin"), "icon": "bi-clipboard-data", "section": "Academic Management", "badge": None})
        items.append({"id": "class_ranking", "label": "Class Ranking", "url": _safe_reverse("evals:class_ranking"), "icon": "bi-trophy", "section": "Academic Management", "badge": None})
        items.append({"id": "school_ranking", "label": "School Ranking", "url": _safe_reverse("evals:school_ranking"), "icon": "bi-bar-chart-line", "section": "Academic Management", "badge": None})
        items.append({"id": "publish_results", "label": "Publish Results", "url": _safe_reverse("reports:publish_term_results"), "icon": "bi-megaphone", "section": "Academic Management", "badge": None})
        items.append({"id": "finance_dashboard", "label": "Finance Dashboard", "url": _safe_reverse("finance:dashboard"), "icon": "bi-currency-exchange", "section": "Financial Management", "badge": None})
        items.append({"id": "payroll", "label": "Payroll", "url": _safe_reverse("payroll:dashboard"), "icon": "bi-cash-stack", "section": "Financial Management", "badge": None})
        items.append({"id": "analytics", "label": "Analytics", "url": _safe_reverse("analytics:dashboard"), "icon": "bi-graph-up-arrow", "section": "Analytics & Reports", "badge": None})
        items.append({"id": "report_library", "label": "Report Library", "url": _safe_reverse("siteconfig:report_library"), "icon": "bi-journal-text", "section": "Analytics & Reports", "badge": None})
        items.append({"id": "reportcard_builder", "label": "Report Card Builder", "url": _safe_reverse("siteconfig:reportcard_builder"), "icon": "bi-file-earmark-richtext", "section": "Analytics & Reports", "badge": None})

    # Drop items with no URL
    items = [x for x in items if x.get("url")]

    # Sort by portal_sidebar_order if set
    order = getattr(site, "portal_sidebar_order", None) or []
    if isinstance(order, list) and len(order) > 0:
        id_to_item = {x["id"]: x for x in items}
        ordered_ids = [x for x in order if isinstance(x, str) and x.strip() and x.strip() in id_to_item]
        remaining = [x for x in items if x["id"] not in ordered_ids]
        items = [id_to_item[i] for i in ordered_ids] + remaining

    return items
