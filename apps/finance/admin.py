from datetime import timedelta
from decimal import Decimal
from django.contrib import admin
from django.contrib.admin.sites import AlreadyRegistered
from django.core.exceptions import ValidationError
from django.db import DatabaseError, IntegrityError
from config.admin import register_tenant_admin
from apps.platform_runtime.helpers import get_effective_site_settings

from unfold.admin import ModelAdmin

from .models import (
    AidAuditLog,
    Asset,
    AssetCategory,
    AwardSource,
    BankAccount,
    BankStatementEntry,
    BankStatementUpload,
    Budget,
    BudgetLine,
    CashOfficeClosure,
    ComplianceProfile,
    ContributionRule,
    Counterparty,
    FeeInstallment,
    FeeItem,
    FeePlan,
    FinancialAidApplication,
    FinanceRequestAudit,
    Grant,
    GrantAllocation,
    Invoice,
    InvoiceLine,
    JournalEntry,
    JournalLine,
    LedgerAccount,
    Payment,
    PaymentDispute,
    PaymentProofUpload,
    ReferralReward,
    Scholarship,
    SuspensePayment,
    SuspensePaymentAllocation,
    TaxBracket,
    PaymentReminder,
    PaymentReminderLog,
    Notification,
    ReportRequest,
)


class ComplianceProfileAdmin(ModelAdmin):
    list_display = (
        "name",
        "country_code",
        "currency_code",
        "chart_template",
        "timezone",
        "is_active",
    )
    list_filter = ("country_code", "chart_template", "is_active")
    list_per_page = 50  # PERFORMANCE: Add pagination
    show_full_result_count = False
    search_fields = ("name", "country_code")
    fieldsets = (
        ("Identity", {"fields": ("name", "country_code", "currency_code")}),
        (
            "Localization",
            {
                "fields": ("timezone",),
                "description": "Default timezone for date/time operations; overrides settings.TIME_ZONE.",
            },
        ),
        ("Configuration", {"fields": ("chart_template", "available_payment_methods")}),
        ("Status", {"fields": ("is_active",)}),
    )


class TaxBracketAdmin(ModelAdmin):
    list_display = ("profile", "lower_bound", "upper_bound", "rate")
    list_filter = ("profile",)
    list_per_page = 50  # PERFORMANCE: Add pagination
    show_full_result_count = False


class ContributionRuleAdmin(ModelAdmin):
    list_display = (
        "profile",
        "code",
        "name",
        "employee_rate",
        "employer_rate",
        "cap_amount",
    )
    list_filter = ("profile",)
    list_per_page = 50  # PERFORMANCE: Add pagination
    show_full_result_count = False
    search_fields = ("code", "name")


class LedgerAccountAdmin(ModelAdmin):
    list_display = ("profile", "code", "name", "account_type", "is_active")
    list_filter = ("profile", "account_type", "is_active")
    list_per_page = 50  # PERFORMANCE: Add pagination
    show_full_result_count = False
    search_fields = ("code", "name")


class JournalLineInline(admin.TabularInline):
    model = JournalLine
    extra = 0


class JournalEntryAdmin(ModelAdmin):
    list_display = ("entry_date", "reference", "profile", "posted_at")
    list_filter = ("profile",)
    list_per_page = 50  # PERFORMANCE: Add pagination
    show_full_result_count = False
    search_fields = ("reference", "memo")
    inlines = [JournalLineInline]


class CounterpartyAdmin(ModelAdmin):
    list_display = ("name", "counterparty_type", "student", "user")
    list_filter = ("counterparty_type",)
    list_per_page = 50  # PERFORMANCE: Add pagination
    show_full_result_count = False
    search_fields = ("name", "email", "phone")


class FeeItemInline(admin.TabularInline):
    model = FeeItem
    extra = 0


