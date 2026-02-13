"""
Celery tasks for finance (payment reminders, fee generation, invoice status updates, etc.).
Run via: send_payment_reminders_task.delay()
Or synchronously from management command when no broker: task.apply()
"""
from __future__ import annotations

import logging
from decimal import Decimal
from datetime import timedelta

from django.conf import settings
from django.core.mail import EmailMessage
from django.core.cache import cache
from django.utils import timezone
from django.db import transaction

from celery import shared_task

from apps.finance.models import PaymentReminder, PaymentReminderLog, Invoice, FeePlan, PaymentProofUpload
from apps.finance.services import generate_payment_link, create_fee_invoices, recalculate_invoice, create_payment_from_receipt
from apps.finance.receipt_verification import ReceiptVerificationService
from apps.finance.fraud_detection import ReceiptFraudDetector
from apps.people.models import StudentGuardian
from apps.siteconfig.models import Integration, SiteSettings
from apps.automation.models import AutomationExecutionLog, AutomationApprovalQueue
from apps.automation.helpers import get_cached_site_settings, get_current_academic_year, get_current_term, get_notification_channels
from apps.evals.notifications import NotificationService

logger = logging.getLogger(__name__)


def _get_payment_instructions(invoice: Invoice) -> dict:
    """
    Get payment instructions (bank accounts, MoMo numbers, etc.) for invoice reminders.
    Returns dict with payment instruction variables for template formatting.
    """
    from apps.finance.models import BankAccount
    from apps.siteconfig.models import RegionConfig
    
    instructions = {
        "bank_account": "",
        "bank_name": "",
        "branch": "",
        "mtn_momo_number": "",
        "orange_money_number": "",
    }
    
    try:
        # Get region from invoice's profile
        profile = invoice.profile
        region = profile.region if hasattr(profile, 'region') else None
        
        if not region:
            # Try to get default region
            region = RegionConfig.objects.filter(is_active=True).first()
        
        if region:
            # Get bank accounts for this region
            bank_accounts = BankAccount.objects.filter(region=region, is_active=True)
            
            # Get bank account
            bank_account = bank_accounts.filter(account_type=BankAccount.AccountType.BANK).first()
            if bank_account:
                instructions["bank_account"] = bank_account.account_number
                instructions["bank_name"] = bank_account.bank_name or ""
                instructions["branch"] = bank_account.branch or ""
            
            # Get MTN MoMo
            mtn_account = bank_accounts.filter(account_type=BankAccount.AccountType.MTN_MOMO).first()
            if mtn_account:
                instructions["mtn_momo_number"] = mtn_account.account_number
            
            # Get Orange Money
            orange_account = bank_accounts.filter(account_type=BankAccount.AccountType.ORANGE_MONEY).first()
            if orange_account:
                instructions["orange_money_number"] = orange_account.account_number
    except Exception as e:
        logger.error(f"Error getting payment instructions: {str(e)}")
    
    return instructions


def _send_payment_email(to_email: str, subject: str, body: str, integration: Integration | None) -> None:
    if not to_email:
        return
    from_email = settings.DEFAULT_FROM_EMAIL
    if integration and integration.config:
        from_email = integration.config.get("from_email", from_email)
    email = EmailMessage(subject, body, from_email, [to_email])
    email.send(fail_silently=True)


