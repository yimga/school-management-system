from decimal import Decimal
from django.utils import timezone

from django import forms

from apps.people.models import StudentGuardian

from .models import BankAccount, PaymentMethodCode, ReportRequest


class ReportRequestForm(forms.ModelForm):
    class Meta:
        model = ReportRequest
        fields = ["report_type", "description"]
        widgets = {
            "report_type": forms.Select(attrs={"class": "form-select"}),
            "description": forms.Textarea(attrs={"class": "form-control", "rows": 3}),
        }


class SplitAllocationForm(forms.Form):
    """Form to record a single payment split across fee types (Tuition, Sports, Workshop, etc.)."""

    NUM_ROWS = 5
    NUM_PAYER_ROWS = 4
    SPLIT_MODE_CHOICES = (
        ("none", "No payer split"),
        ("equal", "Auto-split equally across guardians"),
        ("custom", "Custom guardian split"),
    )

    student = forms.ModelChoiceField(
        queryset=None,
        required=True,
        label="Student",
        widget=forms.Select(attrs={"class": "form-select"}),
    )
    total_amount = forms.DecimalField(
        min_value=Decimal("0.01"),
        max_digits=12,
        decimal_places=2,
        required=True,
        label="Total amount",
        widget=forms.NumberInput(attrs={"class": "form-control", "step": "0.01"}),
    )
    method = forms.ChoiceField(
        choices=PaymentMethodCode.choices,
        required=True,
        label="Payment method",
        widget=forms.Select(attrs={"class": "form-select"}),
    )
    split_mode = forms.ChoiceField(
        choices=SPLIT_MODE_CHOICES,
        required=False,
        initial="none",
        label="Payer split mode",
        widget=forms.Select(attrs={"class": "form-select"}),
    )

    def __init__(self, *args, student_queryset=None, guardian_queryset=None, **kwargs):
        super().__init__(*args, **kwargs)
        if student_queryset is not None:
            self.fields["student"].queryset = student_queryset
        self._guardian_queryset = (
            guardian_queryset
            if guardian_queryset is not None
            else StudentGuardian.objects.none()
        )
        for i in range(1, self.NUM_ROWS + 1):
            self.fields[f"desc_{i}"] = forms.CharField(
                required=False,
                max_length=200,
                label=f"Line {i} description",
                widget=forms.TextInput(
                    attrs={
                        "class": "form-control",
                        "placeholder": "e.g. Tuition, Sports",
                    }
                ),
            )
            self.fields[f"amount_{i}"] = forms.DecimalField(
                required=False,
                min_value=Decimal("0"),
                max_digits=12,
                decimal_places=2,
                label=f"Line {i} amount",
                widget=forms.NumberInput(
                    attrs={
                        "class": "form-control allocation-amount",
                        "step": "0.01",
                        "placeholder": "0",
                    }
                ),
            )
        for i in range(1, self.NUM_PAYER_ROWS + 1):
            self.fields[f"payer_guardian_{i}"] = forms.ModelChoiceField(
                queryset=self._guardian_queryset,
                required=False,
                label=f"Payer {i}",
                widget=forms.Select(attrs={"class": "form-select"}),
            )
            self.fields[f"payer_amount_{i}"] = forms.DecimalField(
                required=False,
                min_value=Decimal("0"),
                max_digits=12,
                decimal_places=2,
                label=f"Payer {i} amount",
                widget=forms.NumberInput(
                    attrs={"class": "form-control", "step": "0.01", "placeholder": "0"}
                ),
            )

    def get_allocations(self):
        """Return list of (description, amount) for rows with amount > 0."""
        out = []
        for i in range(1, self.NUM_ROWS + 1):
            amt = self.cleaned_data.get(f"amount_{i}")
            if amt is None or amt <= 0:
                continue
            desc = (self.cleaned_data.get(f"desc_{i}") or "").strip() or f"Line {i}"
            out.append((desc, amt))
        return out

    def get_payer_allocations(self):
        """Return list of (guardian_link, amount) for custom payer rows."""
        out = []
        for i in range(1, self.NUM_PAYER_ROWS + 1):
            guardian = self.cleaned_data.get(f"payer_guardian_{i}")
            amt = self.cleaned_data.get(f"payer_amount_{i}")
            if guardian is None or amt is None or amt <= 0:
                continue
            out.append((guardian, amt))
        return out

    def clean(self):
        data = super().clean()
        total = data.get("total_amount")
        if total is None:
            return data
        sum_alloc = Decimal("0.00")
        count = 0
        for i in range(1, self.NUM_ROWS + 1):
            amt = data.get(f"amount_{i}")
            if amt is not None and amt > 0:
                sum_alloc += amt
                count += 1
        if count == 0:
            self.add_error(None, "Add at least one allocation line with amount > 0.")
            return data
        if sum_alloc != total:
            self.add_error(
                None,
                f"Allocation total ({sum_alloc}) must equal total amount ({total}).",
            )

        split_mode = (data.get("split_mode") or "none").strip().lower()
        if split_mode == "equal":
            if not self._guardian_queryset.exists():
                self.add_error(
                    "split_mode",
                    "Selected student has no finance-enabled guardians for equal split.",
                )
            return data
        if split_mode == "custom":
            payer_total = Decimal("0.00")
            payer_count = 0
            guardian_ids = set()
            for i in range(1, self.NUM_PAYER_ROWS + 1):
                guardian = data.get(f"payer_guardian_{i}")
                amount = data.get(f"payer_amount_{i}")
                has_guardian = guardian is not None
                has_amount = amount is not None and amount > 0
                if has_guardian != has_amount:
                    self.add_error(
                        None, f"Payer row {i} requires both guardian and amount."
                    )
                    continue
                if not has_guardian:
                    continue
                if guardian.id in guardian_ids:
                    self.add_error(
                        None, "A guardian can only appear once in custom split."
                    )
                    continue
                guardian_ids.add(guardian.id)
                payer_total += amount
                payer_count += 1
            if payer_count == 0:
                self.add_error(
                    "split_mode", "Add at least one payer allocation for custom split."
                )
                return data
            if payer_total != total:
                self.add_error(
                    None,
                    f"Payer split total ({payer_total}) must equal total amount ({total}).",
                )
        return data


