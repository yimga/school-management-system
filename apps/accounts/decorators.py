from django.contrib.auth.decorators import user_passes_test

def role_required(*roles: str):
    def check(user):
        return user.is_authenticated and getattr(user, "role", None) in roles
    return user_passes_test(check)