def run_payment_reminders(dry_run: bool = False) -> dict:
    """
    Send payment reminders for upcoming invoice due dates. Supports multi-channel (email, SMS, WhatsApp).
    When dry_run=True, only computes and returns what would be sent; no emails/SMS/WhatsApp, no DB updates.
    Returns summary for logging/CLI.
    """
    now = timezone.now()
    reminders = list(
        PaymentReminder.objects.filter(is_active=True, next_send_at__lte=now).select_related("invoice", "invoice__student")
    )
    if not reminders:
        return {"sent": 0, "count": 0, "channels": {}, "dry_run": dry_run}

    integration = Integration.objects.filter(provider="email", enabled=True).first()
    default_link = getattr(settings, "SITE_URL", "https://school.example/")
    sent_count = 0
    channel_counts = {"email": 0, "sms": 0, "whatsapp": 0}
    notification_service = NotificationService()

    for reminder in reminders:
        lock_key = f"finance:payment-reminder:lock:{reminder.id}"
        if not cache.add(lock_key, "1", timeout=300):
            logger.info("Skipping reminder %s because another worker is already processing it.", reminder.id)
            continue
        try:
            invoice = reminder.invoice
            guardians = StudentGuardian.objects.filter(
                student=invoice.student,
                can_view_finance=True,
                guardian_user__is_active=True,
            ).select_related("guardian_user", "guardian_user__preferences")

            if not guardians:
                logger.info("No guardians configured for invoice %s.", invoice)
                continue

            payment_link = generate_payment_link(invoice)
            link_display = payment_link["url"] if payment_link else default_link
            due_display = invoice.due_date or timezone.localdate(now)

            # Get reminder channels (per-reminder override or SiteSettings default)
            channels = reminder.get_reminder_channels()
            reminder_active_channels = set()

            for guardian in guardians:
                guardian_user = guardian.guardian_user
                guardian_name = guardian_user.get_full_name() or guardian_user.username

                # Get user-specific channels (respects UserPreference)
                user_channels = get_notification_channels(guardian_user, "payment_reminder")
                # Use intersection: only send via channels both reminder and user support
                active_channels = [ch for ch in channels if ch in user_channels] if user_channels else channels

                # No contact: prefer StudentGuardian.email/phone, then guardian_user (see docs/DATA_PARENT_CONTACT.md)
                has_contact = bool(
                    (getattr(guardian, "email", None) or "").strip()
                    or (guardian_user.email or "").strip()
                    or getattr(guardian_user, "phone", None)
                    or getattr(guardian, "phone", None)
                    or getattr(guardian, "whatsapp_number", None)
                )
                if not has_contact:
                    no_contact_action = getattr(
                        SiteSettings.get_solo(),
                        "finance_reminder_no_contact_action",
                        "warn_only",
                    )
                    logger.warning(
                        "Payment reminder: no contact for guardian %s, invoice %s (student: %s)",
                        guardian_name,
                        invoice.reference or invoice.id,
                        invoice.student,
                    )
                    if no_contact_action == "create_task":
                        from apps.finance.models import Notification
                        from apps.accounts.models import User
                        finance_user = User.objects.filter(
                            is_staff=True,
                            groups__name__in=["Finance", "Bursar", "Accountant"],
                        ).first() or User.objects.filter(is_staff=True).first()
                        if finance_user:
                            Notification.objects.create(
                                title="Payment reminder: no contact for guardian",
                                message=f"Invoice {invoice.reference or invoice.id} ({invoice.student}). Guardian: {guardian_name}. Add email/phone or contact manually.",
                                link=f"/admin/finance/invoice/{invoice.id}/change/",
                                severity=Notification.Severity.WARNING,
                                recipient=finance_user,
                            )
                    continue
                if not active_channels:
                    continue

                # Get payment instructions from bank accounts
                payment_instructions = _get_payment_instructions(invoice)

                context = {
                    "guardian": guardian_name,
                    "amount": invoice.balance_amount,
                    "invoice": invoice.reference or invoice.id,
                    "due_date": due_display,
                    "link": link_display,
                    "payment_code": getattr(invoice, "payment_code", "") or "",
                    "receipt_upload_link": f"{default_link}finance/invoices/{invoice.id}/",
                    **payment_instructions,  # Include bank/MoMo numbers, etc.
                }

                for channel in active_channels:
                    reminder_active_channels.add(channel)
                    try:
                        template = reminder.get_message_template(channel)
                        # Format template with payment instructions
                        try:
                            body = template.format(**context)
                        except KeyError as e:
                            # If template variable missing, use default value
                            logger.warning(f"Missing template variable {e} in reminder template, using defaults")
                            # Fill missing variables with empty strings
                            safe_context = {k: v or "" for k, v in context.items()}
                            body = template.format(**safe_context)
                        subject = f"[Reminder] Pay {invoice.reference or invoice.id}"

                        if channel == "email":
                            to_email = (getattr(guardian, "email", None) or "").strip() or guardian_user.email or ""
                            if to_email:
                                _send_payment_email(to_email, subject, body, integration)
                                PaymentReminderLog.objects.create(
                                    reminder=reminder,
                                    status="SENT",
                                    note=f"Email sent to {to_email}",
                                )
                                channel_counts["email"] += 1
                                sent_count += 1

                        elif channel == "sms":
                            phone = getattr(guardian, "phone", None) or getattr(guardian_user, "phone", None)
                            if phone:
                                notification_service.send_sms(phone, body)
                                PaymentReminderLog.objects.create(
                                    reminder=reminder,
                                    status="SENT",
                                    note=f"SMS sent to {phone}",
                                )
                                channel_counts["sms"] += 1
                                sent_count += 1

                        elif channel == "whatsapp":
                            phone = getattr(guardian, "phone", None) or getattr(guardian, "whatsapp_number", None) or getattr(guardian_user, "phone", None)
                            if phone:
                                whatsapp_url = notification_service.send_whatsapp(guardian_user, "GENERIC", context)
                                PaymentReminderLog.objects.create(
                                    reminder=reminder,
                                    status="SENT",
                                    note=f"WhatsApp link generated for {phone}: {whatsapp_url}",
                                )
                                channel_counts["whatsapp"] += 1
                                sent_count += 1

                    except Exception as e:
                        logger.error("Error sending %s reminder for invoice %s: %s", channel, invoice.reference or invoice.id, str(e))
                        PaymentReminderLog.objects.create(
                            reminder=reminder,
                            status="FAILED",
                            note=f"Failed to send {channel}: {str(e)}",
                        )

            reminder.last_sent_at = now
            reminder.schedule_next()
            reminder.save(update_fields=["last_sent_at", "next_send_at"])
            logger.info(
                "Processed reminder for invoice %s via %s.",
                invoice.reference or invoice.id,
                ", ".join(sorted(reminder_active_channels)) or "no-channels",
            )
        finally:
            cache.delete(lock_key)

    return {"sent": sent_count, "count": len(reminders), "channels": channel_counts}


@shared_task(bind=True, name="finance.send_payment_reminders")
def send_payment_reminders_task(self, dry_run: bool = False) -> dict:
    """Celery task: send payment reminders for upcoming invoice due dates. Set dry_run=True to log what would be sent without sending."""
    execution_log = AutomationExecutionLog.objects.create(
        task_name="finance.send_payment_reminders",
        execution_type=AutomationExecutionLog.ExecutionType.DRY_RUN if dry_run else AutomationExecutionLog.ExecutionType.SCHEDULED,
        status=AutomationExecutionLog.Status.PENDING,
    )
    try:
        result = run_payment_reminders(dry_run=dry_run)
        sent = result.get("sent", 0)
        count = result.get("count", 0)
        execution_log.mark_completed(
            AutomationExecutionLog.Status.SUCCESS,
            records_processed=sent,
            records_failed=max(0, count - sent),
            summary={"channels": result.get("channels", {}), "count": count, "dry_run": dry_run},
        )
        return result
    except Exception as e:
        logger.exception("send_payment_reminders_task failed")
        execution_log.mark_completed(
            AutomationExecutionLog.Status.FAILED,
            error_message=str(e),
        )
        raise


