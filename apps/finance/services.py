from __future__ import annotations

import hashlib
import hmac
import logging
import uuid
from collections import defaultdict
from datetime import date
from decimal import Decimal, InvalidOperation, ROUND_DOWN
from typing import TYPE_CHECKING, Iterable

from django.conf import settings
from django.db import transaction
from django.db.models import Count, Q, Sum
from django.db.utils import DatabaseError
from django.core.exceptions import ObjectDoesNotExist, ImproperlyConfigured
from django.urls.exceptions import NoReverseMatch
from django.urls import reverse
from django.utils import timezone

from apps.apicenter.gating import is_integration_allowed
from apps.global_registries.models import RegionConfig
from apps.integrations_marketplace.models import Integration
from apps.people.models import StudentProfile, StudentGuardian
from apps.platform_runtime.helpers import get_platform_defaults
from apps.siteconfig.config_service import get_effective_site_settings

from .json_decimal import quantize_money

from .models import (
    ComplianceProfile,
    FeeInstallment,
    FeeItem,
    FeePlan,
    Invoice,
    InvoicePayerShare,
    InvoicePayerSharePaymentAllocation,
    InvoiceLine,
    JournalEntry,
    JournalLine,
    LedgerAccount,
    ParentWallet,
    Payment,
    PaymentMethodCode,
    PaymentProofUpload,
    RefundRequest,
    WalletTransaction,
)

if TYPE_CHECKING:  # annotation-only; not evaluated at runtime (PEP 563)
    from apps.accounts.models import User
    from apps.schools.models import School

logger = logging.getLogger(__name__)


PAYMENT_METHOD_PROVIDER_SLUGS = {
    PaymentMethodCode.MTN_MOMO: "mtn_momo",
    PaymentMethodCode.ORANGE_MOMO: "orange_momo",
}
PROVIDER_SLUG_ALIASES = {
    "mtn": "mtn_momo",
    "mtnmomo": "mtn_momo",
    "orange": "orange_momo",
    "orange_money": "orange_momo",
    "mpesa": "mpesa_daraja",
    "mpesa-daraja": "mpesa_daraja",
    "safaricom": "mpesa_daraja",
}
PROVIDER_SLUG_TO_METHOD = {
    "mtn_momo": PaymentMethodCode.MTN_MOMO,
    "mtn": PaymentMethodCode.MTN_MOMO,
    "orange_momo": PaymentMethodCode.ORANGE_MOMO,
    "orange_money": PaymentMethodCode.ORANGE_MOMO,
    "orange": PaymentMethodCode.ORANGE_MOMO,
    "mpesa_daraja": PaymentMethodCode.MPESA,
    "mpesa": PaymentMethodCode.MPESA,
}
DEFAULT_SIGNATURE_FORMAT = "{invoice_id}:{amount}"
DEFAULT_SIGNATURE_HEADER = "X-Signature"


def _site_settings_for_school(school=None):
    # config-resolver-allow: namespace object returned to callers (wrapper helper)
    return get_effective_site_settings(school=school)


def _decimal_site_setting(site, field_name: str, default: str) -> Decimal:
    raw_value = getattr(site, field_name, default)
    if raw_value in (None, ""):
        raw_value = default
    try:
        return Decimal(str(raw_value))
    except (InvalidOperation, ValueError):
        logger.warning(
            "Invalid decimal site setting %s=%r; using default %s",
            field_name,
            raw_value,
            default,
        )
        return Decimal(default)


def normalize_provider_slug(slug: str | None) -> str:
    value = (slug or "").strip().lower()
    if not value:
        return ""
    return PROVIDER_SLUG_ALIASES.get(value, value)


def _signature_mapping(data: dict) -> dict:
    return {
        "invoice_id": data.get("invoice_id"),
        "amount": str(data.get("amount")),
        "method": data.get("method"),
        "reference": data.get("reference"),
    }


def _format_signature_payload(fmt: str, mapping: dict) -> str:
    class MissingDict(dict):
        def __missing__(self, key):
            return ""

    return fmt.format_map(MissingDict(mapping))


def _build_signature(secret: str, payload: str) -> str:
    return hmac.new(secret.encode(), payload.encode(), hashlib.sha256).hexdigest()


def get_payment_integration_by_method(method: str) -> Integration | None:
    slug = PAYMENT_METHOD_PROVIDER_SLUGS.get(method)
    if not slug:
        return None
    integration = (
        # tenant-isolation-allow: service-layer-scoped-via-caller-student-classroom-or-teacher-fk
        Integration.objects.filter(
            provider="payments",
            enabled=True,
            config__provider_slug=slug,
        )
        .order_by("-id")
        .first()
    )
    if integration and not is_integration_allowed(integration):
        return None
    return integration


def get_payment_integration_by_slug(slug: str) -> Integration | None:
    normalized = normalize_provider_slug(slug)
    candidates = {normalized}
    if slug:
        candidates.add((slug or "").strip().lower())
    if normalized == "orange_momo":
        candidates.add("orange_money")
    if normalized == "mtn_momo":
        candidates.add("mtn")

    # tenant-isolation-allow: service-layer-scoped-via-caller-student-classroom-or-teacher-fk
    integration = (
        Integration.objects.filter(provider="payments", enabled=True)
        .filter(Q(config__provider_slug__in=candidates) | Q(slug__in=candidates))
        .order_by("-id")
        .first()
    )
    if integration and not is_integration_allowed(integration):
        return None
    return integration


def _account(
    profile: ComplianceProfile, code: str, name: str, account_type: str
) -> LedgerAccount:
    account, _ = LedgerAccount.objects.get_or_create(
        profile=profile,
        code=code,
        defaults={
            "name": name,
            "account_type": account_type,
            "is_active": True,
        },
    )
    return account


def generate_payment_link(invoice: Invoice, method: str | None = None) -> dict | None:
    if not invoice:
        return None
    chosen = method or invoice.preferred_payment_method or PaymentMethodCode.MTN_MOMO
    integration = get_payment_integration_by_method(chosen)
    if not integration:
        return None

    config = integration.config or {}
    base_url = config.get("base_url")
    if not base_url:
        return None

    callback_path = config.get(
        "callback_path",
        f"/finance/payments/webhook/{config.get('provider_slug', PAYMENT_METHOD_PROVIDER_SLUGS.get(chosen))}/",
    )
    site_url = getattr(settings, "SITE_URL", "https://school.example/").rstrip("/")
    callback_url = config.get("callback_url") or f"{site_url}{callback_path}"

    amount_to_pay = max(invoice.balance_amount or Decimal("0.00"), Decimal("0.00"))
    payload_data = _signature_mapping(
        {
            "invoice_id": invoice.id,
            "amount": str(amount_to_pay),
            "method": chosen,
        }
    )
    signature_fmt = config.get("signature_format", DEFAULT_SIGNATURE_FORMAT)
    payload = _format_signature_payload(signature_fmt, payload_data)
    signature = _build_signature(config.get("secret", settings.SECRET_KEY), payload)

    return {
        "url": f"{base_url}?invoice={invoice.id}&method={chosen}&amount={amount_to_pay}&sig={signature}&callback={callback_url}",
        "method": chosen,
        "integration": integration,
        "signature_header": config.get("signature_header", DEFAULT_SIGNATURE_HEADER),
        "callback_url": callback_url,
    }


