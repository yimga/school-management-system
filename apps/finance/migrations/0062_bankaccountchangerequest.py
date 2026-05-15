# v2.57 — anti-fraud combined wave: M-of-N dual-authorization for high-risk
# financial routing changes (bank account create / update / deactivate).
# See apps/finance/bank_account_dual_auth.py for the service layer.

import uuid

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("finance", "0061_alter_bankaccount_currency_and_more"),
        ("schools", "0001_initial"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="BankAccountChangeRequest",
            fields=[
                (
                    "id",
                    models.UUIDField(
                        default=uuid.uuid4,
                        editable=False,
                        primary_key=True,
                        serialize=False,
                    ),
                ),
                (
                    "change_kind",
                    models.CharField(
                        choices=[
                            ("CREATE", "Create new bank account"),
                            ("UPDATE", "Modify existing bank account"),
                            ("DEACTIVATE", "Deactivate bank account"),
                        ],
                        max_length=16,
                    ),
                ),
                (
                    "payload",
                    models.JSONField(
                        default=dict,
                        help_text=(
                            "Proposed field values. For CREATE: the full account spec. "
                            "For UPDATE: only the fields being changed (with their new values). "
                            "For DEACTIVATE: empty (the action is implicit)."
                        ),
                    ),
                ),
                (
                    "reason",
                    models.TextField(help_text="Why the requester needs this change. Mandatory."),
                ),
                (
                    "approver_note",
                    models.TextField(
                        blank=True,
                        help_text="Approver's justification (visible in audit log).",
                    ),
                ),
                (
                    "state",
                    models.CharField(
                        choices=[
                            ("PENDING", "Pending second-admin approval"),
                            ("APPROVED", "Approved & applied"),
                            ("REJECTED", "Rejected by peer approver"),
                            ("EXPIRED", "Expired without decision"),
                        ],
                        db_index=True,
                        default="PENDING",
                        max_length=16,
                    ),
                ),
                ("requester_ip", models.GenericIPAddressField(blank=True, null=True)),
                ("approver_ip", models.GenericIPAddressField(blank=True, null=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("decided_at", models.DateTimeField(blank=True, null=True)),
                (
                    "expires_at",
                    models.DateTimeField(help_text="Pending requests auto-expire after this time."),
                ),
                (
                    "approver",
                    models.ForeignKey(
                        blank=True,
                        help_text="The peer administrator who approved or rejected the change.",
                        null=True,
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="bank_account_change_requests_decided",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "bank_account",
                    models.ForeignKey(
                        blank=True,
                        help_text="Target account; null for CREATE (account does not exist yet).",
                        null=True,
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="change_requests",
                        to="finance.bankaccount",
                    ),
                ),
                (
                    "requester",
                    models.ForeignKey(
                        help_text="The administrator who initiated the change.",
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="bank_account_change_requests_filed",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "school",
                    models.ForeignKey(
                        help_text="Tenant the change targets — required for tenant isolation.",
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="bank_account_change_requests",
                        to="schools.school",
                    ),
                ),
            ],
            options={
                "verbose_name": "Bank account change request",
                "verbose_name_plural": "Bank account change requests",
                "ordering": ("-created_at",),
            },
        ),
        migrations.AddIndex(
            model_name="bankaccountchangerequest",
            index=models.Index(
                fields=["school", "state"],
                name="finance_ban_school__de51c6_idx",
            ),
        ),
        migrations.AddIndex(
            model_name="bankaccountchangerequest",
            index=models.Index(
                fields=["state", "expires_at"],
                name="finance_ban_state_742143_idx",
            ),
        ),
    ]
