# User accounts and admin login

Same user accounts work in two places:

| Where | URL | Use |
|-------|-----|-----|
| **Portal / Backend dashboard** | `/authentication/login/` | Staff, teachers, parents, students |
| **Django Admin (config)** | `/admin/` (login at `/admin/login/`) | Superuser only |

Use **username** and **password** (not email) to sign in at both.

---

## When credentials “don’t work”

### 1. No users yet (e.g. after migrations or fresh DB)

Create a superuser:

```bash
python manage.py ensure_superuser
```

- With no options, in DEBUG it creates user `admin` with password `Sch00l_1234`.
- For platform super-admin (admin/admin):  
  `python manage.py ensure_superuser --username admin --password admin --no-input`
- To set a different password:  
  `python manage.py ensure_superuser --username admin --password YourSecurePassword --no-input`

Then log in at `/authentication/login/` or `/admin/login/` with that username and password. On Render, `seed_render_users` ensures admin/admin; `ADMIN_PASSWORD` is used only for tenant demo users (teacher1, Parent1, principal1), not for admin.

### 2. Users exist but no superuser / admin access

Run:

```bash
python manage.py ensure_superuser --username admin --password NewPassword
```

If a user with that username exists, they are promoted to superuser and their password is set to `NewPassword`. If not, a new superuser is created.

### 3. You know the username but forgot the password

```bash
python manage.py changepassword <username>
```

You’ll be prompted for the new password. Then use that username and new password at `/authentication/login/` or `/admin/login/`.

### 4. Create a brand‑new superuser interactively

```bash
python manage.py createsuperuser
```

Enter username, email, and password when prompted. Use the same username and password to log in at the URLs above.

---

## Quick reference

- **Portal/backend login:** `/authentication/login/` → username + password.
- **Django Admin:** `/admin/` (redirects to `/admin/login/` if not logged in) → same username + password; user must be **staff** and **superuser**.
- **Ensure at least one admin:** `python manage.py ensure_superuser`
- **Reset password:** `python manage.py changepassword <username>`