class FeePlanAdmin(ModelAdmin):
    list_display = ("name", "academic_year", "classroom", "specialty", "is_active")
    list_filter = ("academic_year", "classroom", "specialty", "is_active")
    list_per_page = 50  # PERFORMANCE: Add pagination
    show_full_result_count = False
    search_fields = ("name",)
    inlines = [FeeItemInline]
    actions = ["copy_to_next_year"]

    def copy_to_next_year(self, request, queryset):
        """Copy selected fee plans to the next academic year."""
        from apps.academics.models import AcademicYear
        from apps.finance.services import copy_fee_plan_to_year
        from django.contrib import messages

        school = getattr(queryset.select_related("school").first(), "school", None)
        site = get_effective_site_settings(school=school)
        increase_pct = getattr(
            site, "finance_fee_plan_copy_increase_percentage", Decimal("0.00")
        )

        # Find next academic year
        current_year = None
        for plan in queryset:
            if not current_year:
                current_year = plan.academic_year
            elif plan.academic_year.start_date > current_year.start_date:
                current_year = plan.academic_year

        if not current_year:
            self.message_user(
                request,
                "Could not determine current academic year.",
                level=messages.ERROR,
            )
            return

        # Find next year (year with start_date after current)
        next_year = (
            AcademicYear.objects.filter(start_date__gt=current_year.end_date)
            .order_by("start_date")
            .first()
        )

        if not next_year:
            self.message_user(
                request,
                f"No academic year found after {current_year.name}. Please create one first.",
                level=messages.ERROR,
            )
            return

        copied_count = 0
        for plan in queryset:
            try:
                copy_fee_plan_to_year(plan, next_year, increase_pct)
                copied_count += 1
            except (
                ValueError,
                TypeError,
                ValidationError,
                DatabaseError,
                IntegrityError,
            ) as e:
                self.message_user(
                    request,
                    f"Error copying {plan.name}: {str(e)}",
                    level=messages.ERROR,
                )

        if copied_count > 0:
            increase_text = (
                f" with {increase_pct}% increase" if increase_pct > 0 else ""
            )
            self.message_user(
                request,
                f"Successfully copied {copied_count} fee plan(s) to {next_year.name}{increase_text}.",
                level=messages.SUCCESS,
            )

    copy_to_next_year.short_description = (
        "Copy selected fee plans to next academic year"
    )


class FeeInstallmentAdmin(ModelAdmin):
    list_display = ("fee_item", "installment_number", "amount", "due_date")
    list_filter = ("fee_item",)
    list_per_page = 50  # PERFORMANCE: Add pagination
    show_full_result_count = False


class InvoiceLineInline(admin.TabularInline):
    model = InvoiceLine
    extra = 0


class InvoiceAdmin(ModelAdmin):
    list_display = (
        "invoice_type",
        "reference",
        "status",
        "student",
        "total_amount",
        "balance_amount",
        "issued_date",
        "attachment",
    )
    list_filter = ("invoice_type", "status", "issued_date")
    list_per_page = 50  # PERFORMANCE: Add pagination
    show_full_result_count = False
    search_fields = ("reference", "student__student_code", "counterparty__name")
    inlines = [InvoiceLineInline]

    def save_model(self, request, obj, form, change):
        if change and obj.status == Invoice.Status.VOID:
            try:
                old = (
                    Invoice.objects.filter(pk=obj.pk)
                    .values_list("status", flat=True)
                    .first()
                )
                if old != Invoice.Status.VOID:
                    from apps.compliance.models_audit import AuditLog

                    AuditLog.objects.create(
                        action=AuditLog.Action.REJECT,
                        user=request.user,
                        model_name="Invoice",
                        object_id=str(obj.pk),
                        object_repr=str(obj),
                        app_label="finance",
                        new_values={
                            "status": "VOID",
                            "void_reason": (
                                obj.void_reason or "Voided by admin"
                            ).strip(),
                        },
                        reason=(obj.void_reason or "Voided by admin")[:255],
                        sensitivity=AuditLog.Sensitivity.HIGH,
                    )
            except (
                DatabaseError,
                IntegrityError,
                ValidationError,
                AttributeError,
            ) as e:
                import logging

                logging.getLogger(__name__).debug("AuditLog create on void: %s", e)
        super().save_model(request, obj, form, change)


class PaymentAdmin(ModelAdmin):
    list_display = (
        "invoice",
        "amount",
        "method",
        "paid_at",
        "receipt_number",
        "physical_receipt_book_serial",
        "physical_receipt_number",
        "receipt_file",
    )
    list_filter = ("method", "paid_at")
    list_per_page = 50  # PERFORMANCE: Add pagination
    show_full_result_count = False
    search_fields = ("reference", "receipt_number")