def verify_payment_signature(
    integration: Integration, data: dict, signature: str | None
) -> bool:
    if not signature:
        return False
    config = integration.config or {}
    fmt = config.get("signature_format", DEFAULT_SIGNATURE_FORMAT)
    payload = _format_signature_payload(fmt, _signature_mapping(data))
    expected = _build_signature(config.get("secret", settings.SECRET_KEY), payload)
    return hmac.compare_digest(expected, signature)


def record_provider_payment(
    invoice: Invoice,
    amount: Decimal | str | float,
    method: str,
    reference: str | None = None,
    external_reference: str | None = None,
) -> Payment | None:
    if not invoice:
        return None

    amount_val = Decimal(str(amount))
    if amount_val <= 0:
        return None

    ext_ref = external_reference or reference
    defaults = {
        "amount": amount_val,
        "method": method,
        "reference": reference or ext_ref or "",
    }
    if ext_ref:
        defaults["external_reference"] = ext_ref
        payment, _ = Payment.objects.update_or_create(
            invoice=invoice,
            external_reference=ext_ref,
            defaults=defaults,
        )
    else:
        payment = Payment.objects.create(invoice=invoice, **defaults)
    apply_payment(payment)
    # Feed the fractional clearance sub-ledger. A confirmed gateway / mobile-money
    # settlement (Paystack / Flutterwave / MTN MoMo / Stripe webhook) IS an
    # irregular partial payment against the invoice — exactly what
    # FractionalPaymentLedger models. Without this the sub-ledger stayed
    # permanently EMPTY for every gateway payer, so enrollment_clearance_for_invoice()
    # could never return True and reports.student_has_financial_clearance() +
    # academics.year_close blocked an M-Pesa instalment payer from their report
    # card AND re-enrollment forever. The cash path already posts source=CASH_COUNTER
    # (payment_orchestration.reconcile_offline_payment_intent); GATEWAY was one of
    # the two producerless holes. Idempotent on the Payment identity: a redelivered
    # webhook resolves to the same Payment row (update_or_create on
    # invoice+external_reference), so a second confirmation is a no-op and can
    # never double-credit clearance. Currency is resolved from the invoice by the
    # producer (never a blind USD). Invoice.school is nullable (platform/AP
    # invoices carry no tenant) but FractionalPaymentLedger.school is NOT NULL and
    # both clearance readers are school-scoped, so a school-less row is unwritable
    # AND unreadable — tenant enrollment-clearance simply does not apply there.
    if getattr(invoice, "school_id", None) is not None:
        from apps.finance.fractional_ledger_services import post_partial_payment
        from apps.finance.models_fractional_ledger import FractionalPaymentLedger

        post_partial_payment(
            school=invoice.school,
            invoice=invoice,
            amount=amount_val,
            source=FractionalPaymentLedger.Source.GATEWAY,
            idempotency_key=f"gateway-payment-{payment.pk}",
            student=getattr(invoice, "student", None),
            note=f"Gateway settlement (payment {payment.pk})"[:255],
        )
    return payment


@transaction.atomic
def pay_invoice_with_wallet(
    school: "School",
    user: "User",
    invoice: Invoice,
    amount: Decimal | str | float | None = None,
) -> tuple[Payment, ParentWallet]:
    """
    Pay (part of) an invoice using the parent's wallet. Debits wallet, creates Payment
    with method WALLET and WalletTransaction, applies payment and ledger.
    Returns (payment, wallet). Raises ValueError if insufficient balance or invalid input.
    """
    if getattr(invoice, "school_id", None) and invoice.school_id != school.pk:
        raise ValueError("Invoice does not belong to this school.")
    # Lock the invoice row for the duration of this atomic block. Two
    # DIFFERENT parents paying the SAME invoice concurrently each lock only
    # their own wallet row (below), so without an invoice-level lock the
    # balance is read twice and both pays are admitted — overpaying the
    # invoice. Re-reading the locked row also picks up any payment that
    # committed while we were blocked on the lock, so the balance check
    # below is against current truth. (No-op on SQLite test DB.)
    try:
        invoice = Invoice.objects.select_for_update().get(pk=invoice.pk)
    except Invoice.DoesNotExist:
        raise ValueError("Invoice no longer exists.")
    amount_val = (
        Decimal(str(amount)) if amount is not None else invoice.computed_balance
    )
    if amount_val <= 0:
        raise ValueError("Amount must be positive.")
    if amount_val > invoice.computed_balance:
        raise ValueError("Amount exceeds invoice balance.")

    wallet, _ = ParentWallet.objects.select_for_update().get_or_create(
        school=school,
        user=user,
        defaults={
            "currency_code": getattr(school, "currency_code", None)
            or get_platform_defaults(use_db=False)["currency"]
        },
    )
    if wallet.balance < amount_val:
        raise ValueError(
            f"Insufficient wallet balance: {wallet.balance} (need {amount_val})."
        )
    # uuid suffix guarantees uniqueness — second-granular timestamps collide
    # for concurrent same-invoice pays and would violate the (invoice,
    # external_reference) unique constraint with an IntegrityError.
    ref = f"WALLET-{invoice.id}-{timezone.now().strftime('%Y%m%d%H%M%S')}-{uuid.uuid4().hex[:8]}"
    payment = Payment.objects.create(
        invoice=invoice,
        school=getattr(invoice, "school", None) or school,
        amount=amount_val,
        method=PaymentMethodCode.WALLET,
        reference=ref,
        external_reference=ref,
    )
    # Quantize the running balance to the 2dp currency step so an >2dp
    # value from upstream arithmetic (FX-converted top-up, split remainder)
    # can't be persisted unrounded and drift the next balance comparison.
    new_balance = quantize_money(wallet.balance - amount_val)
    WalletTransaction.objects.create(
        wallet=wallet,
        amount=-amount_val,
        kind=WalletTransaction.Kind.PAYMENT,
        balance_after=new_balance,
        payment=payment,
        reference=ref,
    )
    wallet.balance = new_balance
    wallet.save(update_fields=["balance", "updated_at"])
    apply_payment(payment)
    # Feed the fractional clearance sub-ledger (same rationale as the gateway and
    # cash paths): a wallet debit against the invoice is an irregular partial
    # payment. WALLET was the second producerless hole — without this a parent who
    # pays school fees from the cashless wallet in instalments never cleared
    # enrollment_clearance_for_invoice() and stayed blocked from report cards +
    # year-close re-enrollment. Keyed on the Payment identity; each wallet pay
    # mints a distinct Payment (unique ref), so distinct instalments post distinct
    # rows and a retried call is a no-op. Currency is resolved from the invoice by
    # the producer. Runs inside this function's @transaction.atomic envelope, so
    # the wallet debit, the Payment and its clearance line commit together — a
    # swallowed ledger write would be a silent money-integrity bug. school comes
    # from the invoice (nullable) with the caller's tenant as fallback; both
    # clearance readers are school-scoped so the row is only written when known.
    ledger_school = getattr(invoice, "school", None) or school
    if ledger_school is not None:
        from apps.finance.fractional_ledger_services import post_partial_payment
        from apps.finance.models_fractional_ledger import FractionalPaymentLedger

        post_partial_payment(
            school=ledger_school,
            invoice=invoice,
            amount=amount_val,
            source=FractionalPaymentLedger.Source.WALLET,
            idempotency_key=f"wallet-payment-{payment.pk}",
            student=getattr(invoice, "student", None),
            note=f"Wallet settlement (payment {payment.pk})"[:255],
        )
    return payment, wallet