@shared_task(bind=True, name="finance.retry_failed_payment_reminders")
def retry_failed_payment_reminders_task(self, dry_run: bool = False) -> dict:
    """
    Reset next_send_at for reminders that had FAILED sends, so the next reminder run will retry.
    Only retries if last failure was at least finance_reminder_retry_failed_hours ago.
    When dry_run=True, only reports how many would be reset; no DB updates.
    """
    from apps.finance.models import PaymentReminderLog

    execution_log = AutomationExecutionLog.objects.create(
        task_name="finance.retry_failed_payment_reminders",
        execution_type=AutomationExecutionLog.ExecutionType.DRY_RUN if dry_run else AutomationExecutionLog.ExecutionType.SCHEDULED,
        status=AutomationExecutionLog.Status.PENDING,
    )
    try:
        site = SiteSettings.get_solo()
        retry_hours = getattr(site, "finance_reminder_retry_failed_hours", 24) or 0
        max_retries = getattr(site, "finance_reminder_max_retries", 2) or 0
        if retry_hours <= 0:
            execution_log.mark_completed(
                AutomationExecutionLog.Status.SUCCESS,
                summary={"message": "Retry disabled (retry_hours <= 0)", "dry_run": dry_run},
            )
            return {"reset": 0, "dry_run": dry_run}

        cutoff = timezone.now() - timedelta(hours=retry_hours)
        reminder_ids_with_old_failure = set(
            PaymentReminderLog.objects.filter(status="FAILED", sent_at__lte=cutoff)
            .values_list("reminder_id", flat=True)
            .distinct()
        )
        reset_count = 0
        for reminder_id in reminder_ids_with_old_failure:
            reminder = PaymentReminder.objects.filter(id=reminder_id, is_active=True).first()
            if not reminder:
                continue
            last_log = reminder.logs.order_by("-sent_at").first()
            if not last_log or last_log.status != "FAILED" or last_log.sent_at > cutoff:
                continue
            failed_in_week = reminder.logs.filter(
                status="FAILED",
                sent_at__gte=timezone.now() - timedelta(days=7),
            ).count()
            if max_retries and failed_in_week > max_retries:
                continue
            if not dry_run:
                reminder.next_send_at = timezone.now()
                reminder.save(update_fields=["next_send_at"])
            reset_count += 1
        execution_log.mark_completed(
            AutomationExecutionLog.Status.SUCCESS,
            records_processed=reset_count,
            summary={"reset": reset_count, "dry_run": dry_run},
        )
        return {"reset": reset_count, "dry_run": dry_run}
    except Exception as e:
        logger.exception("retry_failed_payment_reminders_task failed")
        execution_log.mark_completed(
            AutomationExecutionLog.Status.FAILED,
            error_message=str(e),
        )
        raise


@shared_task(bind=True, name="finance.auto_generate_fee_invoices", autoretry_for=(Exception,), max_retries=3, retry_backoff=True)
def auto_generate_fee_invoices_task(self, dry_run: bool = False) -> dict:
    """
    Automatically generate fee invoices based on schedule configuration.
    
    Args:
        dry_run: If True, log what would be done but don't execute.
    
    Returns:
        Dict with execution summary
    """
    from apps.finance.models import ComplianceProfile
    from apps.automation.helpers import get_current_academic_year, get_current_term
    
    execution_log = AutomationExecutionLog.objects.create(
        task_name="finance.auto_generate_fee_invoices",
        execution_type=AutomationExecutionLog.ExecutionType.DRY_RUN if dry_run else AutomationExecutionLog.ExecutionType.SCHEDULED,
        status=AutomationExecutionLog.Status.PENDING,
    )
    
    try:
        site = get_cached_site_settings()
        
        if not getattr(site, "finance_auto_generate_invoices_enabled", False):
            execution_log.mark_completed(
                AutomationExecutionLog.Status.SUCCESS,
                summary={"message": "Fee auto-generation disabled in SiteSettings"}
            )
            return {"status": "disabled"}
        
        schedule = getattr(site, "finance_auto_generate_schedule", {})
        mode = schedule.get("mode", "academic_year_start")
        due_date_offset = getattr(site, "finance_auto_generate_due_date_offset_days", 30)
        
        current_year = get_current_academic_year()
        if not current_year:
            execution_log.mark_completed(
                AutomationExecutionLog.Status.FAILED,
                error_message="No active academic year found"
            )
            return {"status": "error", "message": "No active academic year"}
        
        # Check if generation is due based on schedule
        now = timezone.now().date()
        should_generate = False
        
        if mode == "academic_year_start":
            offset_days = schedule.get("academic_year_start_offset_days", 0)
            target_date = current_year.start_date + timedelta(days=offset_days)
            should_generate = now >= target_date
        
        elif mode == "term_start":
            current_term = get_current_term(current_year)
            if current_term:
                offset_days = schedule.get("term_start_offset_days", 0)
                target_date = current_term.start_date + timedelta(days=offset_days)
                should_generate = now >= target_date
        
        elif mode == "custom_date":
            custom_date_str = schedule.get("custom_date")
            if custom_date_str:
                from datetime import datetime
                target_date = datetime.fromisoformat(custom_date_str).date()
                should_generate = now >= target_date
        
        if not should_generate and not dry_run:
            execution_log.mark_completed(
                AutomationExecutionLog.Status.SUCCESS,
                summary={"message": "Generation not due yet"}
            )
            return {"status": "not_due"}
        
        # Get active fee plans
        plans = FeePlan.objects.filter(
            academic_year=current_year,
            is_active=True
        ).select_related("academic_year", "classroom", "specialty")
        
        if not plans.exists():
            execution_log.mark_completed(
                AutomationExecutionLog.Status.SUCCESS,
                summary={"message": "No active fee plans found"}
            )
            return {"status": "no_plans"}
        
        profile = site.compliance_profile
        if not profile:
            execution_log.mark_completed(
                AutomationExecutionLog.Status.FAILED,
                error_message="No compliance profile configured"
            )
            return {"status": "error", "message": "No compliance profile"}
        
        issued_date = now
        due_date = now + timedelta(days=due_date_offset)
        
        execution_summary = {
            "plans": [],
            "total_invoices": 0,
            "total_students": 0,
        }
        
        if dry_run:
            # Calculate what would be generated
            for plan in plans:
                from apps.finance.services import _student_for_plan
                students = list(_student_for_plan(plan))
                execution_summary["plans"].append({
                    "plan_id": plan.id,
                    "plan_name": plan.name,
                    "students_count": len(students),
                    "would_create_invoices": len(students),
                })
                execution_summary["total_students"] += len(students)
                execution_summary["total_invoices"] += len(students)
            
            execution_log.mark_completed(
                AutomationExecutionLog.Status.SUCCESS,
                records_processed=execution_summary["total_invoices"],
                summary=execution_summary
            )
            return {"dry_run": True, **execution_summary}
        
        # Check if approval required
        require_approval = getattr(site, "finance_auto_generate_require_approval", False)
        
        if require_approval:
            # Create approval queue entry
            queue_entry = AutomationApprovalQueue.objects.create(
                automation_type="fee_invoice_generation",
                execution_summary=execution_summary,
                status=AutomationApprovalQueue.Status.PENDING,
            )
            execution_log.mark_completed(
                AutomationExecutionLog.Status.SUCCESS,
                summary={"status": "pending_approval", "queue_id": queue_entry.id}
            )
            return {"status": "pending_approval", "queue_id": queue_entry.id}
        
        # Execute generation
        total_invoices = 0
        total_failed = 0
        
        for plan in plans:
            try:
                invoices = create_fee_invoices(
                    plan=plan,
                    profile=profile,
                    issued_date=issued_date,
                    due_date=due_date,
                )
                total_invoices += len(invoices)
                execution_summary["plans"].append({
                    "plan_id": plan.id,
                    "plan_name": plan.name,
                    "invoices_created": len(invoices),
                })
            except Exception as e:
                logger.error("Error generating invoices for plan %s: %s", plan.name, str(e))
                total_failed += 1
        
        execution_log.mark_completed(
            AutomationExecutionLog.Status.SUCCESS if total_failed == 0 else AutomationExecutionLog.Status.PARTIAL,
            records_processed=total_invoices,
            records_failed=total_failed,
            summary=execution_summary
        )
        
        return {
            "status": "success",
            "invoices_created": total_invoices,
            "plans_processed": len(plans),
            "failed": total_failed,
        }
    
    except Exception as e:
        logger.error("Error in auto_generate_fee_invoices_task: %s", str(e))
        execution_log.mark_completed(
            AutomationExecutionLog.Status.FAILED,
            error_message=str(e)
        )
        raise