class PaymentReminderAdmin(ModelAdmin):
    list_display = (
        "invoice",
        "is_active",
        "next_send_at",
        "last_sent_at",
        "reminder_days_before",
        "reminder_history_link",
    )
    list_filter = ("is_active",)
    list_per_page = 50  # PERFORMANCE: Add pagination
    show_full_result_count = False
    search_fields = ("invoice__reference", "invoice__student__student_code")
    readonly_fields = ("reminder_history", "last_sent_at", "next_send_at")
    actions = ["resend_selected_reminders"]
    fieldsets = (
        (
            "Reminder Configuration",
            {
                "fields": (
                    "invoice",
                    "is_active",
                    "reminder_days_before",
                    "reminder_channels",
                )
            },
        ),
        ("Schedule", {"fields": ("next_send_at", "last_sent_at")}),
        (
            "Templates",
            {
                "fields": (
                    "message_template_email",
                    "message_template_sms",
                    "message_template_whatsapp",
                ),
                "classes": ("collapse",),
            },
        ),
        (
            "History",
            {
                "fields": ("reminder_history",),
                "description": "Recent reminder send history (last 10 sends).",
            },
        ),
    )

    def reminder_history_link(self, obj):
        """Link to reminder logs."""
        if not obj:
            return "-"
        log_count = obj.logs.count()
        if log_count == 0:
            return "No history"
        from django.utils.html import format_html
        from django.urls import reverse

        url = (
            reverse("admin:finance_paymentreminderlog_changelist")
            + f"?reminder__id__exact={obj.id}"
        )
        return format_html('<a href="{}">{} log(s)</a>', url, log_count)

    reminder_history_link.short_description = "History"

    def reminder_history(self, obj):
        """Show recent reminder logs inline."""
        if not obj:
            return "-"
        logs = obj.logs.order_by("-sent_at")[:10]
        if not logs:
            return "No reminder history yet."
        from django.utils.html import format_html

        lines = []
        for log in logs:
            status_color = (
                "success"
                if log.status == "SENT"
                else "danger"
                if log.status == "FAILED"
                else "warning"
            )
            lines.append(
                f'<div class="small mb-1">'
                f'<span class="badge bg-{status_color}">{log.status}</span> '
                f"{log.sent_at.strftime('%Y-%m-%d %H:%M')} - {log.note[:100] if log.note else 'No note'}"
                f"</div>"
            )
        return format_html("".join(lines))

    reminder_history.short_description = "Recent reminder history"

    def resend_selected_reminders(self, request, queryset):
        """Resend reminders immediately for selected reminders."""
        from apps.finance.tasks import run_payment_reminders
        from django.utils import timezone

        resend_count = 0
        for reminder in queryset.filter(is_active=True):
            # Force send now by setting next_send_at to past
            reminder.next_send_at = timezone.now() - timedelta(minutes=1)
            reminder.save(update_fields=["next_send_at"])
            resend_count += 1

        if resend_count > 0:
            # Run reminder task synchronously (or queue it)
            try:
                result = run_payment_reminders()
                self.message_user(
                    request,
                    f"Resent {resend_count} reminder(s). Sent: {result.get('sent', 0)} via {result.get('channels', {})}",
                    level="success",
                )
            except (
                ValueError,
                TypeError,
                ValidationError,
                DatabaseError,
                IntegrityError,
            ) as e:
                self.message_user(
                    request,
                    f"Error resending reminders: {str(e)}",
                    level="error",
                )
        else:
            self.message_user(request, "No active reminders selected.", level="warning")

    resend_selected_reminders.short_description = "Resend selected reminders now"


class PaymentReminderLogAdmin(ModelAdmin):
    list_display = ("reminder", "sent_at", "status")
    list_filter = ("status",)
    list_per_page = 50  # PERFORMANCE: Add pagination
    show_full_result_count = False


class BudgetAdmin(ModelAdmin):
    list_display = ("name", "academic_year", "department", "total_amount")
    list_filter = ("academic_year", "department")
    list_per_page = 50  # PERFORMANCE: Add pagination
    show_full_result_count = False


class BudgetLineAdmin(ModelAdmin):
    list_display = ("budget", "account", "amount")
    list_filter = ("budget",)
    list_per_page = 50  # PERFORMANCE: Add pagination
    show_full_result_count = False


class AssetCategoryAdmin(ModelAdmin):
    list_display = ("name",)
    list_per_page = 50  # PERFORMANCE: Add pagination
    show_full_result_count = False


class AssetAdmin(ModelAdmin):
    list_display = ("name", "category", "status", "purchase_cost")
    list_filter = ("status", "category")
    list_per_page = 50  # PERFORMANCE: Add pagination
    show_full_result_count = False
    search_fields = ("name", "asset_tag")