@transaction.atomic
def top_up_wallet(
    school: "School",
    user: "User",
    amount: Decimal | str | float,
    reference: str | None = None,
) -> tuple[ParentWallet, WalletTransaction]:
    """
    Credit the parent's wallet (top-up). Creates wallet if needed, records WalletTransaction TOP_UP.
    Returns (wallet, transaction). Raises ValueError if amount <= 0.
    """
    amount_val = Decimal(str(amount))
    if amount_val <= 0:
        raise ValueError("Top-up amount must be positive.")
    # Row-lock the wallet for the duration of this atomic block so two
    # concurrent top-ups for the same (school, user) cannot read the same
    # balance and lose one credit (mirrors pay_invoice_with_wallet).
    wallet, _ = ParentWallet.objects.select_for_update().get_or_create(
        school=school,
        user=user,
        defaults={
            "currency_code": getattr(school, "currency_code", None)
            or get_platform_defaults(use_db=False)["currency"]
        },
    )
    new_balance = quantize_money(wallet.balance + amount_val)
    ref = reference or f"TOPUP-{timezone.now().strftime('%Y%m%d%H%M%S')}-{uuid.uuid4().hex[:8]}"
    txn = WalletTransaction.objects.create(
        wallet=wallet,
        amount=amount_val,
        kind=WalletTransaction.Kind.TOP_UP,
        balance_after=new_balance,
        reference=ref,
    )
    wallet.balance = new_balance
    wallet.save(update_fields=["balance", "updated_at"])
    return wallet, txn


@transaction.atomic
def post_invoice_to_ledger(invoice: Invoice) -> None:
    # Atomic so the JournalEntry + its debit/credit JournalLines are
    # all-or-nothing; a partial failure must never leave an unbalanced entry
    # (double-entry invariant). Safe under nested calls — Django uses savepoints.
    if invoice.status in {Invoice.Status.DRAFT, Invoice.Status.VOID}:
        return
    if invoice.total_amount <= 0:
        return
    entry = JournalEntry.objects.filter(
        source_type="invoice", source_id=invoice.id
    ).first()

    profile = invoice.profile
    if invoice.invoice_type == Invoice.InvoiceType.AP:
        debit_account = _account(
            profile, "611", "Purchases and Services", LedgerAccount.AccountType.EXPENSE
        )
        credit_account = _account(
            profile, "401", "Trade Payables", LedgerAccount.AccountType.LIABILITY
        )
    else:
        debit_account = _account(
            profile, "411", "Student Receivables", LedgerAccount.AccountType.ASSET
        )
        credit_account = _account(
            profile, "706", "Tuition Revenue", LedgerAccount.AccountType.INCOME
        )

    if entry:
        entry.entry_date = invoice.issued_date
        entry.reference = invoice.reference or f"INV-{invoice.id}"
        entry.memo = invoice.notes or ""
        entry.posted_at = entry.posted_at or timezone.now()
        entry.save(update_fields=["entry_date", "reference", "memo", "posted_at"])
        entry.lines.all().delete()
    else:
        entry = JournalEntry.objects.create(
            profile=profile,
            entry_date=invoice.issued_date,
            reference=invoice.reference or f"INV-{invoice.id}",
            memo=invoice.notes or "",
            source_type="invoice",
            source_id=invoice.id,
            posted_at=timezone.now(),
        )
    JournalLine.objects.create(
        entry=entry,
        account=debit_account,
        description=invoice.reference or "Invoice",
        debit=invoice.total_amount,
        credit=Decimal("0.00"),
    )
    JournalLine.objects.create(
        entry=entry,
        account=credit_account,
        description=invoice.reference or "Invoice",
        debit=Decimal("0.00"),
        credit=invoice.total_amount,
    )


@transaction.atomic
def post_payment_to_ledger(payment: Payment) -> None:
    # Atomic so the JournalEntry + its debit/credit JournalLines are
    # all-or-nothing (double-entry invariant); never leave an entry with only
    # one side on a partial failure. Safe under nesting (savepoints).
    if payment.amount <= 0:
        return
    entry = JournalEntry.objects.filter(
        source_type="payment", source_id=payment.id
    ).first()

    invoice = payment.invoice
    profile = invoice.profile

    cash_account = _account(profile, "531", "Cash", LedgerAccount.AccountType.ASSET)
    bank_account = _account(profile, "512", "Bank", LedgerAccount.AccountType.ASSET)
    mobile_account = _account(
        profile, "514", "Mobile Money", LedgerAccount.AccountType.ASSET
    )

    if payment.method in {PaymentMethodCode.CASH}:
        debit_account = cash_account
    elif payment.method in {PaymentMethodCode.MTN_MOMO, PaymentMethodCode.ORANGE_MOMO}:
        debit_account = mobile_account
    elif payment.method == PaymentMethodCode.WALLET:
        debit_account = _account(
            profile, "515", "Parent Wallet", LedgerAccount.AccountType.ASSET
        )
    else:
        debit_account = bank_account

    if invoice.invoice_type == Invoice.InvoiceType.AP:
        credit_account = debit_account
        debit_account = _account(
            profile, "401", "Trade Payables", LedgerAccount.AccountType.LIABILITY
        )
    else:
        credit_account = _account(
            profile, "411", "Student Receivables", LedgerAccount.AccountType.ASSET
        )

    if entry:
        entry.entry_date = payment.paid_at.date()
        entry.reference = payment.receipt_number or f"PAY-{payment.id}"
        entry.memo = payment.reference or ""
        entry.posted_at = entry.posted_at or timezone.now()
        entry.save(update_fields=["entry_date", "reference", "memo", "posted_at"])
        entry.lines.all().delete()
    else:
        entry = JournalEntry.objects.create(
            profile=profile,
            entry_date=payment.paid_at.date(),
            reference=payment.receipt_number or f"PAY-{payment.id}",
            memo=payment.reference or "",
            source_type="payment",
            source_id=payment.id,
            posted_at=timezone.now(),
        )
    JournalLine.objects.create(
        entry=entry,
        account=debit_account,
        description=invoice.reference or "Payment",
        debit=payment.amount,
        credit=Decimal("0.00"),
    )
    JournalLine.objects.create(
        entry=entry,
        account=credit_account,
        description=invoice.reference or "Payment",
        debit=Decimal("0.00"),
        credit=payment.amount,
    )


