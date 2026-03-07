# Admission Number Configuration Guide

## Overview

The school management system supports flexible admission number generation and validation, allowing schools to:
- Auto-generate admission numbers using a configurable pattern
- Allow manual entry for offline scenarios or special cases
- Validate admission numbers against custom regex patterns
- Support different formats for different regions or school types

## Configuration

### Where to Configure

Admission number settings are managed in **Site Settings** (`/admin/siteconfig/sitesettings/` or `/siteconfig/customizer/`).

### Settings

#### 1. School Code (`school_code`)
- **Purpose**: Short identifier used in admission number generation (e.g., "GIL", "ABC", "XYZ")
- **Default**: "GIL"
- **Example**: If school code is "GIL", admission numbers will include "GIL" in the pattern
- **Location**: Company Details fieldset in Site Settings

#### 2. Admission Number Mode (`admission_number_mode`)

Controls how admission numbers are handled when creating or updating student profiles.

**Options:**

- **AUTO** - Auto-generate (recommended)
  - System automatically generates admission numbers when the field is left blank
  - Manual entry is not allowed
  - Best for: Schools with consistent internet connectivity and standardized numbering

- **MANUAL** - Manual entry only
  - Staff must enter admission numbers manually
  - No auto-generation occurs
  - Best for: Schools with offline registration workflows or external numbering systems

- **AUTO_OR_MANUAL** - Allow auto or manual (default)
  - System auto-generates if field is blank
  - Staff can override with manual entry
  - Best for: Flexible workflows supporting both online and offline registration

**Default**: `AUTO_OR_MANUAL`

#### 3. Admission Number Pattern (`admission_number_pattern`)

Regex pattern used to validate admission numbers. Must be a valid Python regex string.

**Default Pattern:**
```
(\d{2}[A-Z0-9]{2,10}\d{4}[A-Z0-9]{2,6}[A-Z0-9]{1,4})|(\d{2}-[A-Z0-9]{2,10}-\d{4}-[A-Z0-9]{2,6}-[A-Z0-9]{1,4})
```

This pattern supports two formats:
1. **New format (no dashes)**: `YY + SCHOOL + #### + SPEC + CLASS`
   - Example: `26GIL1234CS001` (Year 26, School GIL, Number 1234, Specialty CS, Class 001)
2. **Legacy format (with dashes)**: `YY-SCHOOL-####-SPEC-CLASS`
   - Example: `26-GIL-1234-CS-001`

**Customizing the Pattern:**

To create a custom pattern for your school:

1. Identify your format components:
   - Year (2 digits): `\d{2}`
   - School code (2-10 alphanumeric): `[A-Z0-9]{2,10}`
   - Sequential number (4 digits): `\d{4}`
   - Specialty code (2-6 alphanumeric): `[A-Z0-9]{2,6}`
   - Class code (1-4 alphanumeric): `[A-Z0-9]{1,4}`

2. Build your regex:
   ```regex
   ^\d{2}[A-Z0-9]{2,10}\d{4}[A-Z0-9]{2,6}[A-Z0-9]{1,4}$
   ```

3. Test your pattern using online regex testers before saving

**Important Notes:**
- Patterns are case-sensitive
- Use `^` and `$` anchors if you want exact matches
- Escape special regex characters (e.g., `\.` for a literal dot)
- Leave blank to use the default pattern

## How It Works

### For Staff/Admin Users

#### Creating a New Student

1. **Navigate to**: `/admin/people/studentprofile/add/`

2. **Admission Number Field Behavior**:
   - **AUTO mode**: Field is read-only or hidden; number is generated automatically on save
   - **MANUAL mode**: Field is required; you must enter a valid admission number
   - **AUTO_OR_MANUAL mode**: 
     - Leave blank → System auto-generates
     - Enter a value → System validates against pattern

3. **Auto-Generation Requirements**:
   For auto-generation to work, the student must have:
   - `academic_year` (required)
   - `specialty` (required)
   - `classroom` (required)
   
   If any of these are missing, you'll need to enter the admission number manually.

4. **Validation**:
   - On save, the system validates the admission number against the configured pattern
   - If validation fails, you'll see an error message
   - The system also checks for uniqueness (no duplicate admission numbers)

#### Updating an Existing Student

- Admission numbers can be edited (unless in AUTO-only mode)
- Changes are validated against the pattern
- Uniqueness is enforced