class GrantAllocationInline(admin.TabularInline):
    model = GrantAllocation
    extra = 0


class GrantAdmin(ModelAdmin):
    list_display = ("name", "funder", "amount", "start_date", "end_date")
    list_per_page = 50  # PERFORMANCE: Add pagination
    show_full_result_count = False
    search_fields = ("name", "funder")
    inlines = [GrantAllocationInline]


class NotificationAdmin(ModelAdmin):
    list_display = (
        "title",
        "severity",
        "is_read",
        "created_at",
        "recipient",
        "created_by",
    )
    list_filter = ("severity", "is_read")
    list_per_page = 50  # PERFORMANCE: Add pagination
    show_full_result_count = False
    search_fields = ("title", "message", "created_by__username", "recipient__username")


class FinanceRequestAuditAdmin(ModelAdmin):
    list_display = ("notification", "user", "action", "created_at")
    list_filter = ("action",)
    list_per_page = 50
    show_full_result_count = False
    search_fields = ("notification__title", "user__username")


class ReportRequestAdmin(ModelAdmin):
    list_display = ("report_type", "requested_by", "status", "created_at")
    list_filter = ("report_type", "status")
    list_per_page = 50  # PERFORMANCE: Add pagination
    show_full_result_count = False
    search_fields = ("requested_by__username", "description")


class CashOfficeClosureAdmin(ModelAdmin):
    list_display = (
        "profile",
        "closure_date",
        "status",
        "opening_cash",
        "cash_collected",
        "deposited_to_bank",
        "cash_on_hand",
        "discrepancy",
        "closed_by",
    )
    list_filter = ("status", "profile", "closure_date")
    show_full_result_count = False
    search_fields = ("profile__name", "deposit_reference", "notes")
    readonly_fields = (
        "expected_cash",
        "discrepancy",
        "closed_at",
        "created_at",
        "updated_at",
    )


class ReferralRewardAdmin(ModelAdmin):
    list_display = (
        "student",
        "guardian",
        "amount",
        "status",
        "awarded_by",
        "created_at",
    )
    list_filter = ("status",)
    list_per_page = 50  # PERFORMANCE: Add pagination
    show_full_result_count = False
    search_fields = (
        "student__student_code",
        "guardian__guardian_user__username",
        "guardian__guardian_user__email",
    )


# Register all models with tenant admin only
register_tenant_admin(ComplianceProfile, ComplianceProfileAdmin)
register_tenant_admin(TaxBracket, TaxBracketAdmin)
register_tenant_admin(ContributionRule, ContributionRuleAdmin)
register_tenant_admin(LedgerAccount, LedgerAccountAdmin)
register_tenant_admin(JournalEntry, JournalEntryAdmin)
register_tenant_admin(Counterparty, CounterpartyAdmin)
register_tenant_admin(FeePlan, FeePlanAdmin)
register_tenant_admin(FeeInstallment, FeeInstallmentAdmin)
register_tenant_admin(Invoice, InvoiceAdmin)
register_tenant_admin(Payment, PaymentAdmin)


class PaymentDisputeAdmin(ModelAdmin):
    list_display = ("id", "payment", "status", "reason", "raised_by", "created_at")
    list_filter = ("status", "reason")
    search_fields = ("description", "payment__reference_number")
    raw_id_fields = ("payment", "raised_by", "resolved_by")
    readonly_fields = ("created_at", "updated_at")


register_tenant_admin(PaymentDispute, PaymentDisputeAdmin)
register_tenant_admin(PaymentReminder, PaymentReminderAdmin)
register_tenant_admin(PaymentReminderLog, PaymentReminderLogAdmin)
register_tenant_admin(Budget, BudgetAdmin)
register_tenant_admin(BudgetLine, BudgetLineAdmin)
register_tenant_admin(AssetCategory, AssetCategoryAdmin)
register_tenant_admin(Asset, AssetAdmin)
register_tenant_admin(Grant, GrantAdmin)
register_tenant_admin(Notification, NotificationAdmin)
try:
    register_tenant_admin(FinanceRequestAudit, FinanceRequestAuditAdmin)
except AlreadyRegistered:
    pass
register_tenant_admin(ReportRequest, ReportRequestAdmin)
register_tenant_admin(CashOfficeClosure, CashOfficeClosureAdmin)
register_tenant_admin(ReferralReward, ReferralRewardAdmin)