def post_scholarship_disbursement_to_ledger(
    *,
    application,
    amount: Decimal,
    invoice: Invoice | None = None,
    payment: Payment | None = None,
) -> JournalEntry | None:
    """
    Post scholarship disbursement as balanced journal entry.

    Debit: Scholarship Aid Expense (658)
    Credit: Student Receivables (411) when applied as invoice credit;
            otherwise a cash/bank/mobile-money asset account.
    """
    amount = Decimal(str(amount or "0"))
    if amount <= 0:
        return None

    profile = None
    if invoice and invoice.profile_id:
        profile = invoice.profile
    elif payment and payment.invoice_id:
        profile = payment.invoice.profile
    else:
        school = getattr(
            getattr(application, "school", None), "school", None
        ) or getattr(application, "school", None)
        site = _site_settings_for_school(school)
        profile = (
            getattr(site, "compliance_profile", None)
            or ComplianceProfile.objects.filter(is_active=True).first()
        )
    if not profile:
        return None

    entry = JournalEntry.objects.filter(
        source_type="financial_aid_disbursement",
        source_id=application.id,
    ).first()

    expense_account = _account(
        profile, "658", "Scholarship Aid Expense", LedgerAccount.AccountType.EXPENSE
    )
    if invoice:
        credit_account = _account(
            profile, "411", "Student Receivables", LedgerAccount.AccountType.ASSET
        )
    else:
        cash_account = _account(profile, "531", "Cash", LedgerAccount.AccountType.ASSET)
        bank_account = _account(profile, "512", "Bank", LedgerAccount.AccountType.ASSET)
        mobile_account = _account(
            profile, "514", "Mobile Money", LedgerAccount.AccountType.ASSET
        )
        method = (getattr(payment, "method", "") or "").strip()
        if method in {PaymentMethodCode.MTN_MOMO, PaymentMethodCode.ORANGE_MOMO}:
            credit_account = mobile_account
        elif method == PaymentMethodCode.CASH:
            credit_account = cash_account
        else:
            credit_account = bank_account

    reference = f"AID-{application.id}"
    memo = f"Scholarship disbursement: {application.scholarship.title}"
    entry_date = timezone.now().date()
    if entry:
        entry.entry_date = entry_date
        entry.reference = reference
        entry.memo = memo
        entry.posted_at = entry.posted_at or timezone.now()
        entry.save(update_fields=["entry_date", "reference", "memo", "posted_at"])
        entry.lines.all().delete()
    else:
        entry = JournalEntry.objects.create(
            profile=profile,
            entry_date=entry_date,
            reference=reference,
            memo=memo,
            source_type="financial_aid_disbursement",
            source_id=application.id,
            posted_at=timezone.now(),
        )

    line_desc = f"Application {application.id}"
    JournalLine.objects.create(
        entry=entry,
        account=expense_account,
        description=line_desc,
        debit=amount,
        credit=Decimal("0.00"),
    )
    JournalLine.objects.create(
        entry=entry,
        account=credit_account,
        description=line_desc,
        debit=Decimal("0.00"),
        credit=amount,
    )
    return entry


def post_donation_to_ledger(
    *,
    school,
    amount: Decimal,
    reference_id,
    memo: str = "Donation",
    method: str = "",
    profile=None,
) -> JournalEntry | None:
    """
    Post an incoming donation as a balanced journal entry — the INFLOW mirror of
    ``post_scholarship_disbursement_to_ledger`` (which posts the outflow). Without
    this, fund credits were visible in AidAuditLog but absent from the GL while
    disbursements posted, breaking double-entry symmetry.

    Debit: Cash (531) / Bank (512) / Mobile Money (514) asset, by method.
    Credit: Donations & Grants Income (754).
    Returns None (no-op) when no compliance profile is configured.
    """
    amount = Decimal(str(amount or "0"))
    if amount <= 0:
        return None

    if profile is None:
        site = _site_settings_for_school(school)
        profile = (
            getattr(site, "compliance_profile", None)
            or ComplianceProfile.objects.filter(is_active=True).first()
        )
    if not profile:
        return None

    income_account = _account(
        profile, "754", "Donations & Grants Income", LedgerAccount.AccountType.INCOME
    )
    cash_account = _account(profile, "531", "Cash", LedgerAccount.AccountType.ASSET)
    bank_account = _account(profile, "512", "Bank", LedgerAccount.AccountType.ASSET)
    mobile_account = _account(
        profile, "514", "Mobile Money", LedgerAccount.AccountType.ASSET
    )
    method = (method or "").strip()
    if method in {PaymentMethodCode.MTN_MOMO, PaymentMethodCode.ORANGE_MOMO}:
        debit_account = mobile_account
    elif method == PaymentMethodCode.CASH:
        debit_account = cash_account
    else:
        debit_account = bank_account

    reference = f"DON-{reference_id}"
    entry = JournalEntry.objects.filter(
        source_type="advancement_donation",
        source_id=reference_id,
    ).first()
    entry_date = timezone.now().date()
    if entry:
        entry.entry_date = entry_date
        entry.reference = reference
        entry.memo = memo[:255]
        entry.posted_at = entry.posted_at or timezone.now()
        entry.save(update_fields=["entry_date", "reference", "memo", "posted_at"])
        entry.lines.all().delete()
    else:
        entry = JournalEntry.objects.create(
            profile=profile,
            entry_date=entry_date,
            reference=reference,
            memo=memo[:255],
            source_type="advancement_donation",
            source_id=reference_id,
            posted_at=timezone.now(),
        )

    line_desc = memo[:255]
    JournalLine.objects.create(
        entry=entry,
        account=debit_account,
        description=line_desc,
        debit=amount,
        credit=Decimal("0.00"),
    )
    JournalLine.objects.create(
        entry=entry,
        account=income_account,
        description=line_desc,
        debit=Decimal("0.00"),
        credit=amount,
    )
    return entry


def _invoice_status(total: Decimal, balance: Decimal) -> str:
    if total <= 0:
        return Invoice.Status.DRAFT
    if balance <= 0:
        return Invoice.Status.PAID
    if balance < total:
        return Invoice.Status.PARTIAL
    return Invoice.Status.ISSUED


@transaction.atomic
def recalculate_invoice(invoice: Invoice) -> None:
    # Atomic so the invoice total/balance/status write + reconcile + ledger
    # re-post commit together. Load-bearing on the Payment.delete() path, which
    # calls this without an outer transaction of its own.
    if not invoice:
        return
    # Query by invoice_id so totals match the DB. `invoice.lines.all()` can return a stale
    # reverse-cache if lines were just created against the same in-memory invoice instance.
    subtotal = Decimal("0.00")
    for line in InvoiceLine.objects.filter(invoice_id=invoice.pk):
        subtotal += line.amount

    total = subtotal
    profile = getattr(invoice, "profile", None)
    if profile is not None:
        vat_percent = getattr(profile, "vat_rate", None) or Decimal("0")
        if vat_percent > 0:
            from apps.finance.tax_engine import compute_tax, resolve_vat_rate_fraction

            region_code = str(getattr(profile, "country_code", None) or "US")[:2]
            rate = resolve_vat_rate_fraction(
                region_code=region_code,
                vat_percent=vat_percent,
            )
            tax_amount = compute_tax(subtotal, region_code, rate_override=rate)
            total = subtotal + tax_amount

    paid = Decimal("0.00")
    # Exclude soft-deleted payments AND not-received statuses (failed/cancelled/
    # refunded) so a reversed/failed payment stops counting toward paid — mirrors
    # Invoice.computed_balance. A partially-refunded payment stays 'completed' but
    # only its net (amount - refunded_amount) counts, so partial refunds reduce
    # paid too (also mirrors computed_balance).
    from apps.finance.models import _NON_RECEIVED_PAYMENT_STATUSES

    # tenant-isolation-allow: service-scoped-via-request-school-context
    for payment in Payment.objects.filter(
        invoice_id=invoice.pk, deleted_at__isnull=True
    ).exclude(status__in=_NON_RECEIVED_PAYMENT_STATUSES):
        paid += max(
            payment.amount - (payment.refunded_amount or Decimal("0.00")),
            Decimal("0.00"),
        )

    balance = max(total - paid, Decimal("0.00"))
    invoice.total_amount = total
    invoice.balance_amount = balance
    invoice.status = _invoice_status(total, balance)
    try:
        invoice._recalculating = True
        invoice.save(
            update_fields=["total_amount", "balance_amount", "status", "updated_at"]
        )
    finally:
        invoice._recalculating = False
    invoice.reconcile_balance()
    post_invoice_to_ledger(invoice)


