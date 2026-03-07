# Commit & main alignment checklist

## Done in this pass

1. **`.gitignore`**
   - Added `nul` (Windows null device – avoid accidental commits).
   - Added `.cursor/` (Cursor worktrees/IDE – keep out of repo).

2. **New files staged**
   - `static/css/admin-dark-readability.css`
   - `static/css/portal-theme-modes.css`

3. **All modified files staged**
   - `git add -u` was run so every already-tracked file with local changes is staged (apps, config, templates, static CSS/JS, etc.).

4. **Template fix**
   - `templates/portal_base.html`: duplicate `{% block extrastyle %}` removed so dashboards no longer hit the “block appears more than once” error.

## Verify locally (run in repo root)

```bash
# See what is staged
git status
git diff --cached --name-only

# Optional: commit
git commit -m "Portal dashboards fix, .gitignore, new CSS, RBAC/UI/backend theme and workflow fixes"
```

## Files on `main` that are not on `improvements`

These were in main’s “Commit all: untracked and modified files” but are **missing** on `improvements`:

| File | Note |
|------|------|
| `templates/people/backend_teacher_create.html` | Exists on main only; add from main if you need it. |
| `apps/siteconfig/templatetags/report_style_tags.py` | Exists on main only; add from main if reports use it. |
| `push-all.sh` | Exists on main only; add from main if you use it. |

To bring them in without losing your work:

```bash
git fetch origin main
git checkout origin/main -- templates/people/backend_teacher_create.html
git checkout origin/main -- apps/siteconfig/templatetags/report_style_tags.py
git checkout origin/main -- push-all.sh
# Then stage and commit if desired.
```

## Summary

- All current changes on `improvements` are staged (modified + new CSS).
- `nul` and `.cursor/` are ignored.
- Duplicate `extrastyle` block is fixed in `portal_base.html`.
- Optional: pull the three main-only files above if you want full parity with main.