@shared_task(bind=True, name="finance.auto_copy_fee_plans", autoretry_for=(Exception,), max_retries=3, retry_backoff=True)
def auto_copy_fee_plans_task(self, dry_run: bool = False) -> dict:
    """
    Copy active fee plans from a source academic year to the next year based on SiteSettings mode.
    """
    from apps.academics.models import AcademicYear
    from apps.finance.services import copy_fee_plan_to_year

    execution_log = AutomationExecutionLog.objects.create(
        task_name="finance.auto_copy_fee_plans",
        execution_type=AutomationExecutionLog.ExecutionType.DRY_RUN if dry_run else AutomationExecutionLog.ExecutionType.SCHEDULED,
        status=AutomationExecutionLog.Status.PENDING,
    )
    try:
        site = get_cached_site_settings()
        enabled = getattr(site, "finance_fee_plan_auto_copy_enabled", False)
        mode = getattr(site, "finance_fee_plan_auto_copy_mode", "manual")
        increase_pct = getattr(site, "finance_fee_plan_copy_increase_percentage", Decimal("0.00"))
        if not enabled or mode == "manual":
            execution_log.mark_completed(
                AutomationExecutionLog.Status.SUCCESS,
                summary={"message": "Fee plan auto-copy disabled or manual mode."},
            )
            return {"status": "disabled"}

        today = timezone.now().date()
        source_year = None
        if mode == "year_start":
            source_year = get_current_academic_year()
        elif mode == "year_end":
            source_year = AcademicYear.objects.filter(end_date__lt=today).order_by("-end_date").first()

        if not source_year:
            execution_log.mark_completed(
                AutomationExecutionLog.Status.SUCCESS,
                summary={"message": "No source academic year found for auto-copy.", "mode": mode},
            )
            return {"status": "no_source_year", "mode": mode}

        target_year = AcademicYear.objects.filter(start_date__gt=source_year.end_date).order_by("start_date").first()
        if not target_year:
            execution_log.mark_completed(
                AutomationExecutionLog.Status.SUCCESS,
                summary={
                    "message": "No target academic year found after source year.",
                    "source_year": source_year.name,
                },
            )
            return {"status": "no_target_year", "source_year": source_year.name}

        source_plans = FeePlan.objects.filter(academic_year=source_year, is_active=True).select_related(
            "classroom", "specialty", "academic_year"
        )
        if not source_plans.exists():
            execution_log.mark_completed(
                AutomationExecutionLog.Status.SUCCESS,
                summary={
                    "message": "No active fee plans to copy.",
                    "source_year": source_year.name,
                    "target_year": target_year.name,
                },
            )
            return {
                "status": "no_plans",
                "source_year": source_year.name,
                "target_year": target_year.name,
            }

        copied = 0
        skipped = 0
        errors = 0
        for plan in source_plans:
            candidate_name = f"{plan.name} ({target_year.name})"
            exists = FeePlan.objects.filter(
                academic_year=target_year,
                classroom=plan.classroom,
                specialty=plan.specialty,
                name=candidate_name,
            ).exists()
            if exists:
                skipped += 1
                continue

            if dry_run:
                copied += 1
                continue

            try:
                copy_fee_plan_to_year(plan, target_year, increase_pct)
                copied += 1
            except Exception as e:
                errors += 1
                logger.error(
                    "Error auto-copying fee plan %s from %s to %s: %s",
                    plan.id,
                    source_year.name,
                    target_year.name,
                    str(e),
                )

        task_status = (
            AutomationExecutionLog.Status.SUCCESS
            if errors == 0
            else AutomationExecutionLog.Status.PARTIAL
        )
        execution_log.mark_completed(
            task_status,
            records_processed=copied,
            records_failed=errors,
            summary={
                "mode": mode,
                "source_year": source_year.name,
                "target_year": target_year.name,
                "copied": copied,
                "skipped_existing": skipped,
                "errors": errors,
                "dry_run": dry_run,
            },
        )
        return {
            "status": "success",
            "mode": mode,
            "source_year": source_year.name,
            "target_year": target_year.name,
            "copied": copied,
            "skipped_existing": skipped,
            "errors": errors,
            "dry_run": dry_run,
        }
    except Exception as e:
        logger.error("Error in auto_copy_fee_plans_task: %s", str(e))
        execution_log.mark_completed(
            AutomationExecutionLog.Status.FAILED,
            error_message=str(e),
        )
        raise