class RefundProcessingError(Exception):
    """Raised when a RefundRequest cannot be applied to the ledger."""


def process_refund_request(refund_request, *, processed_by=None):
    """Apply a ``RefundRequest`` to the ledger and recompute the invoice balance.

    This is the missing PRODUCER for a refund: it increments the underlying
    payment's ``refunded_amount``, flips the payment to ``status="refunded"``
    once it is fully refunded, marks the request ``processed`` (stamping
    ``processed_at``), and recomputes the invoice so collected revenue stops
    counting the returned money. Without it a ``RefundRequest`` (created e.g.
    for an overpayment) sat ``pending`` forever and the invoice balance never
    reflected the refund.

    Idempotent: a request already ``processed`` is a no-op (so double-clicking
    the admin action or a retried task never double-refunds). Raises
    ``RefundProcessingError`` for an un-processable request (rejected, amount
    <= 0, deleted/reversed payment, or a refund that would exceed the payment's
    refundable balance).

    The status/``refunded_amount`` transition is a deliberately scoped
    ``.update()`` (NOT ``payment.save()``) so the Payment ``post_save`` signal
    does not re-fire ``apply_payment`` — which would re-send a "payment
    received" notification and re-run payer-share allocation on what is
    actually a refund. The balance is instead recomputed here explicitly via
    ``recalculate_invoice``. (Payment.save()'s immutability guard explicitly
    directs refunds to a separate entry like this one.)
    """
    from apps.finance.models import Payment

    if refund_request.status == "processed":
        return refund_request  # idempotent: already applied
    if refund_request.status == "rejected":
        raise RefundProcessingError("Cannot process a rejected refund request.")

    amount = refund_request.amount or Decimal("0.00")
    if amount <= Decimal("0.00"):
        raise RefundProcessingError("Refund amount must be positive.")

    with transaction.atomic():
        payment = Payment.objects.select_for_update().get(pk=refund_request.payment_id)
        if payment.deleted_at is not None:
            raise RefundProcessingError(
                "Cannot refund a reversed (soft-deleted) payment."
            )
        already_refunded = payment.refunded_amount or Decimal("0.00")
        refundable = payment.amount - already_refunded
        if amount > refundable:
            raise RefundProcessingError(
                f"Refund {amount} exceeds the refundable balance {refundable} "
                f"on payment {payment.pk}."
            )
        new_refunded = already_refunded + amount
        new_status = "refunded" if new_refunded >= payment.amount else payment.status

        # Scoped status/refund transition — see the docstring for why this is a
        # queryset .update() and not payment.save(). (Payment has no updated_at
        # column; created_at is auto_now_add, so nothing else to stamp here.)
        # tenant-isolation-allow: pk-scoped-refund-transition-on-invoice-owned-payment
        Payment.objects.filter(pk=payment.pk).update(
            refunded_amount=new_refunded,
            status=new_status,
        )

        refund_request.status = "processed"
        refund_request.processed_at = timezone.now()
        if processed_by is not None and refund_request.approved_by_id is None:
            refund_request.approved_by = processed_by
        refund_request.save(
            update_fields=["status", "processed_at", "approved_by", "updated_at"]
        )

        if payment.invoice_id:
            payment.refresh_from_db(fields=["refunded_amount", "status"])
            recalculate_invoice(payment.invoice)

    return refund_request


@transaction.atomic
def apply_payment(payment: Payment) -> None:
    # Envelope transaction: recalc + payer-share allocation + ledger post must
    # commit together or roll back together, so a mid-execution failure cannot
    # leave a half-applied payment (stale invoice balance / unbalanced ledger).
    # Called from the post_save signal and webhook path which have no outer
    # atomic block of their own, so this decorator is load-bearing.
    if not payment or not payment.invoice:
        return
    recalculate_invoice(payment.invoice)
    allocate_payment_to_payer_shares(payment)
    post_payment_to_ledger(payment)
    try:
        from apps.siteconfig.workflow_triggers import dispatch_payment_received_from_payment

        dispatch_payment_received_from_payment(payment)
    except ImportError:
        pass
    try:
        inv = payment.invoice
        sch = getattr(inv, "school", None) or getattr(payment, "school", None)
        if sch is not None and getattr(payment, "status", "") in ("completed", "success", "paid"):
            from apps.finance.payment_notification_intent import dispatch_payment_received_intent

            dispatch_payment_received_intent(school=sch, payment=payment)
    except (DatabaseError, ImportError, AttributeError, TypeError, ValueError):
        logging.getLogger(__name__).warning(
            "payment_received notification intent failed", exc_info=True
        )
    try:
        inv = payment.invoice
        sch = getattr(inv, "school", None) or getattr(payment, "school", None)
        if sch is not None:
            from apps.schools.funnel_events import (
                record_payment_outcome_signal,
                try_record_first_result_payment,
            )

            try_record_first_result_payment(sch, payment)
            record_payment_outcome_signal(
                sch,
                success=True,
                metadata={
                    "source": "finance_payment",
                    "payment_id": getattr(payment, "pk", None),
                },
            )
    except (ImportError, AttributeError, TypeError, ValueError):
        pass


def split_amount_equally(total_amount: Decimal, count: int) -> list[Decimal]:
    """
    Deterministic split with cent-level remainder distribution.
    Example: 100.00 / 3 -> [33.34, 33.33, 33.33]
    """
    if count <= 0:
        return []
    quant = Decimal("0.01")
    total = Decimal(str(total_amount)).quantize(quant)
    base = (total / Decimal(count)).quantize(quant, rounding=ROUND_DOWN)
    parts = [base for _ in range(count)]
    distributed = base * count
    remainder_steps = int(((total - distributed) / quant).to_integral_value())
    for idx in range(remainder_steps):
        parts[idx] = (parts[idx] + quant).quantize(quant)
    return parts


@transaction.atomic
def assign_invoice_payer_shares(
    invoice: Invoice,
    payer_allocations: list[tuple[StudentGuardian, Decimal]],
    *,
    due_date=None,
) -> list[InvoicePayerShare]:
    """
    Set payer-share splits for an invoice. Replaces existing active shares.
    """
    if not invoice or not invoice.id:
        return []
    if not payer_allocations:
        InvoicePayerShare.objects.filter(invoice=invoice).delete()
        return []

    quant = Decimal("0.01")
    grouped: dict[int, Decimal] = defaultdict(lambda: Decimal("0.00"))
    guardian_by_id: dict[int, StudentGuardian] = {}
    for guardian, amount in payer_allocations:
        if guardian is None:
            continue
        amt = Decimal(str(amount or "0")).quantize(quant)
        if amt <= Decimal("0.00"):
            continue
        if invoice.student_id and guardian.student_id != invoice.student_id:
            raise ValueError("Guardian allocation does not match invoice student.")
        grouped[guardian.id] += amt
        guardian_by_id[guardian.id] = guardian

    if not grouped:
        InvoicePayerShare.objects.filter(invoice=invoice).delete()
        return []

    expected_total = Decimal(str(invoice.total_amount or "0")).quantize(quant)
    split_total = sum(grouped.values(), Decimal("0.00")).quantize(quant)
    if split_total != expected_total:
        raise ValueError(
            f"Payer split total ({split_total}) must match invoice total ({expected_total})."
        )

    InvoicePayerShare.objects.filter(invoice=invoice).delete()
    rows = []
    for guardian_id, amount in grouped.items():
        rows.append(
            InvoicePayerShare(
                invoice=invoice,
                guardian=guardian_by_id[guardian_id],
                allocated_amount=amount,
                due_date=due_date or invoice.due_date,
                status=InvoicePayerShare.Status.OPEN,
            )
        )
    created = InvoicePayerShare.objects.bulk_create(rows)
    return list(created)