class PaymentProofUploadAdmin(ModelAdmin):
    list_display = (
        "id",
        "invoice",
        "uploaded_by",
        "payment_method",
        "uploaded_amount",
        "status",
        "fraud_risk_score",
        "is_suspicious",
        "verification_confidence",
        "created_at",
        "verified_at",
    )
    list_filter = (
        "status",
        "payment_method",
        "is_suspicious",
        "created_at",
        "fraud_risk_score",
    )
    show_full_result_count = False
    search_fields = (
        "invoice__reference",
        "invoice__id",
        "transaction_reference",
        "uploaded_by__email",
        "uploaded_by__username",
    )
    readonly_fields = (
        "invoice",
        "uploaded_by",
        "receipt_file",
        "verification_data",
        "verification_confidence",
        "created_at",
        "verified_at",
        "payment",
    )
    fieldsets = (
        (
            "Upload Information",
            {
                "fields": (
                    "invoice",
                    "uploaded_by",
                    "receipt_file",
                    "payment_method",
                    "idempotency_key",
                    "created_at",
                )
            },
        ),
        (
            "Reassign (wrong invoice)",
            {
                "fields": ("reassign_to_invoice",),
                "description": "Set target invoice and save to move this receipt to another invoice (e.g. same student).",
            },
        ),
        (
            "Payment Details",
            {
                "fields": (
                    "transaction_reference",
                    "uploaded_amount",
                    "verification_notes",
                )
            },
        ),
        (
            "Verification",
            {
                "fields": (
                    "status",
                    "verification_data",
                    "verification_confidence",
                    "verified_by",
                    "verified_at",
                    "verification_reason",
                )
            },
        ),
        ("Result", {"fields": ("payment",)}),
    )

    def get_queryset(self, request):
        qs = (
            super()
            .get_queryset(request)
            .select_related(
                "invoice", "uploaded_by", "verified_by", "payment", "flagged_by"
            )
        )
        # Show suspicious receipts first
        return qs.order_by("-is_suspicious", "-fraud_risk_score", "-created_at")

    actions = ["approve_selected", "reject_selected"]

    def approve_selected(self, request, queryset):
        """Approve selected receipt uploads and create payments."""
        from apps.finance.services import create_payment_from_receipt
        from apps.finance.receipt_verification import ReceiptVerificationService

        school = getattr(queryset.select_related("school").first(), "school", None)
        site = get_effective_site_settings(school=school)
        require_reason = getattr(
            site, "finance_receipt_require_verification_reason", True
        )
        approved_count = 0
        for proof_upload in queryset.filter(
            status=PaymentProofUpload.Status.DISCREPANCY
        ):
            if require_reason and not (
                proof_upload.verification_reason or proof_upload.verification_notes
            ):
                self.message_user(
                    request,
                    f"Add a verification reason (or notes) to receipt #{proof_upload.id} before approving.",
                    level="error",
                )
                continue
            try:
                verification_service = ReceiptVerificationService()
                receipt_data = (
                    proof_upload.verification_data
                    or verification_service.extract_receipt_data(
                        proof_upload.receipt_file
                    )
                )
                _payment = create_payment_from_receipt(
                    proof_upload, receipt_data, verified_by=request.user
                )
                if proof_upload.verification_reason:
                    proof_upload.verification_notes = (
                        proof_upload.verification_notes or ""
                    ) + f" [Override reason: {proof_upload.verification_reason}]"
                    proof_upload.save(update_fields=["verification_notes"])
                approved_count += 1
            except (
                ValueError,
                TypeError,
                ValidationError,
                DatabaseError,
                IntegrityError,
            ) as e:
                self.message_user(
                    request,
                    f"Error approving {proof_upload.id}: {str(e)}",
                    level="error",
                )
        self.message_user(request, f"Approved {approved_count} receipt upload(s).")

    approve_selected.short_description = "Approve selected receipts and create payments"

    def reject_selected(self, request, queryset):
        """Reject selected receipt uploads (reason in verification_reason or verification_notes). Audited."""
        from apps.compliance.models_audit import AuditLog

        school = getattr(queryset.select_related("school").first(), "school", None)
        site = get_effective_site_settings(school=school)
        require_reason = getattr(
            site, "finance_receipt_require_verification_reason", True
        )
        to_reject = queryset.filter(
            status__in=[
                PaymentProofUpload.Status.PENDING,
                PaymentProofUpload.Status.DISCREPANCY,
            ]
        )
        for proof_upload in to_reject:
            if require_reason and not (
                proof_upload.verification_reason or proof_upload.verification_notes
            ):
                self.message_user(
                    request,
                    f"Add a verification reason (or notes) to receipt #{proof_upload.id} before rejecting.",
                    level="error",
                )
                return
            reason = (
                proof_upload.verification_reason
                or proof_upload.verification_notes
                or "Rejected by admin"
            )[:255]
            proof_upload.status = PaymentProofUpload.Status.REJECTED
            proof_upload.verified_by = request.user
            if not proof_upload.verification_notes:
                proof_upload.verification_notes = "Rejected by admin"
            if proof_upload.verification_reason:
                proof_upload.verification_notes += (
                    f" Reason: {proof_upload.verification_reason}"
                )
            proof_upload.save()
            try:
                AuditLog.objects.create(
                    action=AuditLog.Action.REJECT,
                    user=request.user,
                    model_name="PaymentProofUpload",
                    object_id=str(proof_upload.pk),
                    object_repr=str(proof_upload),
                    app_label="finance",
                    new_values={"status": "REJECTED"},
                    reason=reason,
                    sensitivity=AuditLog.Sensitivity.HIGH,
                )
            except (
                DatabaseError,
                IntegrityError,
                ValidationError,
                AttributeError,
            ) as e:
                import logging

                logging.getLogger(__name__).debug("AuditLog on reject_selected: %s", e)
        self.message_user(request, f"Rejected {to_reject.count()} receipt upload(s).")

    reject_selected.short_description = "Reject selected receipts"


