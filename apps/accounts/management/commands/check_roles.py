from django.core.management import BaseCommand

from apps.accounts.models import AccessRole, Permission, User


class Command(BaseCommand):
    help = "Audit roles and permissions for gaps or unused entries."

    def handle(self, *args, **options):
        roles = AccessRole.objects.all().prefetch_related("permissions")
        perms = Permission.objects.all()

        empty_roles = [r for r in roles if r.permissions.count() == 0]
        unused_perms = [p for p in perms if not p.roles.exists() and not p.users.exists()]

        self.stdout.write(self.style.MIGRATE_HEADING("Access role audit"))
        if empty_roles:
            for r in empty_roles:
                self.stdout.write(self.style.WARNING(f"Role '{r.code}' has no permissions assigned."))
        else:
            self.stdout.write(self.style.SUCCESS("All roles have at least one permission."))

        self.stdout.write(self.style.MIGRATE_HEADING("Permission usage audit"))
        if unused_perms:
            for p in unused_perms:
                self.stdout.write(self.style.WARNING(f"Permission '{p.code}' is not assigned to any role/user."))
        else:
            self.stdout.write(self.style.SUCCESS("All permissions are assigned to a role or user."))

        self.stdout.write(self.style.MIGRATE_HEADING("User role coverage"))
        no_role = User.objects.filter(is_superuser=False, roles__isnull=True, feature_permissions__isnull=True).distinct()
        if no_role.exists():
            for u in no_role:
                self.stdout.write(self.style.WARNING(f"User '{u.username}' has no roles or feature permissions."))
        else:
            self.stdout.write(self.style.SUCCESS("All non-superusers have at least one role or permission."))