@transaction.atomic
def assign_equal_invoice_payer_shares(invoice: Invoice) -> list[InvoicePayerShare]:
    """
    Equal split across finance-enabled guardians for the invoice student.
    With a single finance-enabled guardian, the full invoice total is allocated to that payer.
    """
    if not invoice or not invoice.student_id:
        return []
    guardians = list(
        StudentGuardian.objects.filter(
            student_id=invoice.student_id,
            can_view_finance=True,
            guardian_user__is_active=True,
        ).select_related("guardian_user")
    )
    if not guardians:
        return []
    parts = split_amount_equally(
        Decimal(str(invoice.total_amount or "0.00")), len(guardians)
    )
    allocations = list(zip(guardians, parts))
    return assign_invoice_payer_shares(invoice, allocations, due_date=invoice.due_date)


@transaction.atomic
def allocate_payment_to_payer_shares(payment: Payment) -> None:
    """
    Apply a payment to payer-share obligations once (idempotent via allocation rows).
    Preference: payer's own share first, then oldest due.
    """
    if not payment or not payment.invoice_id:
        return
    # Row-lock the shares for the duration of this atomic block so two payments
    # against the same invoice can't both read a stale paid_amount and clobber
    # each other's allocation (lost update on share.paid_amount).
    shares = list(
        InvoicePayerShare.objects.select_for_update()
        .filter(
            invoice_id=payment.invoice_id,
            is_active=True,
        )
        .select_related("guardian", "guardian__guardian_user")
    )
    if not shares:
        return

    already_allocated = InvoicePayerSharePaymentAllocation.objects.filter(
        payment=payment
    ).aggregate(total=Sum("amount")).get("total") or Decimal("0.00")
    remaining = Decimal(str(payment.amount or "0.00")) - Decimal(str(already_allocated))
    if remaining <= Decimal("0.00"):
        for share in shares:
            share.refresh_status()
        return

    preferred_guardian_user_id = getattr(
        getattr(payment, "created_by", None), "id", None
    )
    ordered = sorted(
        shares,
        key=lambda share: (
            0
            if preferred_guardian_user_id
            and share.guardian.guardian_user_id == preferred_guardian_user_id
            else 1,
            share.due_date or date.max,
            share.id,
        ),
    )

    for share in ordered:
        if remaining <= Decimal("0.00"):
            break
        outstanding = share.outstanding_amount
        if outstanding <= Decimal("0.00"):
            continue
        applied = min(remaining, outstanding)
        if applied <= Decimal("0.00"):
            continue

        InvoicePayerSharePaymentAllocation.objects.create(
            payer_share=share,
            payment=payment,
            amount=applied,
        )
        share.paid_amount = (share.paid_amount or Decimal("0.00")) + applied
        share.refresh_status(save=False)
        share.save(update_fields=["paid_amount", "status", "updated_at"])
        remaining -= applied


def carry_forward_arrears(source_year, target_year) -> int:
    """
    For each student with unpaid invoice balance in source_year, create an Opening Balance
    (arrears) invoice in target_year. Idempotent: uses reference ARREARS-{target_year.name}-{student_code}
    so re-running does not duplicate. Returns the number of arrears invoices created.
    """
    from apps.academics.models import AcademicYear

    # tenant-isolation-allow: service-scoped-via-request-school-context
    if not isinstance(source_year, AcademicYear):
        source_year = AcademicYear.objects.get(id=source_year)
    if not isinstance(target_year, AcademicYear):
        # tenant-isolation-allow: service-layer-scoped-via-caller-student-classroom-or-teacher-fk
        target_year = AcademicYear.objects.get(id=target_year)

    profile = ComplianceProfile.objects.filter(is_active=True).first()
    if not profile:
        return 0
# tenant-isolation-allow: service-layer-scoped-via-caller-student-classroom-or-teacher-fk

    invoices_source = (
        # tenant-isolation-allow: service-layer-scoped-via-caller-student-classroom-or-teacher-fk
        Invoice.objects.filter(
            academic_year=source_year,
            student__isnull=False,
            invoice_type=Invoice.InvoiceType.AR,
        )
        .exclude(status=Invoice.Status.VOID)
        .select_related("student")
    )

    # Group by student: sum computed_balance (property, so we iterate)
    arrears_by_student: dict[int, Decimal] = {}
    for inv in invoices_source:
        bal = inv.computed_balance
        if bal > Decimal("0.00"):
            sid = inv.student_id
            arrears_by_student[sid] = arrears_by_student.get(sid, Decimal("0.00")) + bal

    created = 0
    issued = timezone.now().date()
    with transaction.atomic():
        # tenant-isolation-allow: service-layer-scoped-via-caller-student-classroom-or-teacher-fk
        for student_id, total_arrears in arrears_by_student.items():
            if total_arrears <= Decimal("0.00"):
                # tenant-isolation-allow: service-layer-scoped-via-caller-student-classroom-or-teacher-fk
                continue
            student = StudentProfile.objects.filter(id=student_id).first()
            if not student:
                continue
            ref = f"ARREARS-{target_year.name}-{student.student_code}"
            inv, created_inv = Invoice.objects.get_or_create(
                profile=profile,
                academic_year=target_year,
                student_id=student_id,
                reference=ref,
                invoice_type=Invoice.InvoiceType.AR,
                defaults={
                    "issued_date": issued,
                    "due_date": issued,
                    "status": Invoice.Status.ISSUED,
                    "total_amount": total_arrears,
                },
            )
            if not created_inv:
                continue
            InvoiceLine.objects.create(
                invoice=inv,
                description=f"Opening balance / Arrears from {source_year.name}",
                quantity=Decimal("1.00"),
                unit_price=total_arrears,
                amount=total_arrears,
            )
            recalculate_invoice(inv)
            created += 1
    return created


def _get_region_for_refund(invoice: Invoice):
    """Get RegionConfig for refund/overpayment (use first region)."""
    return RegionConfig.objects.first()