@shared_task(bind=True, name="finance.update_invoice_statuses", autoretry_for=(Exception,), max_retries=3, retry_backoff=True)
def update_invoice_statuses_task(self, dry_run: bool = False) -> dict:
    """
    Automatically update invoice statuses (overdue, paid).
    
    Args:
        dry_run: If True, log what would be done but don't execute.
    
    Returns:
        Dict with execution summary
    """
    execution_log = AutomationExecutionLog.objects.create(
        task_name="finance.update_invoice_statuses",
        execution_type=AutomationExecutionLog.ExecutionType.DRY_RUN if dry_run else AutomationExecutionLog.ExecutionType.SCHEDULED,
        status=AutomationExecutionLog.Status.PENDING,
    )
    
    try:
        site = get_cached_site_settings()
        
        if not getattr(site, "finance_invoice_auto_status_updates_enabled", True):
            execution_log.mark_completed(
                AutomationExecutionLog.Status.SUCCESS,
                summary={"message": "Invoice status updates disabled"}
            )
            return {"status": "disabled"}
        
        grace_period = getattr(site, "finance_invoice_overdue_grace_period_days", 0)
        now = timezone.now().date()
        cutoff_date = now - timedelta(days=grace_period)
        
        # Find overdue invoices
        overdue_query = Invoice.objects.filter(
            due_date__lt=cutoff_date,
            status__in=[Invoice.Status.ISSUED, Invoice.Status.PARTIAL],
        )
        
        # Find paid invoices (balance = 0 but status not PAID)
        paid_query = Invoice.objects.filter(
            balance_amount=0,
        ).exclude(status=Invoice.Status.PAID)
        
        overdue_count = overdue_query.count()
        paid_count = paid_query.count()
        
        if dry_run:
            execution_log.mark_completed(
                AutomationExecutionLog.Status.SUCCESS,
                records_processed=overdue_count + paid_count,
                summary={
                    "would_mark_overdue": overdue_count,
                    "would_mark_paid": paid_count,
                }
            )
            return {
                "dry_run": True,
                "would_mark_overdue": overdue_count,
                "would_mark_paid": paid_count,
            }
        
        # Update overdue invoices
        overdue_updated = overdue_query.update(status=Invoice.Status.OVERDUE)
        
        # Update paid invoices
        paid_updated = paid_query.update(status=Invoice.Status.PAID)
        
        execution_log.mark_completed(
            AutomationExecutionLog.Status.SUCCESS,
            records_processed=overdue_updated + paid_updated,
            summary={
                "marked_overdue": overdue_updated,
                "marked_paid": paid_updated,
            }
        )
        
        return {
            "status": "success",
            "marked_overdue": overdue_updated,
            "marked_paid": paid_updated,
        }
    
    except Exception as e:
        logger.error("Error in update_invoice_statuses_task: %s", str(e))
        execution_log.mark_completed(
            AutomationExecutionLog.Status.FAILED,
            error_message=str(e)
        )
        raise


