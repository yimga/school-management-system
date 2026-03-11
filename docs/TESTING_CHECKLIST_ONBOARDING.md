# Pre-Testing Checklist: Onboarding Improvements

**Doc status: Closed.** Checklist is reference for onboarding testing; remaining verification is **Closed (Phase 10)**. See **`docs/PHASE_10_BACKLOG.md`** and **`docs/WHATS_LEFT_COMPLETE_BACKLOG_DEFERRED.md`**.

## Before Testing

### 1. Run Database Migration
```bash
python manage.py migrate siteconfig
```
This applies the new `admission_number_mode` and `admission_number_pattern` fields to `SiteSettings`.

**Expected**: Migration `0043_sitesettings_admission_number_config` runs successfully.

### 2. Verify Site Settings Configuration
- Navigate to `/admin/siteconfig/sitesettings/` or `/siteconfig/customizer/`
- Check that new fields are visible:
  - `school_code` (should be set, e.g., "GIL")
  - `admission_number_mode` (default: "AUTO_OR_MANUAL")
  - `admission_number_pattern` (default: regex pattern)

### 3. Verify Sessions Are Working
The wizard uses Django sessions to persist data between steps. Sessions should already be configured, but verify:
- `SESSION_COOKIE_AGE` is set (default: 14400 seconds = 4 hours)
- `SESSION_SAVE_EVERY_REQUEST` is enabled (default: True)

## Testing the Wizard

### Test 1: Basic Wizard Flow (Happy Path)

1. **As a Parent User**:
   - Log in as a parent user (or create one if needed)
   - Navigate to `/parent/link-child/`
   - You should see the 3-step wizard

2. **Step 1 - Identify Child**:
   - Enter a valid admission number (must exist in database)
   - Select a relationship (e.g., "Guardian")
   - Click "Continue"
   - **Expected**: Student confirmation box appears, then redirects to Step 2

3. **Step 2 - Contact & Permissions**:
   - Enter phone number (optional)
   - Select preferred contact method
   - Check/uncheck permission boxes
   - Click "Continue"
   - **Expected**: Redirects to Step 3

4. **Step 3 - Optional Details**:
   - Fill in some optional fields (or skip all)
   - Optionally enter referral code
   - Click "Complete Setup"
   - **Expected**: 
     - Success message appears
     - Redirects to parent dashboard
     - Student is linked to parent account

### Test 2: Error Handling

1. **Invalid Admission Number**:
   - Enter a non-existent admission number
   - Click "Continue"
   - **Expected**: Error message "No student found with that admission number."

2. **Already Linked Student**:
   - Try to link a student that's already linked to your account
   - **Expected**: Error message "You are already linked to this student."

3. **Missing Required Fields (Step 1)**:
   - Leave admission number blank
   - Click "Continue"
   - **Expected**: Error message "Admission number is required."

4. **Back Navigation**:
   - Complete Step 1, go to Step 2
   - Click "Back"
   - **Expected**: Returns to Step 1 with data preserved

### Test 3: Session Persistence

1. **Data Persistence**:
   - Fill Step 1, go to Step 2
   - Refresh the page
   - **Expected**: Data is still there (from session)

2. **Session Cleanup**:
   - Complete the wizard successfully
   - **Expected**: Session data is cleared (no leftover data)

### Test 4: Mobile Responsiveness

1. **Mobile View**:
   - Open wizard on mobile device or resize browser to mobile width
   - **Expected**: 
     - Steps are clearly visible
     - Form fields are properly sized
     - Buttons stack vertically on small screens
     - Progress bar is visible

### Test 5: Admission Number Configuration

1. **Auto-Generation Mode**:
   - In Site Settings, set `admission_number_mode` to "AUTO"
   - Create a new student in admin (leave admission number blank)
   - **Expected**: Admission number is auto-generated

2. **Manual Mode**:
   - Set `admission_number_mode` to "MANUAL"
   - Create a new student
   - **Expected**: Admission number field is required, no auto-generation

3. **Auto or Manual Mode** (Default):
   - Set `admission_number_mode` to "AUTO_OR_MANUAL"
   - Create a student with blank admission number → auto-generates
   - Create a student with manual entry → uses manual entry
   - **Expected**: Both scenarios work

### Test 6: Parent Dashboard Integration

1. **Onboarding Progress Indicator**:
   - As a parent with no linked children, view dashboard
   - **Expected**: "Get Started" card appears with two options

2. **Onboarding Score**:
   - As a parent with linked children, view dashboard
   - **Expected**: "Setup" tile shows completion percentage

3. **Unified Entry Point**:
   - Click "I have an admission number" from dashboard
   - **Expected**: Opens wizard at Step 1

### Test 7: Legacy Compatibility

1. **Legacy URL**:
   - Navigate to `/parent/link-child/legacy/`
   - **Expected**: Old single-page form still works

## Common Issues & Solutions

### Issue: "No student found with that admission number"
**Solution**: Ensure you have test students in the database with valid admission numbers.

### Issue: Wizard data not persisting
**Solution**: Check Django session configuration in `settings.py`. Ensure `SESSION_SAVE_EVERY_REQUEST = True`.

### Issue: Migration fails
**Solution**: 
- Check that migration `0042` exists and was applied
- Run `python manage.py showmigrations siteconfig` to see migration status
- If needed, manually fix migration dependencies

### Issue: Form fields not styled
**Solution**: Check that Bootstrap CSS is loaded. Verify `STATICFILES_DIRS` includes Bootstrap files.

### Issue: JavaScript not working (auto-focus, etc.)
**Solution**: 
- Check browser console for errors
- Verify `extrajs` block is properly closed in template
- Ensure jQuery/Bootstrap JS is loaded if required

## Post-Testing

After successful testing:

1. ✅ Document any issues found
2. ✅ Update documentation if workflows changed
3. ✅ Consider adding automated tests for critical paths
4. ✅ Update user training materials if needed

## Next Steps After Testing

If all tests pass:
- Deploy to staging environment
- Train staff on new admission number configuration
- Update parent-facing documentation
- Monitor for any production issues
