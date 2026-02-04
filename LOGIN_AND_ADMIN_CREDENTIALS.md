# User Accounts and Admin Credentials Not Working

If you cannot log in at **Portal/Backend** (`/authentication/login/`) or **Django Admin** (`/admin/`), use the steps below.

---

## Same credentials for both

One user account is used for:

- **Portal & Backend:** http://127.0.0.1:8000/authentication/login/
- **Django Admin:** http://127.0.0.1:8000/admin/

Use the **same username and password** in both places.

---

## Fix 1: No users in the database (after migrate)

If the database was just created or reset, there may be no users. Create a superuser:

### Option A – Quick (creates `admin` with password `admin123` when DB is empty)

```bash
python manage.py ensure_superuser
```

- Only runs if **no users exist**.
- In DEBUG mode it creates username `admin`, password `admin123`.
- **Change the password:** `python manage.py changepassword admin`

### Option B – Interactive (choose username and password)

```bash
python manage.py createsuperuser
```

Enter username, email, and password when prompted.

---

## Fix 2: Forgot password

Reset the password for an existing user:

```bash
python manage.py changepassword <username>
```

Example:

```bash
python manage.py changepassword admin
```

Enter the new password twice.

---

## Fix 3: “Invalid username or password” but user exists

1. **Confirm the user is active:** In Django Admin (if you can log in as another admin), open the user and ensure “Active” is checked. Or in shell:
   ```bash
   python manage.py shell
   ```
   ```python
   from django.contrib.auth import get_user_model
   User = get_user_model()
   u = User.objects.get(username='admin')  # use your username
   u.is_active = True
   u.save()
   ```
2. **Reset password:** `python manage.py changepassword <username>`

---

## Summary

| Situation                         | Command / action                          |
|----------------------------------|-------------------------------------------|
| No users (fresh DB)              | `python manage.py ensure_superuser` or `createsuperuser` |
| Forgot password                  | `python manage.py changepassword <username>` |
| User exists but can’t log in     | Ensure `is_active=True`, then reset password |

After creating or resetting a user, log in at:

- **Portal/Backend:** http://127.0.0.1:8000/authentication/login/
- **Django Admin:** http://127.0.0.1:8000/admin/