@shared_task(bind=True, name="finance.process_payment_receipt_upload", autoretry_for=(Exception,), max_retries=3, retry_backoff=True)
def process_payment_receipt_upload_task(self, proof_upload_id: int) -> dict:
    """
    Process a payment receipt upload: extract data, verify against invoice, and auto-apply if verified.

    Args:
        proof_upload_id: PaymentProofUpload ID

    Returns:
        {
            "status": "verified" | "discrepancy" | "rejected",
            "payment_id": int | None,
            "confidence": float,
            "discrepancies": list[str]
        }
    """
    execution_log = AutomationExecutionLog.objects.create(
        task_name="finance.process_payment_receipt_upload",
        execution_type=AutomationExecutionLog.ExecutionType.MANUAL,
        status=AutomationExecutionLog.Status.PENDING,
    )
    try:
        proof_upload = PaymentProofUpload.objects.select_related("invoice", "uploaded_by").get(id=proof_upload_id)

        # Update status to VERIFYING
        proof_upload.status = PaymentProofUpload.Status.VERIFYING
        proof_upload.save(update_fields=["status"])
        
        # Get SiteSettings
        site_settings = get_cached_site_settings()
        verification_method = getattr(site_settings, "finance_receipt_verification_method", "pattern")
        auto_apply_threshold = float(getattr(site_settings, "finance_receipt_auto_apply_threshold", 0.9))
        auto_apply_enabled = getattr(site_settings, "finance_receipt_auto_apply_enabled", True)
        require_approval = getattr(site_settings, "finance_receipt_require_admin_approval", False)
        amount_tolerance = Decimal(str(getattr(site_settings, "finance_receipt_amount_tolerance", "1.00")))
        
        # Extract receipt data
        verification_service = ReceiptVerificationService(
            verification_method=verification_method,
            marksheet_ocr_command=getattr(site_settings, "marksheet_ocr_command", ""),
        )
        receipt_data = verification_service.extract_receipt_data(proof_upload.receipt_file)
        
        # Update proof upload with extracted data
        proof_upload.verification_data = receipt_data
        proof_upload.verification_confidence = receipt_data.get("confidence", 0.0)
        
        # Extract receipt date for fraud detection
        receipt_date_str = receipt_data.get("date")
        if receipt_date_str:
            from datetime import datetime
            try:
                # Parse date
                fraud_detector = ReceiptFraudDetector()
                receipt_date = fraud_detector._parse_date(receipt_date_str)
                if receipt_date:
                    proof_upload.receipt_date = receipt_date
            except:
                pass
        
        # Use extracted amount if available, otherwise use uploaded amount
        if receipt_data.get("amount"):
            proof_upload.uploaded_amount = receipt_data["amount"]
        if receipt_data.get("reference") and not proof_upload.transaction_reference:
            proof_upload.transaction_reference = receipt_data["reference"]
        
        # Re-run fraud detection with extracted date
        if not proof_upload.fraud_flags:  # Only if not already flagged
            fraud_detector = ReceiptFraudDetector()
            fraud_result = fraud_detector.detect_fraud(
                receipt_file=proof_upload.receipt_file,
                receipt_date=receipt_date_str,
                transaction_reference=proof_upload.transaction_reference,
                uploaded_by_id=proof_upload.uploaded_by_id,
                invoice_id=proof_upload.invoice_id,
                uploaded_amount=proof_upload.uploaded_amount,
                ip_address=proof_upload.ip_address,
                user_agent=proof_upload.user_agent
            )
            proof_upload.fraud_risk_score = fraud_result["fraud_risk_score"]
            proof_upload.fraud_flags = fraud_result["fraud_flags"]
            proof_upload.is_suspicious = fraud_result["recommendation"] in ["review", "reject"]
            if proof_upload.is_suspicious and not proof_upload.flagged_at:
                proof_upload.flagged_at = timezone.now()

        # Verify against invoice (before bank verification so confidence can be adjusted)
        verification_result = verification_service.verify_receipt_match(
            receipt_data,
            proof_upload.invoice,
            amount_tolerance=amount_tolerance
        )

        # Run bank deposit verification (if enabled)
        from apps.siteconfig.models import SiteSettings
        site_settings = SiteSettings.get_solo()
        if getattr(site_settings, "finance_bank_verification_enabled", True):
            from apps.finance.bank_verification import BankDepositVerifier
            verifier = BankDepositVerifier()
            
            # Get relevant bank statements
            from apps.finance.models import BankAccount, BankStatementEntry
            
            if proof_upload.payment_method == "BANK":
                accounts = BankAccount.objects.filter(
                    account_type=BankAccount.AccountType.BANK,
                    is_active=True
                )
            elif proof_upload.payment_method == "MTN_MOMO":
                accounts = BankAccount.objects.filter(
                    account_type=BankAccount.AccountType.MTN_MOMO,
                    is_active=True
                )
            elif proof_upload.payment_method == "ORANGE_MOMO":
                accounts = BankAccount.objects.filter(
                    account_type=BankAccount.AccountType.ORANGE_MONEY,
                    is_active=True
                )
            else:
                accounts = BankAccount.objects.none()
            
            if accounts.exists():
                # Get bank statements
                all_statements = []
                for account in accounts:
                    statements = BankStatementEntry.objects.filter(
                        bank_account=account,
                        transaction_type__in=[
                            BankStatementEntry.TransactionType.DEPOSIT,
                            BankStatementEntry.TransactionType.TRANSFER_IN
                        ]
                    )
                    all_statements.extend(list(statements))
                
                # Verify deposit
                tolerance_days = int(getattr(site_settings, "finance_bank_verification_tolerance_days", 7))
                
                if proof_upload.payment_method == "MTN_MOMO":
                    bank_verification_result = verifier.verify_mtn_momo_deposit(
                        proof_upload,
                        [s for s in all_statements if s.bank_account.account_type == BankAccount.AccountType.MTN_MOMO]
                    )
                elif proof_upload.payment_method == "ORANGE_MOMO":
                    bank_verification_result = verifier.verify_orange_money_deposit(
                        proof_upload,
                        [s for s in all_statements if s.bank_account.account_type == BankAccount.AccountType.ORANGE_MONEY]
                    )
                else:
                    bank_verification_result = verifier.verify_deposit(
                        proof_upload,
                        all_statements,
                        tolerance_days=tolerance_days
                    )
                
                # Update bank verification fields
                proof_upload.bank_verified = bank_verification_result["verified"]
                proof_upload.bank_verification_date = timezone.now() if bank_verification_result["verified"] else None
                proof_upload.bank_verification_method = bank_verification_result["match_method"]
                proof_upload.bank_statement_entry = bank_verification_result.get("matched_entry")
                proof_upload.bank_verification_notes = "; ".join(bank_verification_result.get("discrepancies", []))
                proof_upload.last_verification_attempt = timezone.now()
                
                # If not verified, increment retry count (for delayed verification)
                if not bank_verification_result["verified"]:
                    proof_upload.verification_retry_count += 1
                
                # If bank verified, increase confidence
                if bank_verification_result["verified"]:
                    verification_result["confidence"] = min(
                        verification_result["confidence"] + 0.1,
                        1.0
                    )
                else:
                    # If bank verification failed, reduce confidence
                    verification_result["confidence"] = max(
                        verification_result["confidence"] - 0.2,
                        0.0
                    )
                    if not proof_upload.verification_notes:
                        proof_upload.verification_notes = ""
                    proof_upload.verification_notes += f" Bank verification failed: {bank_verification_result.get('discrepancies', ['No match'])[0]}"
        
        # This task does not support dry_run; auto-apply is controlled by site settings only.
        dry_run = False

        # If fraud risk is high, force review regardless of verification
        if proof_upload.fraud_risk_score >= 70:
            should_auto_apply = False
            proof_upload.status = PaymentProofUpload.Status.DISCREPANCY
            proof_upload.verification_notes = (
                f"⚠️ HIGH FRAUD RISK ({proof_upload.fraud_risk_score}/100). "
                f"Flags: {', '.join(proof_upload.fraud_flags)}. "
                f"Requires manual review. "
            ) + proof_upload.verification_notes
            proof_upload.is_suspicious = True
            proof_upload.flagged_at = timezone.now()
            
            # Notify finance staff
            _notify_finance_staff_suspicious_receipt(proof_upload, {
                "fraud_risk_score": proof_upload.fraud_risk_score,
                "fraud_flags": proof_upload.fraud_flags,
                "recommendation": "reject"
            })

        # Determine if we should auto-apply (skip in dry_run)
        should_auto_apply = (
            not dry_run and
            auto_apply_enabled and
            not require_approval and
            verification_result["matches"] and
            verification_result["confidence"] >= auto_apply_threshold
        )
        
        if dry_run:
            # Report only; do not create payment or change status beyond VERIFYING
            proof_upload.verification_notes = (proof_upload.verification_notes or "") + " [Dry run: verification only; no payment applied.]"
            proof_upload.status = PaymentProofUpload.Status.DISCREPANCY
            proof_upload.save(update_fields=["verification_notes", "status"])
            execution_log.mark_completed(
                AutomationExecutionLog.Status.SUCCESS,
                records_processed=1,
                summary={
                    "dry_run": True,
                    "would_apply": (
                        auto_apply_enabled and
                        not require_approval and
                        verification_result["matches"] and
                        verification_result["confidence"] >= auto_apply_threshold and
                        proof_upload.fraud_risk_score < 70
                    ),
                    "confidence": verification_result["confidence"],
                    "discrepancies": verification_result.get("discrepancies", []),
                },
            )
            return {
                "status": "discrepancy",
                "payment_id": None,
                "confidence": verification_result["confidence"],
                "discrepancies": verification_result.get("discrepancies", []),
                "dry_run": True,
            }
        
        if should_auto_apply:
            # Create and apply payment
            payment = create_payment_from_receipt(proof_upload, receipt_data)
            
            # Send notification to parent
            try:
                notification_service = NotificationService()
                channels = get_notification_channels(proof_upload.uploaded_by, "payment_verified")
                message = (
                    f"Your payment receipt for invoice {proof_upload.invoice.reference or proof_upload.invoice.id} "
                    f"has been verified and payment of {payment.amount} has been applied."
                )
                notification_service.send_notification(
                    user=proof_upload.uploaded_by,
                    title="Payment Verified",
                    message=message,
                    channels=channels,
                )
            except Exception as e:
                logger.error("Failed to send notification for verified payment: %s", str(e))
            
            logger.info(
                f"Payment receipt {proof_upload_id} verified and payment {payment.id} applied automatically"
            )
            execution_log.mark_completed(
                AutomationExecutionLog.Status.SUCCESS,
                records_processed=1,
                summary={"status": "verified", "payment_id": payment.id},
            )
            return {
                "status": "verified",
                "payment_id": payment.id,
                "confidence": verification_result["confidence"],
                "discrepancies": []
            }
        else:
            # Flag for review
            proof_upload.status = PaymentProofUpload.Status.DISCREPANCY
            proof_upload.verification_notes = "; ".join(verification_result.get("discrepancies", []))
            if verification_result["confidence"] < auto_apply_threshold:
                proof_upload.verification_notes += f" (Confidence: {verification_result['confidence']:.2f} < threshold: {auto_apply_threshold})"
            proof_upload.save()
            
            # Send notification to finance staff if suspicious
            if proof_upload.is_suspicious:
                _notify_finance_staff_suspicious_receipt(proof_upload, {
                    "fraud_risk_score": proof_upload.fraud_risk_score,
                    "fraud_flags": proof_upload.fraud_flags,
                    "recommendation": "review"
                })
            
            logger.info(
                f"Payment receipt {proof_upload_id} flagged for review: {proof_upload.verification_notes}"
            )
            execution_log.mark_completed(
                AutomationExecutionLog.Status.SUCCESS,
                records_processed=1,
                summary={"status": "discrepancy"},
            )
            return {
                "status": "discrepancy",
                "payment_id": None,
                "confidence": verification_result["confidence"],
                "discrepancies": verification_result.get("discrepancies", []),
                "dry_run": False,
            }

    except PaymentProofUpload.DoesNotExist:
        logger.error(f"PaymentProofUpload {proof_upload_id} not found")
        execution_log.mark_completed(
            AutomationExecutionLog.Status.FAILED,
            error_message="Proof upload not found",
        )
        return {"status": "error", "error": "Proof upload not found"}
    except Exception as e:
        logger.error("Error processing payment receipt upload %s: %s", proof_upload_id, str(e))
        execution_log.mark_completed(
            AutomationExecutionLog.Status.FAILED,
            error_message=str(e),
        )
        # Update status to indicate error
        try:
            proof_upload = PaymentProofUpload.objects.get(id=proof_upload_id)
            proof_upload.status = PaymentProofUpload.Status.DISCREPANCY
            proof_upload.verification_notes = f"Error during verification: {str(e)}"
            proof_upload.save()
        except Exception:
            pass
        raise


