# Pay Scale & Salary Management Guide

## Overview

The pay scale system allows administrators to define standardized salary structures (pay scales/grades) and apply them to staff members. This ensures consistency, simplifies salary management, and makes it easy to apply salary changes across multiple employees.

## Current System

### What Exists Now

**Before Pay Scale System:**
- `TeacherProfile.pay_grade` - Free text field (e.g., "Grade 1", "Senior Teacher")
- `TeacherProfile.salary_amount` - Direct salary value
- `PayrollEmployee.base_salary` - Direct salary value
- No structured pay scale system

**With Pay Scale System (New):**
- `PayScale` model - Structured pay scales with min/max/default salaries
- `PayrollEmployee.pay_scale` - Link to PayScale
- `TeacherProfile.pay_scale` - Link to PayScale (for convenience)
- `EmploymentContract.pay_scale` - Pay scale for contract period

## How It Works

### 1. Creating Pay Scales

**Location**: `/admin/payroll/payscale/`

**Steps**:
1. Click "Add Pay Scale"
2. Fill in:
   - **Name**: Display name (e.g., "Grade 1 - Entry Level")
   - **Code**: Short code (e.g., "GR1", "SEN", "ADM")
   - **Description**: Who this scale applies to
   - **Min Salary**: Minimum salary for this grade
   - **Max Salary**: Maximum salary for this grade
   - **Default Salary**: Starting salary when applying this scale (optional)
   - **Department**: Optional - restrict to specific department
   - **Is Active**: Only active scales can be applied
3. Save

**Example Pay Scales**:
```
Grade 1 (GR1)
- Min: 100,000 XAF
- Max: 150,000 XAF
- Default: 120,000 XAF
- Department: General

Grade 2 (GR2)
- Min: 150,000 XAF
- Max: 200,000 XAF
- Default: 175,000 XAF
- Department: General

Senior Teacher (SEN)
- Min: 200,000 XAF
- Max: 300,000 XAF
- Default: 250,000 XAF
- Department: Teaching

Administrative Staff (ADM)
- Min: 150,000 XAF
- Max: 250,000 XAF
- Default: 200,000 XAF
- Department: Administration
```

### 2. Applying Pay Scales to Staff

#### Method A: Via PayrollEmployee Admin

1. Navigate to `/admin/payroll/payrollemployee/`
2. Select employee(s) or edit individual employee
3. In the "Pay Scale & Compensation" section:
   - Select a **Pay Scale** from dropdown
   - Optionally set **Base Salary** (can override default)
4. Save

**Bulk Action**: "Apply default salary from pay scale"
- Select multiple employees
- Choose action from dropdown
- System applies default salary from their assigned pay scale

#### Method B: Via TeacherProfile Admin

1. Navigate to `/admin/people/teacherprofile/`
2. Edit teacher profile
3. In "Compensation" section:
   - Select **Pay Scale**
   - System can auto-sync `pay_grade` field with scale code
   - `salary_amount` can be set from scale default
4. Save

**Bulk Action**: "Apply pay scale default salary"
- Select multiple teachers
- Choose action
- System applies default salary from their pay scale

### 3. Pay Scale Validation

The system validates:
- **Min ≤ Max**: Minimum salary cannot exceed maximum
- **Default in Range**: Default salary must be within min/max range
- **Active Status**: Only active scales appear in dropdowns for new assignments

## Benefits

### 1. Consistency
- Standardized salary structures across the organization
- Easy to see who is on which pay scale
- Prevents salary inconsistencies

### 2. Efficiency
- Apply scales to multiple employees at once
- Bulk actions for salary updates
- Department-specific scales for different roles

### 3. Flexibility
- Can still set individual salaries (override scale default)
- Scales can be department-specific or general
- Support for both monthly and hourly pay types

### 4. Audit Trail
- Track which employees are on which scales
- See salary ranges for each scale
- Historical tracking via EmploymentContract

## Use Cases

### Use Case 1: New Teacher Onboarding

1. Admin creates teacher account and profile
2. Admin assigns appropriate pay scale (e.g., "Grade 1")
3. System suggests default salary from scale
4. Admin confirms or adjusts salary
5. Teacher is assigned to pay scale

### Use Case 2: Salary Review & Promotion

1. Admin reviews employees on "Grade 1" scale
2. Admin promotes employee to "Grade 2" scale
3. Admin uses bulk action to apply new default salary
4. All employees on Grade 2 get updated

### Use Case 3: Department-Specific Scales

1. Admin creates "Teaching Staff" scale for Education department
2. Admin creates "Administrative Staff" scale for Admin department
3. Each department has appropriate salary ranges
4. Scales automatically filter by department in admin

### Use Case 4: Contract-Based Pay Scales

1. Admin creates EmploymentContract for employee
2. Admin assigns pay scale to contract
3. Contract can override employee's default scale
4. Payroll calculation uses contract scale if active

## Admin Interface

### PayScale Admin (`/admin/payroll/payscale/`)

