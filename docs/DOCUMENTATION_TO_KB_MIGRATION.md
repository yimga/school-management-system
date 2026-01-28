# Documentation to Knowledge Base Migration

## Summary

All documentation has been organized for import into the Knowledge Base (KB) system, making it accessible to users through the portal interface.

## What Was Created

### 1. Import Command
**File**: `apps/portal/management/commands/import_docs_to_kb.py`

A Django management command that:
- Reads markdown files from `docs/` directory
- Converts them to KB articles
- Organizes them into appropriate categories
- Handles markdown-to-HTML conversion
- Sanitizes HTML for security
- Skips developer-only documentation

### 2. Import Guide
**File**: `docs/KB_IMPORT_GUIDE.md`

Complete guide explaining:
- How to run the import command
- What gets imported and what's skipped
- How to customize the import
- Troubleshooting tips

## How to Use

### Quick Import

```bash
# Import all user-facing documentation
python manage.py import_docs_to_kb

# Preview what would be imported (dry run)
python manage.py import_docs_to_kb --dry-run

# Overwrite existing articles
python manage.py import_docs_to_kb --overwrite
```

### After Import

Articles will be available at:
- `/kb/` - KB home page
- `/kb/category/student-management/` - By category
- `/kb/article/admission-number-guide/` - Individual articles

## Documentation Organization

### Categories Created

1. **Getting Started** (`getting-started`)
   - Onboarding guides
   - Testing checklists
   - Setup instructions

2. **Student Management** (`student-management`)
   - Admission number configuration
   - Student registration
   - Internationalization guides

3. **System Administration** (`system-admin`)
   - Customization guides
   - Configuration documentation
   - Security checklists
   - Accessibility guides

4. **Finance** (`finance`)
   - Payment guides
   - Payroll automation
   - Fee management

5. **Reports** (`reports`)
   - Report generation
   - Localization guides

6. **Communication** (`communication`)
   - UX guides
   - Communication features

## Files That Will Be Imported

✅ **User-Facing Documentation**:
- `ADMISSION_NUMBER_GUIDE.md` → Student Management
- `TESTING_CHECKLIST_ONBOARDING.md` → Getting Started
- `ONBOARDING_READY_FOR_TESTING.md` → Getting Started
- `customization.md` → System Administration
- `SETUP_NEW_SCHOOL_WORLDWIDE.md` → System Administration
- `finance-payments.md` → Finance
- `payroll-automation.md` → Finance
- `PHASE_1_2_7_REPORT_LOCALIZATION.md` → Reports
- `ACCESSIBILITY.md` → System Administration
- `MOBILE_API_HANDBOOK.md` → System Administration
- `security-checklist.md` → System Administration
- `PHASE_1_2_8_COMPLIANCE_LEGAL.md` → System Administration
- `PHASE_1_2_5_ADMIN_GUIDE.md` → System Administration
- `PHASE_1_2_4_INTERNATIONALIZATION.md` → Student Management
- `ux.md` → Communication

❌ **Skipped (Developer Documentation)**:
- `KB_*.md` files (already in KB format)
- `*IMPLEMENTATION_GUIDE*.md`
- `*CHECKLIST*.md` (internal)
- `*ROADMAP*.md`
- `*COMPLETION*.md`
- `*INDEX*.md`
- `*ANALYSIS*.md`
- `*TESTING*.md` (except onboarding testing)
- `*READY_FOR_TESTING*.md`

## Benefits

1. **Centralized Access**: All documentation in one place
2. **Searchable**: KB has built-in search functionality
3. **User-Friendly**: Clean, readable interface
4. **Categorized**: Easy to find relevant docs
5. **Maintainable**: Update markdown files, re-import
6. **Accessible**: Available to all portal users

## Next Steps

1. **Run the import**:
   ```bash
   python manage.py import_docs_to_kb --dry-run  # Preview first
   python manage.py import_docs_to_kb            # Then import
   ```

2. **Review imported articles**:
   - Visit `/kb/` to see all articles
   - Check categories are correct
   - Verify formatting looks good

3. **Customize if needed**:
   - Edit article metadata in admin
   - Adjust categories
   - Add related articles
   - Feature important articles

4. **Keep docs updated**:
   - Update markdown files in `docs/`
   - Re-run import with `--overwrite` to update KB

## Maintenance

### Updating Documentation

1. Edit markdown file in `docs/`
2. Run: `python manage.py import_docs_to_kb --overwrite`
3. Article is updated in KB

### Adding New Documentation

1. Create new `.md` file in `docs/`
2. Add mapping in `import_docs_to_kb.py` if needed
3. Run import command
4. Article appears in KB

### Manual Edits

For articles that need special handling:
- Edit directly in `/admin/portal/kbarticle/`
- Changes persist until next import (if using `--overwrite`)

## Technical Details

### Markdown Conversion

- Uses `markdown` library if available (recommended)
- Falls back to simple conversion if not installed
- All HTML is sanitized for security

### Article Metadata

- **Title**: From first H1 or filename
- **Summary**: First paragraph (200 chars)
- **Slug**: Auto-generated from filename
- **Status**: PUBLISHED (ready to view)
- **Author**: First superuser or staff user

### HTML Sanitization

All HTML is sanitized using `apps.portal.sanitizers.sanitize_html()`:
- Removes unsafe tags
- Prevents XSS attacks
- Allows only safe HTML elements

## Related Files

- `apps/portal/management/commands/import_docs_to_kb.py` - Import command
- `docs/KB_IMPORT_GUIDE.md` - Detailed usage guide
- `apps/portal/models_kb.py` - KB models
- `apps/portal/views_kb.py` - KB views
- `apps/portal/urls_kb.py` - KB URLs

---

**Status**: ✅ Ready to Import  
**Command**: `python manage.py import_docs_to_kb`  
**Documentation**: See `KB_IMPORT_GUIDE.md` for details
