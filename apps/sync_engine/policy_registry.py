"""Versioned conflict and CRDT policy registry for local-first synchronization."""

from __future__ import annotations

from dataclasses import dataclass


POLICY_VERSION = 2


class MergeStrategy:
    CAUSAL_LWW = "causal_lww"
    SERVER_AUTHORITATIVE = "server_authoritative"
    MANUAL_REVIEW = "manual_review"
    FIELD_MERGE = "field_merge"
    APPEND_ONLY = "append_only"
    OR_SET = "or_set"
    G_COUNTER = "g_counter"
    # v2: the domain may not even be QUEUED offline — a live online
    # transaction is the only valid path (distinct from SERVER_AUTHORITATIVE,
    # where an offline attempt is accepted and the server's copy then wins).
    ONLINE_REQUIRED = "online_required"


@dataclass(frozen=True)
class SyncPolicy:
    entity: str
    strategy: str
    protected: bool = False
    allowed_crdt_kinds: frozenset[str] = frozenset()
    rationale: str = ""


ENTITY_ALIASES = {
    "attendance": "attendance_record",
    "grade": "grade_entry",
    "grading": "grade_entry",
    # evals.Evaluation IS the platform's grade row (its scores feed final_score and the
    # report card), so the edge rail registers it as `evaluation` and it must inherit the
    # protected grade_entry policy. Without this alias it was protected only INCIDENTALLY,
    # by get_policy's fail-closed default for unknown entities — declaring it makes the
    # down-only guarantee explicit and survives any future change to that default.
    "evaluation": "grade_entry",
    "payment": "fee_payment",
    "payment_proof": "payment_proof_upload",
    "profile": "user_profile",
    "message": "message_event",
    "offboarding": "tenant_lifecycle_action",
    "tenant_lifecycle": "tenant_lifecycle_action",
    "settlement": "payment_settlement",
    "mfa": "security_credential",
    "password": "security_credential",
}