@transaction.atomic
def create_payment_from_receipt(
    proof_upload: PaymentProofUpload, verification_data: dict, verified_by=None
) -> Payment:
    """
    Create and apply payment from verified receipt upload.
    Caps amount at invoice balance; overpayment within tolerance creates RefundRequest.
    """
    # Idempotency / double-credit guard (2026-06-17 seal): if this receipt already
    # produced a payment, return it instead of creating a second one. ``proof_upload.payment``
    # is set together with ``status=VERIFIED`` at the end of a successful application, so a
    # retry / re-run (e.g. a no-reference receipt re-processed) must not re-credit the invoice.
    if proof_upload.payment_id:
        return proof_upload.payment

    invoice = proof_upload.invoice
    balance = invoice.balance_amount or invoice.total_amount or Decimal("0")
    if not isinstance(balance, Decimal):
        balance = Decimal(str(balance))

    amount = verification_data.get("amount") or proof_upload.uploaded_amount
    if amount is not None and not isinstance(amount, Decimal):
        amount = Decimal(str(amount))
    if not amount:
        raise ValueError("Cannot create payment: amount not found in receipt")

    site = _site_settings_for_school(
        getattr(invoice, "school", None)
        or getattr(getattr(invoice, "student", None), "school", None)
    )
    overpayment_handling = getattr(
        site, "finance_overpayment_handling", "allow_with_refund"
    )
    tolerance = _decimal_site_setting(
        site, "finance_overpayment_tolerance_xaf", "1000"
    )
    _currency = (
        getattr(getattr(invoice, "school", None), "currency_code", None)
        or get_platform_defaults(use_db=False)["currency"]
    )

    amount_to_apply = min(amount, balance)
    overpayment = amount - balance if amount > balance else Decimal("0")

    if overpayment > tolerance and balance > 0:
        raise ValueError(
            f"Receipt amount {amount} exceeds balance {balance} by more than allowed tolerance ({tolerance} {_currency}). "
            "Please review manually."
        )

    payment = Payment.objects.create(
        invoice=invoice,
        student=invoice.student,
        amount=amount_to_apply,
        method=proof_upload.payment_method,
        receipt_file=proof_upload.receipt_file,
        reference=verification_data.get("reference")
        or proof_upload.transaction_reference
        or "",
        external_reference=verification_data.get("reference")
        or proof_upload.transaction_reference
        or "",
        status="completed",  # canonical Payment status value (cf. Payment.mark_completed)
        created_by=proof_upload.uploaded_by,
        processed_by=verified_by,
        paid_at=timezone.now(),
    )

    apply_payment(payment)

    if overpayment > 0 and overpayment_handling in (
        "allow_with_refund",
        "allow_as_credit",
    ):
        region = _get_region_for_refund(invoice)
        if region:
            RefundRequest.objects.create(
                payment=payment,
                region=region,
                amount=overpayment,
                reason="overpayment",
                description=f"Overpayment from receipt upload (proof #{proof_upload.id}). Amount received: {amount}, applied: {amount_to_apply}.",
                status="pending",
                requested_by=verified_by or proof_upload.uploaded_by,
            )
        if not proof_upload.verification_notes:
            proof_upload.verification_notes = ""
        proof_upload.verification_notes += (
            f" Overpayment {overpayment} {_currency} → refund request created. "
        )

    proof_upload.payment = payment
    proof_upload.status = PaymentProofUpload.Status.VERIFIED
    proof_upload.verified_by = verified_by
    proof_upload.verified_at = timezone.now()
    proof_upload.save()

    try:
        from apps.events.services import emit_event

        school_id = getattr(invoice, "school_id", None) or getattr(
            getattr(invoice, "student", None), "school_id", None
        )
        emit_event(
            "payment.received",
            {
                "payment_id": str(payment.id),
                "invoice_id": str(invoice.id),
                "student_id": str(invoice.student_id) if invoice.student_id else None,
                "school_id": str(school_id) if school_id else None,
                "amount": str(amount_to_apply),
                "method": getattr(proof_upload, "payment_method", "") or "",
                "reference": payment.reference or "",
            },
            school_id=school_id,
        )
    except (ImportError, AttributeError, TypeError, ValueError, KeyError) as e:
        logging.getLogger(__name__).debug("payment.received emit_event skip: %s", e)
    return payment


# tenant-isolation-allow: service-layer-scoped-via-caller-student-classroom-or-teacher-fk
def _student_for_plan(plan: FeePlan) -> Iterable[StudentProfile]:
    return StudentProfile.objects.filter(
        academic_year=plan.academic_year,
        classroom=plan.classroom,
        specialty=plan.specialty,
        is_active=True,
    ).order_by("last_name", "first_name")


def _bulk_create_invoice_notify_guardians_skip():
    """Context manager to skip per-invoice notifications during bulk create (Phase 4.1: use Notify guardians instead)."""
    from apps.finance.notifications import _skip_new_invoice_notify

    token = _skip_new_invoice_notify.set(True)
    try:
        yield
    finally:
        _skip_new_invoice_notify.reset(token)


def _apply_fee_discount_nuance(invoice: Invoice, student: StudentProfile) -> None:
    """Section 7: If school has an active fee_discount nuance, apply result as a discount line (capped at total)."""
    try:
        from apps.siteconfig.nuance_engine import apply_nuance
    except ImportError:
        return
    total = invoice.lines.aggregate(s=Sum("amount"))["s"] or Decimal("0")
    if total <= 0:
        return
    context = {
        "fee": float(total),  # money-float-allow: scalar-coerce-input (nuance-engine context)
        "student_id": student.pk,
    }
    # Optional: add gpa, sibling_count if available on student
    if hasattr(student, "gpa") and student.gpa is not None:
        context["gpa"] = float(student.gpa)
    if hasattr(student, "sibling_count") and student.sibling_count is not None:
        context["sibling_count"] = int(student.sibling_count)
    # Information tags for AI Nuance: e.g. {"in": ["Early Bird", {"var": "student_tags"}]} → 10% off
    if hasattr(student, "tags"):
        context["student_tags"] = list(
            student.tags.filter(is_active=True).values_list("name", flat=True)
        )
    else:
        context["student_tags"] = []
    result = apply_nuance(invoice.school, "fee_discount", context)
    if result is None:
        return
    try:
        val = float(result)
    except (TypeError, ValueError):
        return
    if val <= 0:
        return
    if val <= 1:
        discount = total * Decimal(str(val))
    else:
        discount = min(Decimal(str(val)), total)
    if discount <= 0:
        return
    InvoiceLine.objects.create(
        invoice=invoice,
        description="Custom discount (nuance)",
        quantity=Decimal("1.00"),
        unit_price=-discount,
        amount=-discount,
        fee_item=None,
    )


