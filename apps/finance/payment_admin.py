"""Payment Admin Classes for Phase 2.0"""
from django.contrib import admin
from django.utils.html import format_html
from apps.finance.models import Payment, Transaction, RefundRequest, PaymentReconciliation, PaymentAuditLog


@admin.register(Payment)
class PaymentAdmin(admin.ModelAdmin):
    """Admin for Payment model."""
    
    list_display = ('reference_number', 'student', 'amount_display', 'status_badge', 'payment_method', 'created_at')
    list_filter = ('status', 'purpose', 'region', 'payment_method', 'created_at')
    search_fields = ('reference_number', 'student__user__username', 'student__admission_number')
    readonly_fields = ('id', 'gateway_transaction_id', 'created_at', 'initiated_at', 'completed_at', 'failed_at', 'gateway_response')
    fieldsets = (
        ('Payment Info', {
            'fields': ('id', 'reference_number', 'student', 'region', 'payment_method')
        }),
        ('Amount & Purpose', {
            'fields': ('amount', 'currency_code', 'purpose', 'description')
        }),
        ('Status', {
            'fields': ('status', 'status_reason', 'processed_by')
        }),
        ('Gateway Info', {
            'fields': ('gateway_transaction_id', 'gateway_response'),
            'classes': ('collapse',)
        }),
        ('Compliance', {
            'fields': ('compliance_checked', 'compliance_issues'),
            'classes': ('collapse',)
        }),
        ('Timestamps', {
            'fields': ('created_at', 'initiated_at', 'completed_at', 'failed_at'),
            'classes': ('collapse',)
        }),
    )
    
    def amount_display(self, obj):
        return f"{obj.amount} {obj.currency_code}"
    amount_display.short_description = 'Amount'
    
    def status_badge(self, obj):
        colors = {
            'pending': '#FFA500',
            'processing': '#87CEEB',
            'completed': '#90EE90',
            'failed': '#FF6347',
            'refunded': '#FFB6C1',
            'cancelled': '#D3D3D3'
        }
        return format_html(
            '<span style="background-color: {}; padding: 5px 10px; border-radius: 3px; color: white;">{}</span>',
            colors.get(obj.status, '#808080'),
            obj.get_status_display()
        )
    status_badge.short_description = 'Status'


@admin.register(Transaction)
class TransactionAdmin(admin.ModelAdmin):
    """Admin for Transaction model."""
    
    list_display = ('id', 'payment', 'transaction_type', 'amount_display', 'status_badge', 'timestamp')
    list_filter = ('transaction_type', 'status', 'timestamp')
    search_fields = ('payment__reference_number', 'gateway_reference')
    readonly_fields = ('id', 'timestamp', 'metadata')
    
    def amount_display(self, obj):
        return f"{obj.amount} {obj.currency}"
    amount_display.short_description = 'Amount'
    
    def status_badge(self, obj):
        colors = {'success': '#90EE90', 'failed': '#FF6347', 'pending': '#FFA500'}
        return format_html(
            '<span style="background-color: {}; padding: 5px 10px; border-radius: 3px; color: white;">{}</span>',
            colors.get(obj.status, '#808080'),
            obj.get_status_display()
        )
    status_badge.short_description = 'Status'


@admin.register(RefundRequest)
class RefundRequestAdmin(admin.ModelAdmin):
    """Admin for RefundRequest model."""
    
    list_display = ('id', 'payment', 'amount_display', 'reason', 'status_badge', 'created_at')
    list_filter = ('status', 'reason', 'created_at')
    search_fields = ('payment__reference_number', 'description')
    readonly_fields = ('id', 'created_at', 'updated_at', 'processed_at')
    fieldsets = (
        ('Refund Info', {
            'fields': ('id', 'payment', 'region', 'amount', 'reason', 'description')
        }),
        ('Status', {
            'fields': ('status', 'status_notes', 'approved_by')
        }),
        ('Processing', {
            'fields': ('requested_by', 'processed_at', 'created_at', 'updated_at')
        }),
    )
    
    def amount_display(self, obj):
        return f"{obj.amount}"
    amount_display.short_description = 'Refund Amount'
    
    def status_badge(self, obj):
        colors = {
            'pending': '#FFA500',
            'approved': '#87CEEB',
            'rejected': '#FF6347',
            'processed': '#90EE90'
        }
        return format_html(
            '<span style="background-color: {}; padding: 5px 10px; border-radius: 3px; color: white;">{}</span>',
            colors.get(obj.status, '#808080'),
            obj.get_status_display()
        )
    status_badge.short_description = 'Status'


@admin.register(PaymentReconciliation)
class PaymentReconciliationAdmin(admin.ModelAdmin):
    """Admin for PaymentReconciliation model."""
    
    list_display = ('region', 'payment_method', 'period_display', 'net_amount_display', 'status_badge')
    list_filter = ('status', 'period_end', 'region', 'payment_method')
    readonly_fields = ('id', 'created_at', 'reconciled_at')
    fieldsets = (
        ('Period', {
            'fields': ('id', 'region', 'payment_method', 'period_start', 'period_end')
        }),
        ('Totals', {
            'fields': ('total_payments', 'total_refunds', 'total_fees', 'net_amount')
        }),
        ('Reconciliation', {
            'fields': ('status', 'discrepancy_amount', 'discrepancy_notes', 'reconciled_by')
        }),
        ('Timestamps', {
            'fields': ('created_at', 'reconciled_at'),
            'classes': ('collapse',)
        }),
    )
    
    def period_display(self, obj):
        return f"{obj.period_start} to {obj.period_end}"
    period_display.short_description = 'Period'
    
    def net_amount_display(self, obj):
        color = 'green' if obj.net_amount > 0 else 'red'
        return format_html('<span style="color: {};">{}</span>', color, obj.net_amount)
    net_amount_display.short_description = 'Net Amount'
    
    def status_badge(self, obj):
        colors = {'pending': '#FFA500', 'reconciled': '#90EE90', 'discrepancy': '#FF6347'}
        return format_html(
            '<span style="background-color: {}; padding: 5px 10px; border-radius: 3px; color: white;">{}</span>',
            colors.get(obj.status, '#808080'),
            obj.get_status_display()
        )
    status_badge.short_description = 'Status'


@admin.register(PaymentAuditLog)
class PaymentAuditLogAdmin(admin.ModelAdmin):
    """Admin for PaymentAuditLog model."""
    
    list_display = ('action_type', 'region', 'severity_badge', 'user', 'timestamp')
    list_filter = ('action_type', 'severity', 'timestamp', 'region')
    search_fields = ('description', 'user__username')
    readonly_fields = ('id', 'timestamp', 'details')
    
    def severity_badge(self, obj):
        colors = {'low': '#90EE90', 'medium': '#FFA500', 'high': '#FF6347', 'critical': '#8B0000'}
        return format_html(
            '<span style="background-color: {}; padding: 5px 10px; border-radius: 3px; color: white;">{}</span>',
            colors.get(obj.severity, '#808080'),
            obj.get_severity_display()
        )
    severity_badge.short_description = 'Severity'
    
    # No add/delete for audit logs
    def has_add_permission(self, request):
        return False
    
    def has_delete_permission(self, request, obj=None):
        return False