**List View**:
- Shows: Name, Code, Min/Max/Default Salary, Department, Active Status
- Filter by: Active status, Department
- Search by: Name, Code, Description

**Detail View**:
- Basic Information section
- Salary Range section (with validation)
- Department section (optional)
- Metadata section (created by, timestamps)

### PayrollEmployee Admin (`/admin/payroll/payrollemployee/`)

**List View**:
- Shows: User, Department, **Pay Scale**, Pay Type, Base Salary, Active
- Filter by: Department, Pay Type, **Pay Scale**, Active
- **New**: Pay Scale column visible

**Detail View**:
- "Pay Scale & Compensation" section
- Pay Scale dropdown (shows active scales)
- Base Salary field (can override scale default)

**Bulk Actions**:
- "Apply default salary from pay scale"

### TeacherProfile Admin (`/admin/people/teacherprofile/`)

**List View**:
- Shows: Teacher, Staff ID, Department, Position, **Pay Scale**, Pay Grade, Salary, Next Pay Date
- Filter by: Department, **Pay Scale**, Dashboard View, Permissions

**Detail View**:
- "Compensation" section
- Pay Scale dropdown
- Pay Grade field (legacy, can sync with scale code)
- Salary Amount field

**Bulk Actions**:
- "Apply pay scale default salary"

## Integration with Payroll System

### Payroll Calculation

The payroll system (`apps/payroll/services.py`) resolves salary in this order:

1. **EmploymentContract** (if active and has base_salary)
2. **PayrollEmployee.base_salary**
3. **TeacherProfile.salary_amount** (fallback)
4. **PayScale.default_salary** (if scale assigned but no salary set)

This means:
- Contract salaries take precedence
- Individual salaries override scale defaults
- Scale defaults are used when no salary is set

### Salary Validation

When a pay scale is assigned:
- System can validate that `base_salary` is within scale's min/max range
- Warnings can be shown if salary is outside range
- Default salary is suggested from scale

## Migration from Legacy System

### Current State
- Many teachers have `pay_grade` as free text (e.g., "Grade 1")
- Salaries set directly on `salary_amount`

### Migration Steps

1. **Create Pay Scales**:
   - Review existing `pay_grade` values
   - Create corresponding PayScale entries
   - Set appropriate min/max/default salaries

2. **Assign Scales**:
   - Option 1: Manual assignment in admin
   - Option 2: Use management command to bulk assign (see below)

3. **Sync Data**:
   - Update `pay_grade` text field to match scale code (optional)
   - Apply default salaries where missing

### Management Command (Future)

A command could be created to:
```bash
python manage.py migrate_pay_grades_to_scales
```

This would:
- Analyze existing `pay_grade` values
- Create PayScale entries
- Assign scales to employees
- Sync salary amounts

## Best Practices

### 1. Naming Conventions
- Use clear, consistent codes (GR1, GR2, SEN, ADM)
- Use descriptive names ("Grade 1 - Entry Level")
- Document who each scale applies to

### 2. Salary Ranges
- Set realistic min/max ranges
- Leave room for growth within scale
- Consider overlap between scales for promotions

### 3. Default Salaries
- Set default to mid-range or entry point
- Allows for individual adjustments
- Makes bulk assignment easier

### 4. Department-Specific Scales
- Use when departments have different salary structures
- Leave department blank for general scales
- Makes filtering easier in admin

### 5. Active/Inactive Management
- Mark old scales as inactive (don't delete)
- Prevents accidental assignment
- Maintains historical data

## Troubleshooting

### "Pay scale not showing in dropdown"
- Check scale is marked as `is_active=True`
- Verify department matches (if scale is department-specific)
- Check user has permission to view payroll models

### "Default salary not applying"
- Verify scale has `default_salary` set
- Check if employee already has `base_salary` set (won't override)
- Use bulk action to force update

### "Salary outside scale range"
- System validates min/max on scale creation
- Individual salaries can be outside range (flexibility)
- Consider updating scale range or employee salary

### "Can't assign scale to employee"
- Verify employee has `PayrollEmployee` record
- Check scale is active
- Verify department matches (if applicable)

## Related Models

- **PayScale**: Defines the pay scale structure
- **PayrollEmployee**: Links to PayScale, has base_salary
- **TeacherProfile**: Also links to PayScale for convenience
- **EmploymentContract**: Can have its own PayScale for contract period
- **PayrollRun**: Uses employee/contract salaries for calculations

## Future Enhancements

Potential improvements:
1. **Pay Scale Steps**: Define steps within a scale (e.g., Step 1-5 within Grade 1)
2. **Automatic Promotions**: Rules for moving between scales
3. **Salary History**: Track salary changes when scales change
4. **Reporting**: Reports by pay scale, salary distribution
5. **Import/Export**: Bulk import pay scales from CSV

---

**Status**: ✅ Implemented  
**Location**: `/admin/payroll/payscale/`  
**Migration Required**: Yes (`0002_payscale_and_links`, `0004_teacherprofile_pay_scale`)