### For Parent Portal Users

Parents linking their child's account use the **Link a Child** wizard (`/parent/link-child/`):

1. **Step 1**: Enter admission number (must match an existing student)
2. System validates and shows student confirmation
3. Parent completes contact and permission settings

### Offline Registration Workflow

For schools operating in areas with unreliable internet:

1. **Set Mode to**: `AUTO_OR_MANUAL` or `MANUAL`
2. **Staff Process**:
   - Register students manually with admission numbers
   - Numbers are validated against pattern (if pattern is configured)
   - When internet is restored, sync data to server
3. **Best Practice**: Use a consistent numbering scheme that matches your pattern

## Format Examples

### Standard Format (Gilead Tech High)

**Pattern**: `YY + SCHOOL + #### + SPEC + CLASS`

**Examples**:
- `26GIL1234CS001` - Year 2026, School GIL, Student 1234, Computer Science, Class 001
- `25GIL0567EL002` - Year 2025, School GIL, Student 0567, Electronics, Class 002
- `26GIL0001ME001` - Year 2026, School GIL, Student 0001, Mechanical, Class 001

### Legacy Format (with dashes)

**Pattern**: `YY-SCHOOL-####-SPEC-CLASS`

**Examples**:
- `26-GIL-1234-CS-001`
- `25-GIL-0567-EL-002`

### Custom Format Example

**School**: ABC Technical Institute  
**Format**: `SCHOOL-YY-####-SPEC`

**Pattern**: `^[A-Z]{3}-\d{2}-\d{4}-[A-Z]{2,4}$`

**Examples**:
- `ABC-26-1234-CS`
- `ABC-25-0567-EL`

## Troubleshooting

### "Admission number must match pattern" Error

**Cause**: Entered admission number doesn't match the configured regex pattern.

**Solutions**:
1. Check the pattern in Site Settings
2. Verify your admission number format matches the pattern
3. Test your number against the pattern using a regex tester
4. Contact admin to adjust the pattern if your format is valid but not matching

### Auto-Generation Not Working

**Possible Causes**:
1. Mode is set to `MANUAL` → Change to `AUTO` or `AUTO_OR_MANUAL`
2. Missing required fields → Ensure `academic_year`, `specialty`, and `classroom` are set
3. School code is blank → Set `school_code` in Site Settings

**Solution**: Check Site Settings and ensure all required student fields are populated.

### Duplicate Admission Number Error

**Cause**: Another student already has this admission number.

**Solutions**:
1. Check existing students for the number
2. Use a different number
3. If it's a data entry error, correct the existing student's record first

## Best Practices

1. **Choose the Right Mode**:
   - Use `AUTO` for fully online schools with stable internet
   - Use `AUTO_OR_MANUAL` for flexibility (recommended default)
   - Use `MANUAL` only if you have an external numbering system

2. **Document Your Pattern**:
   - Keep a record of your admission number format
   - Share the format with all staff members
   - Include examples in staff training materials

3. **Test Before Production**:
   - Test auto-generation with sample students
   - Verify pattern validation works correctly
   - Ensure uniqueness checks are working

4. **Regular Audits**:
   - Periodically check for duplicate admission numbers
   - Verify all students have valid admission numbers
   - Review and update pattern if format changes

## Technical Details

### Model Behavior

The `StudentProfile` model:
- Auto-generates admission numbers in `save()` method when:
  - Mode allows auto-generation (`AUTO` or `AUTO_OR_MANUAL`)
  - Field is blank
  - Required related objects are present
- Validates admission numbers in `clean()` method using:
  - `SiteSettings.admission_number_pattern` if configured
  - Default pattern if pattern is blank
- Enforces uniqueness at the database level

### Database Migration

After configuring admission number settings, run:
```bash
python manage.py migrate siteconfig
```

This applies the migration that adds the new fields to `SiteSettings`.

## Related Documentation

- [Customization Guide](./customization.md) - General site settings
- [Admin Guide](./PHASE_1_2_5_ADMIN_GUIDE.md) - Regional configuration
- [Student Profile Model](../apps/people/models.py) - Technical implementation

## Support

For questions or issues:
1. Check Site Settings configuration
2. Review this guide
3. Contact system administrator
4. Check Django admin error messages for specific validation issues
