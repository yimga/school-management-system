"""
django-defender integration (plan 3.21): get username from login request for lockout.
Only used when DEFENDER_ENABLED=1 and defender is installed.
"""


def get_username_from_request(request):
    """Return username/email from login form for defender lockout by IP or username."""
    return (
        (request.POST.get("username") or request.POST.get("email") or "").strip()
        if request.method == "POST"
        else ""
    )