def _notify_finance_staff_suspicious_receipt(proof_upload: PaymentProofUpload, fraud_result: dict) -> None:
    """Notify finance staff when suspicious receipt is detected."""
    from apps.accounts.models import User
    from apps.evals.notifications import NotificationService
    
    try:
        # Get finance staff (users with finance permissions)
        finance_staff = User.objects.filter(
            is_staff=True,
            groups__name__in=["Finance", "Bursar", "Accountant"]
        ).distinct()
        
        # If no specific finance group, notify all staff
        if not finance_staff.exists():
            finance_staff = User.objects.filter(is_staff=True, is_superuser=False)
        
        notification_service = NotificationService()
        
        fraud_flags_str = ", ".join(fraud_result.get("fraud_flags", []))
        message = (
            f"⚠️ SUSPICIOUS RECEIPT DETECTED\n\n"
            f"Invoice: {proof_upload.invoice.reference or proof_upload.invoice.id}\n"
            f"Student: {proof_upload.invoice.student}\n"
            f"Uploaded by: {proof_upload.uploaded_by.get_full_name() if proof_upload.uploaded_by else 'Unknown'}\n"
            f"Amount: {proof_upload.uploaded_amount or 'Not specified'}\n"
            f"Fraud Risk Score: {fraud_result.get('fraud_risk_score', 0)}/100\n"
            f"Flags: {fraud_flags_str}\n"
            f"Recommendation: {fraud_result.get('recommendation', 'review').upper()}\n\n"
            f"Please review immediately: /admin/finance/paymentproofupload/{proof_upload.id}/change/"
        )
        
        for staff_member in finance_staff[:10]:  # Limit to 10 staff to avoid spam
            try:
                notification_service.send_notification(
                    user=staff_member,
                    title="🚨 Suspicious Receipt Detected",
                    message=message,
                    channels=["email"],  # Always email for critical alerts
                )
            except Exception as e:
                logger.error(f"Failed to notify finance staff {staff_member.id}: {str(e)}")
    
    except Exception as e:
        logger.error(f"Error notifying finance staff about suspicious receipt: {str(e)}")