class CashOfficeClosureForm(forms.Form):
    closure_date = forms.DateField(
        required=True,
        initial=timezone.localdate,
        widget=forms.DateInput(attrs={"type": "date", "class": "form-control"}),
    )
    opening_cash = forms.DecimalField(
        required=True,
        min_value=Decimal("0.00"),
        max_digits=12,
        decimal_places=2,
        initial=Decimal("0.00"),
        widget=forms.NumberInput(attrs={"class": "form-control", "step": "0.01"}),
    )
    deposited_to_bank = forms.DecimalField(
        required=True,
        min_value=Decimal("0.00"),
        max_digits=12,
        decimal_places=2,
        initial=Decimal("0.00"),
        widget=forms.NumberInput(attrs={"class": "form-control", "step": "0.01"}),
    )
    cash_on_hand = forms.DecimalField(
        required=True,
        min_value=Decimal("0.00"),
        max_digits=12,
        decimal_places=2,
        initial=Decimal("0.00"),
        widget=forms.NumberInput(attrs={"class": "form-control", "step": "0.01"}),
    )
    bank_account = forms.ModelChoiceField(
        queryset=BankAccount.objects.none(),
        required=False,
        widget=forms.Select(attrs={"class": "form-select"}),
    )
    deposit_reference = forms.CharField(
        required=False,
        max_length=100,
        widget=forms.TextInput(
            attrs={"class": "form-control", "placeholder": "e.g. BNK-2026-02-12-001"}
        ),
    )
    notes = forms.CharField(
        required=False,
        widget=forms.Textarea(
            attrs={
                "class": "form-control",
                "rows": 2,
                "placeholder": "Closure notes / anomalies",
            }
        ),
    )

    def __init__(self, *args, profile=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["bank_account"].queryset = BankAccount.objects.filter(
            is_active=True,
            account_type=BankAccount.AccountType.BANK,
        ).order_by("name")


class TellerScanForm(forms.Form):
    """
    OCR scan helper for physical bank tellers and paper receipts.
    This does not post accounting entries directly; it extracts and validates.
    """

    receipt_file = forms.FileField(
        required=True,
        widget=forms.ClearableFileInput(
            attrs={
                "class": "form-control",
                "accept": ".jpg,.jpeg,.png,.pdf",
            }
        ),
    )
    expected_amount = forms.DecimalField(
        required=False,
        min_value=Decimal("0.01"),
        max_digits=12,
        decimal_places=2,
        widget=forms.NumberInput(
            attrs={
                "class": "form-control",
                "step": "0.01",
                "placeholder": "Optional expected amount",
            }
        ),
    )
    transaction_reference = forms.CharField(
        required=False,
        max_length=100,
        widget=forms.TextInput(
            attrs={
                "class": "form-control",
                "placeholder": "Optional teller / transaction reference",
            }
        ),
    )
    payment_method = forms.ChoiceField(
        required=False,
        choices=[("", "Unknown")] + list(PaymentMethodCode.choices),
        widget=forms.Select(attrs={"class": "form-select"}),
    )
