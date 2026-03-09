from django.contrib import admin
from config.admin import register_tenant_admin

from unfold.admin import ModelAdmin

from .models import (
    EmploymentContract,
    LeaveRequest,
    PayrollEmployee,
    PayrollRun,
    Payslip,
    PayslipLine,
    PayScale,
    SalaryAdjustment,
    TimeEntry,
)


class EmploymentContractInline(admin.TabularInline):
    model = EmploymentContract
    extra = 0


class SalaryAdjustmentInline(admin.TabularInline):
    model = SalaryAdjustment
    extra = 0


class TimeEntryInline(admin.TabularInline):
    model = TimeEntry
    extra = 0


class LeaveRequestInline(admin.TabularInline):
    model = LeaveRequest
    extra = 0


class PayScaleAdmin(ModelAdmin):
    list_display = ("name", "code", "min_salary", "max_salary", "default_salary", "department", "is_active")
    list_filter = ("is_active", "department")
    search_fields = ("name", "code", "description")
    fieldsets = (
        ("Basic Information", {
            "fields": ("name", "code", "description", "is_active")
        }),
        ("Salary Range", {
            "fields": ("min_salary", "max_salary", "default_salary"),
            "description": "Define the salary range for this pay scale. Default salary is optional and will be applied when assigning this scale to employees."
        }),
        ("Department (Optional)", {
            "fields": ("department",),
            "description": "If specified, this scale will be restricted to the selected department. Leave blank for general use.",
            "classes": ("collapse",)
        }),
        ("Metadata", {
            "fields": ("created_by", "created_at", "updated_at"),
            "classes": ("collapse",)
        }),
    )
    readonly_fields = ("created_at", "updated_at")
    
    def save_model(self, request, obj, form, change):
        if not change:  # Only set on creation
            obj.created_by = request.user
        super().save_model(request, obj, form, change)


class PayrollEmployeeAdmin(ModelAdmin):
    list_display = ("user", "department", "pay_scale", "pay_type", "base_salary", "is_active")
    list_filter = ("department", "pay_type", "pay_scale", "is_active")
    search_fields = ("user__username", "user__first_name", "user__last_name", "employee_code")
    inlines = [EmploymentContractInline, SalaryAdjustmentInline, TimeEntryInline, LeaveRequestInline]
    fieldsets = (
        ("Employee Information", {
            "fields": ("user", "employee_code", "department", "hire_date", "is_active")
        }),
        ("Pay Scale & Compensation", {
            "fields": ("pay_scale", "pay_type", "base_salary", "hourly_rate", "salary_cap"),
            "description": "Assign a pay scale or set salary directly. Pay scale will suggest salary ranges."
        }),
        ("Payment Details", {
            "fields": ("payment_method", "bank_account", "mobile_money_number", "tax_id", "cnps_number")
        }),
    )
    
    actions = ["apply_pay_scale_defaults"]
    
    def apply_pay_scale_defaults(self, request, queryset):
        """Apply default salary from pay scale to selected employees"""
        updated = 0
        for employee in queryset:
            if employee.pay_scale and employee.pay_scale.default_salary:
                if not employee.base_salary or request.POST.get('force_update') == 'yes':
                    employee.base_salary = employee.pay_scale.default_salary
                    employee.save(update_fields=['base_salary'])
                    updated += 1
        self.message_user(request, f"Updated {updated} employee(s) with pay scale default salaries.")
    apply_pay_scale_defaults.short_description = "Apply default salary from pay scale"


class EmploymentContractAdmin(ModelAdmin):
    list_display = ("employee", "contract_type", "start_date", "end_date", "pay_type", "is_active")
    list_filter = ("contract_type", "pay_type", "is_active")


class SalaryAdjustmentAdmin(ModelAdmin):
    list_display = ("employee", "amount", "effective_date", "is_recurring")
    list_filter = ("effective_date", "is_recurring")


class TimeEntryAdmin(ModelAdmin):
    list_display = ("employee", "entry_date", "hours_worked", "is_approved")
    list_filter = ("entry_date", "is_approved")


class LeaveRequestAdmin(ModelAdmin):
    list_display = ("employee", "leave_type", "start_date", "end_date", "status", "is_paid")
    list_filter = ("leave_type", "status", "is_paid")


class PayslipLineInline(admin.TabularInline):
    model = PayslipLine
    extra = 0


class PayslipAdmin(ModelAdmin):
    list_display = ("employee", "payroll_run", "gross_pay", "net_pay", "status")
    list_filter = ("status",)
    search_fields = ("employee__user__username", "employee__user__last_name", "reference")
    inlines = [PayslipLineInline]


class PayslipInline(admin.TabularInline):
    model = Payslip
    extra = 0


class PayrollRunAdmin(ModelAdmin):
    list_display = ("period_start", "period_end", "profile", "status", "processed_at")
    list_filter = ("status", "profile")
    inlines = [PayslipInline]


# Register all models with tenant admin only
register_tenant_admin(PayScale, PayScaleAdmin)
register_tenant_admin(PayrollEmployee, PayrollEmployeeAdmin)
register_tenant_admin(EmploymentContract, EmploymentContractAdmin)
register_tenant_admin(SalaryAdjustment, SalaryAdjustmentAdmin)
register_tenant_admin(TimeEntry, TimeEntryAdmin)
register_tenant_admin(LeaveRequest, LeaveRequestAdmin)
register_tenant_admin(Payslip, PayslipAdmin)
register_tenant_admin(PayrollRun, PayrollRunAdmin)