POLICIES: dict[str, SyncPolicy] = {
    "attendance_record": SyncPolicy(
        entity="attendance_record",
        strategy=MergeStrategy.CAUSAL_LWW,
        rationale=(
            "A later causally ranked roll-call correction may replace an earlier "
            "mark through the canonical attendance replay handler."
        ),
    ),
    "student_note": SyncPolicy(
        entity="student_note",
        strategy=MergeStrategy.CAUSAL_LWW,
        allowed_crdt_kinds=frozenset({"LWW"}),
        rationale="Approved low-risk scalar note drafts may converge by causal rank.",
    ),
    "lesson_plan": SyncPolicy(
        entity="lesson_plan",
        strategy=MergeStrategy.CAUSAL_LWW,
        allowed_crdt_kinds=frozenset({"LWW"}),
        rationale="Reversible lesson-plan drafts may converge by causal rank.",
    ),
    "contact_preferences": SyncPolicy(
        entity="contact_preferences",
        strategy=MergeStrategy.FIELD_MERGE,
        rationale="Non-identity contact preferences may merge disjoint fields.",
    ),
    "lesson_plan_tags": SyncPolicy(
        entity="lesson_plan_tags",
        strategy=MergeStrategy.OR_SET,
        allowed_crdt_kinds=frozenset({"ORSET-ADD", "ORSET-REMOVE"}),
        rationale="Tags use observed-remove set semantics.",
    ),
    "telemetry_counter": SyncPolicy(
        entity="telemetry_counter",
        strategy=MergeStrategy.G_COUNTER,
        allowed_crdt_kinds=frozenset({"GCOUNTER"}),
        rationale="Non-authoritative monotonic telemetry may use a grow-only counter.",
    ),
    "message_event": SyncPolicy(
        entity="message_event",
        strategy=MergeStrategy.APPEND_ONLY,
        protected=True,
        rationale="Messages are immutable events and must not overwrite one another.",
    ),
    "behavior_event": SyncPolicy(
        entity="behavior_event",
        strategy=MergeStrategy.APPEND_ONLY,
        protected=True,
        rationale="Behavior records are auditable events, not mutable registers.",
    ),
    "homework_submission": SyncPolicy(
        entity="homework_submission",
        strategy=MergeStrategy.SERVER_AUTHORITATIVE,
        protected=True,
        rationale="An accepted server submission is authoritative.",
    ),
    "invoice": SyncPolicy(
        entity="invoice",
        strategy=MergeStrategy.MANUAL_REVIEW,
        protected=True,
        rationale=(
            "An invoice is what a family OWES. The box receives it so a bursar can work "
            "offline, but money is cloud-authoritative: an upward change needs an "
            "accountable human decision, never last-writer-wins. Declared EXPLICITLY "
            "rather than left to get_policy's fail-closed default, so the guarantee "
            "survives any future change to that default."
        ),
    ),
    "grade_entry": SyncPolicy(
        entity="grade_entry",
        strategy=MergeStrategy.MANUAL_REVIEW,
        protected=True,
        rationale="Concurrent grade changes require an accountable human decision.",
    ),
    "payment_proof_upload": SyncPolicy(
        entity="payment_proof_upload",
        strategy=MergeStrategy.MANUAL_REVIEW,
        protected=True,
        rationale="Payment evidence cannot be silently replaced.",
    ),
    "invoice_line": SyncPolicy(
        entity="invoice_line",
        strategy=MergeStrategy.MANUAL_REVIEW,
        protected=True,
        rationale="Financial ledger inputs require explicit review.",
    ),
    "fee_payment": SyncPolicy(
        entity="fee_payment",
        strategy=MergeStrategy.MANUAL_REVIEW,
        protected=True,
        rationale="Money movement cannot be auto-merged.",
    ),
    "wallet_operation": SyncPolicy(
        entity="wallet_operation",
        strategy=MergeStrategy.APPEND_ONLY,
        protected=True,
        rationale="Wallet changes use the canonical unique operation log.",
    ),
    "user_profile": SyncPolicy(
        entity="user_profile",
        strategy=MergeStrategy.SERVER_AUTHORITATIVE,
        protected=True,
        rationale="Identity attributes remain server-authoritative.",
    ),
    "permission_grant": SyncPolicy(
        entity="permission_grant",
        strategy=MergeStrategy.SERVER_AUTHORITATIVE,
        protected=True,
        rationale="Authorization changes must be validated by the server.",
    ),
    "tenant_lifecycle_action": SyncPolicy(
        entity="tenant_lifecycle_action",
        strategy=MergeStrategy.ONLINE_REQUIRED,
        protected=True,
        rationale=(
            "Suspension, offboarding, and purge are destructive lifecycle "
            "actions; a disconnected device must never queue or replay them."
        ),
    ),
    "security_credential": SyncPolicy(
        entity="security_credential",
        strategy=MergeStrategy.ONLINE_REQUIRED,
        protected=True,
        rationale=(
            "Password/MFA/credential changes take effect only through a live "
            "authenticated session — an offline queue would delay revocation."
        ),
    ),
    "payment_settlement": SyncPolicy(
        entity="payment_settlement",
        strategy=MergeStrategy.ONLINE_REQUIRED,
        protected=True,
        rationale=(
            "Executing a charge against a gateway is a live transaction; "
            "offline evidence capture belongs to fee_payment/payment_proof."
        ),
    ),
}


def normalize_entity(entity: str) -> str:
    raw = str(entity or "").strip().lower()
    return ENTITY_ALIASES.get(raw, raw)


def get_policy(entity: str) -> SyncPolicy:
    normalized = normalize_entity(entity)
    return POLICIES.get(
        normalized,
        SyncPolicy(
            entity=normalized,
            strategy=MergeStrategy.MANUAL_REVIEW,
            protected=True,
            rationale="Unknown entities fail closed to manual review.",
        ),
    )


def is_online_required(entity: str) -> bool:
    """Whether the domain may only be performed through a live connection."""
    return get_policy(entity).strategy == MergeStrategy.ONLINE_REQUIRED


def validate_crdt_kind(entity: str, kind: str) -> SyncPolicy:
    policy = get_policy(entity)
    normalized_kind = str(kind or "").strip().upper()
    if normalized_kind not in policy.allowed_crdt_kinds:
        raise ValueError(
            f"crdt_kind_not_allowed:{policy.entity}:{normalized_kind or 'missing'}"
        )
    return policy


__all__ = [
    "ENTITY_ALIASES",
    "MergeStrategy",
    "POLICIES",
    "POLICY_VERSION",
    "SyncPolicy",
    "get_policy",
    "is_online_required",
    "normalize_entity",
    "validate_crdt_kind",
]
