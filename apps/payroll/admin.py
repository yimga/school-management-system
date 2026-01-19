from django.contrib import admin

from unfold.admin import ModelAdmin

from .models import (
    EmploymentContract,
    LeaveRequest,
    PayrollEmployee,
    PayrollRun,
    Payslip,
    PayslipLine,
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


@admin.register(PayrollEmployee)
class PayrollEmployeeAdmin(ModelAdmin):
    list_display = ("user", "department", "pay_type", "base_salary", "is_active")
    list_filter = ("department", "pay_type", "is_active")
    search_fields = ("user__username", "user__first_name", "user__last_name", "employee_code")
    inlines = [EmploymentContractInline, SalaryAdjustmentInline, TimeEntryInline, LeaveRequestInline]


@admin.register(EmploymentContract)
class EmploymentContractAdmin(ModelAdmin):
    list_display = ("employee", "contract_type", "start_date", "end_date", "pay_type", "is_active")
    list_filter = ("contract_type", "pay_type", "is_active")


@admin.register(SalaryAdjustment)
class SalaryAdjustmentAdmin(ModelAdmin):
    list_display = ("employee", "amount", "effective_date", "is_recurring")
    list_filter = ("effective_date", "is_recurring")


@admin.register(TimeEntry)
class TimeEntryAdmin(ModelAdmin):
    list_display = ("employee", "entry_date", "hours_worked", "is_approved")
    list_filter = ("entry_date", "is_approved")


@admin.register(LeaveRequest)
class LeaveRequestAdmin(ModelAdmin):
    list_display = ("employee", "leave_type", "start_date", "end_date", "status", "is_paid")
    list_filter = ("leave_type", "status", "is_paid")


class PayslipLineInline(admin.TabularInline):
    model = PayslipLine
    extra = 0


@admin.register(Payslip)
class PayslipAdmin(ModelAdmin):
    list_display = ("employee", "payroll_run", "gross_pay", "net_pay", "status")
    list_filter = ("status",)
    search_fields = ("employee__user__username", "employee__user__last_name", "reference")
    inlines = [PayslipLineInline]


class PayslipInline(admin.TabularInline):
    model = Payslip
    extra = 0


@admin.register(PayrollRun)
class PayrollRunAdmin(ModelAdmin):
    list_display = ("period_start", "period_end", "profile", "status", "processed_at")
    list_filter = ("status", "profile")
    inlines = [PayslipInline]