@transaction.atomic
def create_fee_invoices(
    *,
    plan: FeePlan,
    profile: ComplianceProfile,
    issued_date=None,
    due_date=None,
) -> list[Invoice]:
    issued_date = issued_date or timezone.now().date()
    fee_items = list(plan.items.all())
    invoices: list[Invoice] = []
    skip_ctx = _bulk_create_invoice_notify_guardians_skip()
    next(skip_ctx)  # enter

    try:
        for student in _student_for_plan(plan):
            invoice, created = Invoice.objects.get_or_create(
                profile=profile,
                academic_year=plan.academic_year,
                student=student,
                invoice_type=Invoice.InvoiceType.AR,
                reference=f"FEE-{plan.academic_year.name}-{student.student_code}",
                defaults={
                    "issued_date": issued_date,
                    "due_date": due_date,
                    "status": Invoice.Status.ISSUED,
                    "total_amount": Decimal("0.01"),
                    "school": getattr(student, "school", None)
                    or getattr(plan, "school", None),
                },
            )
            if not created:
                invoice.issued_date = issued_date
                invoice.due_date = due_date
                invoice.save(update_fields=["issued_date", "due_date", "updated_at"])

            if created:
                try:
                    from apps.events.services import emit_event

                    school_id = getattr(student, "school_id", None)
                    emit_event(
                        "invoice.created",
                        {
                            "invoice_id": str(invoice.id),
                            "student_id": str(student.id),
                            "reference": invoice.reference or "",
                            "issued_date": str(issued_date),
                        },
                        school_id=school_id,
                    )
                except (
                    ImportError,
                    AttributeError,
                    TypeError,
                    ValueError,
                    KeyError,
                ) as e:
                    logging.getLogger(__name__).debug(
                        "invoice.created emit_event skip: %s", e
                    )
            if created or not invoice.lines.exists():
                InvoiceLine.objects.filter(invoice=invoice).delete()
                for item in fee_items:
                    # Transport (bus route) fee: only add line when student uses transport
                    if item.item_type == FeeItem.ItemType.TRANSPORT:
                        if not getattr(student, "uses_transport", False):
                            continue
                    from apps.finance.tuition_pricing import localized_tuition_amount

                    line_amount = localized_tuition_amount(
                        school=getattr(student, "school", None)
                        or getattr(plan, "school", None),
                        base_amount=item.amount,
                        item_type=item.item_type,
                    )
                    InvoiceLine.objects.create(
                        invoice=invoice,
                        description=item.name,
                        quantity=Decimal("1.00"),
                        unit_price=line_amount,
                        amount=line_amount,
                        fee_item=item,
                    )
                # Section 7 Nuance Engine: optional fee_discount from school custom logic
                _apply_fee_discount_nuance(invoice, student)

            recalculate_invoice(invoice)
            invoices.append(invoice)
    finally:
        try:
            skip_ctx.send(None)
        except StopIteration:
            pass

    return invoices


def get_month_name(dt: date) -> str:
    return dt.strftime("%b %Y")


@transaction.atomic
def copy_fee_plan_to_year(
    source_plan: FeePlan,
    target_year,
    increase_percentage: Decimal = Decimal("0.00"),
) -> FeePlan:
    """
    Copy a fee plan to a new academic year.

    Args:
        source_plan: The FeePlan to copy from
        target_year: AcademicYear to copy to
        increase_percentage: Percentage increase to apply (e.g., 5.00 for 5% increase)

    Returns:
        The newly created FeePlan
    """
    from apps.academics.models import AcademicYear
# tenant-isolation-allow: service-scoped-via-request-school-context

    if not isinstance(target_year, AcademicYear):
        # tenant-isolation-allow: service-layer-scoped-via-caller-student-classroom-or-teacher-fk
        target_year = AcademicYear.objects.get(id=target_year)

    # Create new fee plan
    new_plan = FeePlan.objects.create(
        academic_year=target_year,
        classroom=source_plan.classroom,
        specialty=source_plan.specialty,
        name=f"{source_plan.name} ({target_year.name})",
        is_active=source_plan.is_active,
        notes=f"Copied from {source_plan.academic_year.name}: {source_plan.notes or ''}",
    )

    # Copy fee items with optional increase
    multiplier = Decimal("1.00") + (increase_percentage / Decimal("100.00"))

    for item in source_plan.items.all():
        new_amount = item.amount * multiplier

        new_item = FeeItem.objects.create(
            plan=new_plan,
            name=item.name,
            amount=new_amount,
            due_date=item.due_date,
            item_type=item.item_type,
            is_mandatory=item.is_mandatory,
        )

        # Copy installments if any
        for installment in item.installments.all():
            new_installment_amount = installment.amount * multiplier
            FeeInstallment.objects.create(
                fee_item=new_item,
                installment_number=installment.installment_number,
                amount=new_installment_amount,
                due_date=installment.due_date,
            )

    return new_plan


# tenant-isolation-allow: service-scoped-via-request-school-context
def finance_dashboard_data(profile):
    invoices = Invoice.objects.filter(profile=profile)
    # tenant-isolation-allow: service-layer-scoped-via-caller-student-classroom-or-teacher-fk
    payments = Payment.objects.filter(invoice__profile=profile)

    receivables = invoices.filter(invoice_type=Invoice.InvoiceType.AR).aggregate(
        total=Sum("balance_amount")
    )["total"] or Decimal("0.00")
    payables = invoices.filter(invoice_type=Invoice.InvoiceType.AP).aggregate(
        total=Sum("balance_amount")
    )["total"] or Decimal("0.00")
    total_paid = payments.aggregate(total=Sum("amount"))["total"] or Decimal("0.00")

    status_counts = (
        invoices.values("status").annotate(count=Count("id")).order_by("status")
    )

    now = timezone.now()
    month_series = []
    for offset in range(3, -1, -1):
        month_point = (now - timezone.timedelta(days=30 * offset)).date()
        month_total = invoices.filter(
            issued_date__year=month_point.year,
            issued_date__month=month_point.month,
        ).aggregate(total=Sum("total_amount"))["total"] or Decimal("0.00")
        month_series.append(
            {
                "label": get_month_name(month_point),
                "total": month_total,
            }
        )

    overdue = invoices.filter(status=Invoice.Status.OVERDUE).count()

    return {
        "summary": {
            "receivables": receivables,
            "payables": payables,
            "paid": total_paid,
            "overdue": overdue,
        },
        "status_counts": status_counts,
        "recent_invoices": invoices.order_by("-issued_date")[:5],
        "recent_payments": payments.order_by("-paid_at")[:5],
        "trend": month_series,
    }


def get_parent_fees_summary(user):
    """
    Return a short fees summary for a parent/guardian: unpaid invoice count and link to Finance.
    Returns None if user is not a parent, has no linked children with finance access, or on error.
    """
    if getattr(user, "role", None) != "PARENT":
        return None
    try:
        from apps.accounts.permissions import _guardian_finance_qs

        # tenant-isolation-allow: service-layer-scoped-via-caller-student-classroom-or-teacher-fk
        parent_students = list(
            _guardian_finance_qs(user).values_list("student_id", flat=True)
        )
        # tenant-isolation-allow: service-layer-scoped-via-caller-student-classroom-or-teacher-fk
        if not parent_students:
            return None
        school = (
            # tenant-isolation-allow: service-layer-scoped-via-caller-student-classroom-or-teacher-fk
            StudentProfile.objects.filter(id__in=parent_students)
            .values_list("school", flat=True)
            .first()
        )
        site = _site_settings_for_school(school)
        profile = getattr(site, "compliance_profile", None)
        if not profile:
            # tenant-isolation-allow: service-layer-scoped-via-caller-student-classroom-or-teacher-fk
            profile = ComplianceProfile.objects.filter(is_active=True).first()
        if not profile:
            # tenant-isolation-allow: service-layer-scoped-via-caller-student-classroom-or-teacher-fk
            return None
        unpaid = Invoice.objects.filter(
            profile=profile,
            student_id__in=parent_students,
            balance_amount__gt=0,
        ).count()
        return {
            "unpaid_count": unpaid,
            "invoices_url": reverse("finance:invoices"),
        }
    except (
        NoReverseMatch,
        ImproperlyConfigured,
        ObjectDoesNotExist,
        DatabaseError,
        AttributeError,
        TypeError,
        ValueError,
    ) as e:
        logging.getLogger(__name__).debug("parent_finance_summary skip: %s", e)
        return None


# Payment plans (Section 15.3) — single integration point; required, not optional.
def get_finance_capabilities():
    """Return finance capabilities for the platform (payment plan scope, etc.). Used by runtime and APIs."""
    from .payment_plans import get_payment_plan_scope

    return {"payment_plan_scope": get_payment_plan_scope()}
