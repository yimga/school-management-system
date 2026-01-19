from django.db.models.signals import post_delete, post_save
from django.dispatch import receiver

from .models import Invoice, InvoiceLine, Payment
from .services import apply_payment, recalculate_invoice


@receiver(post_save, sender=Invoice)
def ensure_invoice_reference(sender, instance: Invoice, created: bool, **kwargs):
    if instance.reference:
        return
    Invoice.objects.filter(id=instance.id, reference="").update(reference=f"INV-{instance.id:05d}")


@receiver(post_save, sender=InvoiceLine)
def sync_invoice_totals(sender, instance: InvoiceLine, created: bool, **kwargs):
    recalculate_invoice(instance.invoice)


@receiver(post_delete, sender=InvoiceLine)
def sync_invoice_totals_delete(sender, instance: InvoiceLine, **kwargs):
    recalculate_invoice(instance.invoice)


@receiver(post_save, sender=Payment)
def sync_payment(sender, instance: Payment, created: bool, **kwargs):
    if not instance.receipt_number:
        receipt = f"RCPT-{instance.id:05d}"
        Payment.objects.filter(id=instance.id, receipt_number="").update(receipt_number=receipt)
        instance.receipt_number = receipt
    apply_payment(instance)


@receiver(post_delete, sender=Payment)
def sync_payment_delete(sender, instance: Payment, **kwargs):
    recalculate_invoice(instance.invoice)
