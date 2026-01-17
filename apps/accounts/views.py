from django.contrib import messages
from django.contrib.auth import authenticate, login, logout
from django.shortcuts import redirect, render
from django.urls import reverse


def redirect_view(request):
    """Central post-login redirect based on role.

    Keeping this logic in one place makes LOGIN_REDIRECT_URL reliable and
    prevents hard-coded URLs from drifting.
    """
    user = request.user
    if not user.is_authenticated:
        return redirect(reverse("login"))

    if getattr(user, "role", None) == "TEACHER":
        return redirect("teacher_dashboard")
    if getattr(user, "role", None) == "PARENT":
        return redirect("parent_dashboard")

    # Default: admin
    return redirect("admin:index")

def login_view(request):
    if request.method == "POST":
        user = authenticate(
            request,
            username=request.POST.get("username"),
            password=request.POST.get("password"),
        )
        if user:
            login(request,user)
            return redirect(reverse("accounts:redirect"))

        messages.error(request, "Invalid username or password.")
    return render(request,"auth/login.html")

def logout_view(request):
    logout(request)
    return redirect(reverse("login"))