@shared_task(bind=True, name="finance.retry_bank_verification", autoretry_for=(Exception,), max_retries=3, retry_backoff=True)
def retry_bank_verification_task(self, days_old: int = 30) -> dict:
    """
    Retry bank verification for receipts that failed verification earlier.
    Useful when bank statements are uploaded later (e.g., monthly statements).
    
    Args:
        days_old: Only retry receipts older than this many days (default: 30)
    
    Returns:
        {
            "retried": int,
            "verified": int,
            "still_pending": int
        }
    """
    execution_log = AutomationExecutionLog.objects.create(
        task_name="finance.retry_bank_verification",
        execution_type=AutomationExecutionLog.ExecutionType.SCHEDULED,
        status=AutomationExecutionLog.Status.PENDING,
    )
    try:
        from apps.finance.bank_verification import BankDepositVerifier
        from apps.finance.models import BankAccount, BankStatementEntry
        from apps.siteconfig.models import SiteSettings

        verifier = BankDepositVerifier()
        site_settings = SiteSettings.get_solo()
        tolerance_days = int(getattr(site_settings, "finance_bank_verification_tolerance_days", 7))

        # Get receipts that failed bank verification and are old enough
        cutoff_date = timezone.now() - timedelta(days=days_old)
        pending_receipts = PaymentProofUpload.objects.filter(
            bank_verified=False,
            payment_method__in=["BANK", "MTN_MOMO", "ORANGE_MOMO"],
            created_at__lte=cutoff_date,
            status__in=[
                PaymentProofUpload.Status.PENDING,
                PaymentProofUpload.Status.DISCREPANCY
            ]
        ).select_related("invoice", "uploaded_by")

        retried_count = 0
        verified_count = 0
        still_pending_count = 0
        error_count = 0

        for receipt_upload in pending_receipts:
            try:
                # Get relevant bank accounts
                if receipt_upload.payment_method == "BANK":
                    accounts = BankAccount.objects.filter(
                        account_type=BankAccount.AccountType.BANK,
                        is_active=True
                    )
                elif receipt_upload.payment_method == "MTN_MOMO":
                    accounts = BankAccount.objects.filter(
                        account_type=BankAccount.AccountType.MTN_MOMO,
                        is_active=True
                    )
                elif receipt_upload.payment_method == "ORANGE_MOMO":
                    accounts = BankAccount.objects.filter(
                        account_type=BankAccount.AccountType.ORANGE_MONEY,
                        is_active=True
                    )
                else:
                    continue

                # Get bank statements
                all_statements = []
                for account in accounts:
                    statements = BankStatementEntry.objects.filter(
                        bank_account=account,
                        transaction_type__in=[
                            BankStatementEntry.TransactionType.DEPOSIT,
                            BankStatementEntry.TransactionType.TRANSFER_IN
                        ]
                    )
                    all_statements.extend(list(statements))

                # Verify deposit
                if receipt_upload.payment_method == "MTN_MOMO":
                    verification_result = verifier.verify_mtn_momo_deposit(
                        receipt_upload,
                        [s for s in all_statements if s.bank_account.account_type == BankAccount.AccountType.MTN_MOMO]
                    )
                elif receipt_upload.payment_method == "ORANGE_MOMO":
                    verification_result = verifier.verify_orange_money_deposit(
                        receipt_upload,
                        [s for s in all_statements if s.bank_account.account_type == BankAccount.AccountType.ORANGE_MONEY]
                    )
                else:
                    verification_result = verifier.verify_deposit(
                        receipt_upload,
                        all_statements,
                        tolerance_days=tolerance_days
                    )

                # Update receipt upload
                receipt_upload.bank_verified = verification_result["verified"]
                receipt_upload.bank_verification_date = timezone.now() if verification_result["verified"] else None
                receipt_upload.bank_verification_method = verification_result["match_method"]
                receipt_upload.bank_statement_entry = verification_result.get("matched_entry")
                receipt_upload.bank_verification_notes = "; ".join(verification_result.get("discrepancies", []))
                receipt_upload.last_verification_attempt = timezone.now()
                receipt_upload.verification_retry_count += 1

                if verification_result["verified"]:
                    verified_count += 1
                    # Auto-approve if enabled
                    if getattr(site_settings, "finance_bank_verification_auto_approve", False):
                        receipt_data = receipt_upload.verification_data or {}
                        create_payment_from_receipt(receipt_upload, receipt_data)
                else:
                    still_pending_count += 1

                receipt_upload.save()
                retried_count += 1
            except Exception as e:
                error_count += 1
                logger.error("Error retrying bank verification for receipt %s: %s", receipt_upload.id, str(e))

        task_status = (
            AutomationExecutionLog.Status.SUCCESS
            if error_count == 0
            else AutomationExecutionLog.Status.PARTIAL
        )
        execution_log.mark_completed(
            task_status,
            records_processed=retried_count,
            records_failed=error_count,
            summary={
                "retried": retried_count,
                "verified": verified_count,
                "still_pending": still_pending_count,
                "errors": error_count,
            },
        )
        return {
            "retried": retried_count,
            "verified": verified_count,
            "still_pending": still_pending_count,
            "errors": error_count,
        }
    except Exception as e:
        logger.exception("retry_bank_verification_task failed")
        execution_log.mark_completed(
            AutomationExecutionLog.Status.FAILED,
            error_message=str(e),
        )
        raise