register_tenant_admin(PaymentProofUpload, PaymentProofUploadAdmin)


class BankAccountAdmin(ModelAdmin):
    list_display = (
        "name",
        "account_type",
        "account_number",
        "bank_name",
        "currency",
        "is_active",
        "region",
    )
    list_filter = ("account_type", "is_active", "region", "currency")
    show_full_result_count = False
    search_fields = ("name", "account_number", "bank_name")
    fieldsets = (
        (
            "Account Information",
            {
                "fields": (
                    "name",
                    "account_type",
                    "account_number",
                    "bank_name",
                    "branch",
                    "currency",
                    "region",
                )
            },
        ),
        ("Status", {"fields": ("is_active", "notes")}),
    )


class BankStatementEntryAdmin(ModelAdmin):
    list_display = (
        "bank_account",
        "transaction_date",
        "amount",
        "transaction_type",
        "transaction_reference",
        "is_verified",
        "matched_receipt_upload",
    )
    list_filter = (
        "bank_account",
        "transaction_type",
        "is_verified",
        "transaction_date",
    )
    show_full_result_count = False
    search_fields = ("transaction_reference", "description", "bank_account__name")
    readonly_fields = ("matched_receipt_upload", "created_at", "imported_from")
    fieldsets = (
        (
            "Transaction Details",
            {
                "fields": (
                    "bank_account",
                    "transaction_date",
                    "amount",
                    "transaction_type",
                    "transaction_reference",
                    "description",
                    "balance_after",
                )
            },
        ),
        (
            "Verification",
            {
                "fields": (
                    "is_verified",
                    "matched_receipt_upload",
                    "imported_from",
                    "created_at",
                )
            },
        ),
    )


class BankStatementUploadAdmin(ModelAdmin):
    list_display = (
        "bank_account",
        "statement_period_start",
        "statement_period_end",
        "status",
        "entries_imported",
        "uploaded_by",
        "created_at",
    )
    list_filter = ("status", "bank_account", "created_at")
    show_full_result_count = False
    search_fields = ("bank_account__name",)
    readonly_fields = ("status", "entries_imported", "errors", "processed_at")
    actions = ["process_selected_uploads"]
    fieldsets = (
        (
            "Statement Information",
            {
                "fields": (
                    "bank_account",
                    "statement_file",
                    "statement_period_start",
                    "statement_period_end",
                    "uploaded_by",
                )
            },
        ),
        (
            "Import Status",
            {
                "fields": (
                    "status",
                    "entries_imported",
                    "errors",
                    "processed_at",
                    "created_at",
                )
            },
        ),
    )

    @admin.action(description="Process selected statement uploads")
    def process_selected_uploads(self, request, queryset):
        from apps.finance.bank_statement_import import BankStatementImportService

        service = BankStatementImportService()
        processed = 0
        failures = 0
        for upload in queryset:
            result = service.process_upload(upload)
            if result["status"] == BankStatementUpload.Status.FAILED:
                failures += 1
            else:
                processed += 1
        self.message_user(
            request,
            f"Processed {processed} upload(s); failures: {failures}.",
        )


