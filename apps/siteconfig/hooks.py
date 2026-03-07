"""
Canonical hook registry for Request-to-Feature / FeatureFragment (plan 3.20, Powerhouse).
Use these names in templates as {% tenant_hook 'HOOK_NAME' %} and in admin when creating FeatureFragments.
"""

# Hook names must be UPPERCASE; stored and compared in upper case in tenant_hook tag.
HOOK_REGISTRY = [
    "STUDENT_PROFILE_SIDEBAR",
    "STUDENT_LIST_FOOTER",
    "GRADEBOOK_CONTROLS",
    "GRADEBOOK_CARD_FOOTER",
    "FINANCE_DASHBOARD_EXTRA",
    "FINANCE_SUMMARY_FOOTER",
    "BILLING_EXTRA",
    "CARD_FOOTER",
]

# For admin dropdown and docs: (value, label)
HOOK_CHOICES = [
    ("STUDENT_PROFILE_SIDEBAR", "Student profile sidebar"),
    ("STUDENT_LIST_FOOTER", "Student list card footer"),
    ("GRADEBOOK_CONTROLS", "Gradebook controls (header)"),
    ("GRADEBOOK_CARD_FOOTER", "Gradebook card footer"),
    ("FINANCE_DASHBOARD_EXTRA", "Finance dashboard extra"),
    ("FINANCE_SUMMARY_FOOTER", "Finance summary footer"),
    ("BILLING_EXTRA", "Billing / invoice extra"),
    ("CARD_FOOTER", "Generic card footer"),
]


def get_hook_choices():
    """Return choices for model/admin; allows dynamic extension."""
    return HOOK_CHOICES