class SuspensePaymentAllocationInline(admin.TabularInline):
    model = SuspensePaymentAllocation
    extra = 0
    autocomplete_fields = ("invoice", "payment")
    readonly_fields = ("created_at",)


class SuspensePaymentAdmin(ModelAdmin):
    list_display = (
        "id",
        "transaction_reference",
        "amount",
        "currency",
        "status",
        "suggested_invoice",
        "claimed_student",
        "claimed_by",
        "created_at",
    )
    show_full_result_count = False
    list_filter = ("status", "currency", "created_at")
    search_fields = (
        "transaction_reference",
        "payer_name",
        "payer_phone",
        "description",
    )
    readonly_fields = (
        "allocated_amount_display",
        "remaining_amount_display",
        "created_at",
        "updated_at",
    )
    autocomplete_fields = (
        "suggested_invoice",
        "suggested_student",
        "claimed_student",
        "claimed_by",
    )
    inlines = [SuspensePaymentAllocationInline]
    fieldsets = (
        (
            "Transaction",
            {
                "fields": (
                    "bank_statement_entry",
                    "transaction_reference",
                    "amount",
                    "currency",
                    "payer_name",
                    "payer_phone",
                    "description",
                )
            },
        ),
        (
            "Suggestion & Claim",
            {
                "fields": (
                    "status",
                    "suggested_invoice",
                    "suggested_student",
                    "claimed_student",
                    "claimed_by",
                    "claimed_at",
                    "resolved_at",
                    "notes",
                )
            },
        ),
        (
            "Allocation Summary",
            {"fields": ("allocated_amount_display", "remaining_amount_display")},
        ),
        ("Meta", {"fields": ("created_at", "updated_at", "raw_payload")}),
    )

    @admin.display(description="Allocated amount")
    def allocated_amount_display(self, obj):
        return obj.allocated_amount

    @admin.display(description="Remaining amount")
    def remaining_amount_display(self, obj):
        return obj.remaining_amount


# ----- Financial Aid & Scholarships (Phase 1, global platform) -----
class AwardSourceAdmin(ModelAdmin):
    list_display = (
        "name",
        "school",
        "total_budget",
        "remaining_funds",
        "currency",
        "is_active",
    )
    list_filter = ("school", "is_active", "currency")
    search_fields = ("name",)
    list_per_page = 50


class ScholarshipAdmin(ModelAdmin):
    list_display = (
        "title",
        "school",
        "source",
        "award_amount",
        "is_renewable",
        "is_active",
    )
    list_filter = ("school", "is_active")
    search_fields = ("title",)
    list_per_page = 50
    raw_id_fields = ("source",)


class FinancialAidApplicationAdmin(ModelAdmin):
    list_display = (
        "student",
        "scholarship",
        "status",
        "amount_approved",
        "disbursed_at",
        "created_at",
    )
    list_filter = ("school", "status")
    search_fields = ("student__first_name", "student__last_name", "scholarship__title")
    list_per_page = 50
    raw_id_fields = ("student", "scholarship", "dispute_link")
    readonly_fields = ("disbursed_at", "created_at", "updated_at")


class AidAuditLogAdmin(ModelAdmin):
    list_display = (
        "source",
        "action",
        "amount",
        "balance_after",
        "created_at",
        "created_by",
    )
    list_filter = ("school", "action")
    search_fields = ("reason",)
    list_per_page = 50
    readonly_fields = (
        "school",
        "source",
        "action",
        "amount",
        "balance_after",
        "reason",
        "application",
        "created_by",
        "created_at",
    )


register_tenant_admin(AwardSource, AwardSourceAdmin)
register_tenant_admin(Scholarship, ScholarshipAdmin)
register_tenant_admin(FinancialAidApplication, FinancialAidApplicationAdmin)
register_tenant_admin(AidAuditLog, AidAuditLogAdmin)

register_tenant_admin(BankAccount, BankAccountAdmin)
register_tenant_admin(BankStatementEntry, BankStatementEntryAdmin)
register_tenant_admin(BankStatementUpload, BankStatementUploadAdmin)
register_tenant_admin(SuspensePayment, SuspensePaymentAdmin)
