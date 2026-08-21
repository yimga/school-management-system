"""Box <-> cloud pairing: the box DISPLAYS a code, a cloud admin APPROVES it.

WHAT THIS REPLACES. Until now a sovereign box was bound to its cloud by hand. An
operator ran ``mint_edge_credential`` on the cloud, read a bearer token printed once
to a terminal, and typed it -- plus ``RMC_EDGE_OPERATOR_BASE`` and
``RMC_EDGE_SCHOOL_SLUG`` -- into ``deploy/selfhost/.env`` before rebuilding the
container. Three hand-copied values, one of them a long-lived secret, per school, at
every install and after every box rebuild. That is the step that has to disappear
before onboarding a school is a product rather than an errand.

WHY THE CODE TRAVELS BOX -> CLOUD AND NOT THE OTHER WAY. The obvious design is the
mirror of this one: the cloud mints a code, an operator carries it to the box, the box
accepts it in a form. It is worse, for a reason specific to how these boxes are
deployed. The edge profile serves a school LAN over plain HTTP by design
(``SECURE_SSL_REDIRECT=0`` / ``SESSION_COOKIE_SECURE=0`` in ``.env.edge.example``,
because secure cookies silently break login there). A form on the box that accepts a
credential is therefore an unauthenticated write surface on a cleartext LAN, and
whoever reaches it can re-point the school's student and finance data at a cloud they
control.

Turned around, the box's pairing screen DISPLAYS a code and accepts nothing. There is
no input to attack. Someone who loads that page learns a code they cannot use, because
redeeming it requires being signed in to the school's cloud tenant as an admin -- where
the password and MFA already live. The authorization decision happens where the strong
authentication already is, so the box never needs an auth story of its own.

Two consequences worth stating plainly, because they are what make this safe:

  * The short code is NOT a secret. It is an identifier a human reads aloud or types.
    What proves the box is the box is ``poll_secret``, which never leaves the box and
    never appears on a screen. Someone who shoulder-surfs the code cannot collect the
    credential; they can at most ask an admin to approve a pairing that then hands the
    credential to the real box.
  * The machine credential is NEVER stored here, not even briefly. Approval only
    records that a human said yes. The credential is minted during the box's next
    authenticated poll and exists only in that one HTTP response. There is no
    ciphertext at rest to leak, and no key to rotate.

DEFERRED APPROVAL IS THE DEFAULT. A request lives for
``RMC_EDGE_PAIRING_TTL_HOURS`` (default 72) rather than the handful of minutes a
device-code flow usually allows. The install and the approval are done by different
people, often on different days, in schools where the person holding cloud admin is
not in the server room. A 15-minute window would mean the technician on site simply
cannot finish, so the honest window is days, and the compensating controls are that
the code is not a secret, the poll secret is, and approval requires an authenticated
admin.
"""
from __future__ import annotations

import hashlib
import secrets
import uuid
from datetime import timedelta

from django.conf import settings
from django.db import models
from django.utils import timezone

from apps.accounts.legacy_hashes.encryption import EncryptedCharField

# Deliberately excludes I, L, O, 0 and 1. A pairing code is read off one screen and
# typed into another, often from a phone photo of a monitor in a server room; the
# characters people confuse are the ones that turn a working code into a support call.
CODE_ALPHABET = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"
CODE_GROUP_LEN = 4
CODE_GROUPS = 2


def generate_user_code() -> str:
    """A short, human-transcribable code such as ``FRTY-8K2M``.

    31**8 is about 8.5e11. That is not cryptographic strength and is not asked to be:
    the code only identifies a pending request to an already-authenticated admin, and
    lookups are rate-limited. The secret in this protocol is ``poll_secret``.
    """
    raw = "".join(
        secrets.choice(CODE_ALPHABET) for _ in range(CODE_GROUP_LEN * CODE_GROUPS)
    )
    return "-".join(
        raw[i : i + CODE_GROUP_LEN] for i in range(0, len(raw), CODE_GROUP_LEN)
    )


def normalize_user_code(value: str) -> str:
    """Fold what a human typed onto what was generated.

    Accepts lower case, missing or extra hyphens, and surrounding whitespace, then
    re-groups into the canonical ``XXXX-XXXX`` shape.

    Deliberately does NOT try to repair confusable characters. Both members of each
    confusable pair (``0``/``O`` and ``1``/``I``/``L``) are absent from
    :data:`CODE_ALPHABET`, so a generated code can contain neither -- there is no
    ambiguity left to resolve, and "helpfully" rewriting one into the other would
    corrupt a code the user typed correctly. A character outside the alphabet means
    the transcription is genuinely wrong, and failing the lookup says so.
    """
    cleaned = "".join(ch for ch in (value or "").upper() if ch.isalnum())
    return "-".join(
        cleaned[i : i + CODE_GROUP_LEN] for i in range(0, len(cleaned), CODE_GROUP_LEN)
    )


def hash_poll_secret(raw: str) -> str:
    return hashlib.sha256((raw or "").encode("utf-8")).hexdigest()


def pairing_ttl_hours() -> int:
    try:
        return max(1, int(getattr(settings, "RMC_EDGE_PAIRING_TTL_HOURS", 72)))
    except (TypeError, ValueError):
        return 72


class EdgePairingRequest(models.Model):
    """One box asking to be adopted by one school's cloud tenant.

    Lives in SHARED_APPS alongside ``schools.School`` and ``accounts.User``, so both
    foreign keys stay on the public side of the tenancy boundary — a SHARED model may
    not reference a TENANT table (see the ``cross-tenancy-fk`` gate).
    """

    class Status(models.TextChoices):
        PENDING = "pending", "Waiting for approval"
        APPROVED = "approved", "Approved, awaiting collection"
        REDEEMED = "redeemed", "Credential collected"
        DENIED = "denied", "Denied"
        EXPIRED = "expired", "Expired"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    # The school the BOX claims to belong to. Claimed, not proven — proof is the admin
    # of that school approving. Nullable so an unrecognised slug still produces a
    # visible, auditable request instead of a silent 404 that tells an operator nothing.
    school = models.ForeignKey(
        "schools.School",
        on_delete=models.CASCADE,
        related_name="edge_pairing_requests",
        null=True,
        blank=True,
    )
    claimed_slug = models.CharField(max_length=100, blank=True, default="")

    user_code = models.CharField(max_length=16, unique=True, db_index=True)
    # Only the sha256. The box keeps the raw value and presents it on every poll; the
    # cloud can verify but can never reveal it, so a database leak does not let an
    # attacker collect a credential for a pending request.
    poll_secret_hash = models.CharField(max_length=64, db_index=True)

    status = models.CharField(
        max_length=16, choices=Status.choices, default=Status.PENDING, db_index=True
    )

    # What the approving admin sees. Self-reported by the box and therefore evidence,
    # not proof — which is exactly why a human approves rather than a rule.
    device_id = models.CharField(max_length=128, blank=True, default="")
    box_label = models.CharField(max_length=120, blank=True, default="")
    box_hostname = models.CharField(max_length=253, blank=True, default="")
    box_ip = models.GenericIPAddressField(null=True, blank=True)
    box_version = models.CharField(max_length=64, blank=True, default="")

    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    expires_at = models.DateTimeField(db_index=True)
    approved_at = models.DateTimeField(null=True, blank=True)
    approved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
    )
    redeemed_at = models.DateTimeField(null=True, blank=True)
    denied_reason = models.CharField(max_length=200, blank=True, default="")

    # Set once the credential has been handed over, so the pairing is traceable to a
    # DeviceRegistration without the credential itself ever being stored here.
    credential_device_id = models.CharField(max_length=128, blank=True, default="")

    last_polled_at = models.DateTimeField(null=True, blank=True)
    poll_count = models.PositiveIntegerField(default=0)

    class Meta:
        app_label = "sync_engine"
        ordering = ["-created_at"]
        verbose_name = "Edge pairing request"
        verbose_name_plural = "Edge pairing requests"
        indexes = [
            models.Index(fields=["school", "status"]),
            models.Index(fields=["status", "expires_at"]),
        ]

    def __str__(self) -> str:  # pragma: no cover - admin/debug convenience
        return f"EdgePairingRequest({self.user_code},{self.status})"

    # ----------------------------------------------------------------- state ---
    @property
    def is_expired(self) -> bool:
        return timezone.now() >= self.expires_at

    @property
    def is_open(self) -> bool:
        """Still worth polling: not spent, not refused, not timed out."""
        return self.status in (self.Status.PENDING, self.Status.APPROVED) and not self.is_expired

    def effective_status(self) -> str:
        """Status with expiry applied, WITHOUT writing.

        Read paths must not depend on a sweeper having run. A request that has aged
        out reports ``expired`` the moment it is looked at, and the row is tidied
        lazily by :meth:`expire_if_due` on paths that are already writing.
        """
        if self.status in (self.Status.PENDING, self.Status.APPROVED) and self.is_expired:
            return self.Status.EXPIRED
        return self.status

    def expire_if_due(self) -> bool:
        if self.status in (self.Status.PENDING, self.Status.APPROVED) and self.is_expired:
            self.status = self.Status.EXPIRED
            self.save(update_fields=["status"])
            return True
        return False

    def verify_poll_secret(self, raw: str) -> bool:
        """Constant-time check that the caller is the box that opened this request."""
        return secrets.compare_digest(
            self.poll_secret_hash, hash_poll_secret(raw)
        )

    def touch_poll(self) -> None:
        self.last_polled_at = timezone.now()
        self.poll_count = (self.poll_count or 0) + 1
        self.save(update_fields=["last_polled_at", "poll_count"])

    # ------------------------------------------------------------ factories ---
    @classmethod
    def open_request(
        cls,
        *,
        school=None,
        claimed_slug: str = "",
        device_id: str = "",
        box_label: str = "",
        box_hostname: str = "",
        box_ip: str | None = None,
        box_version: str = "",
    ) -> tuple["EdgePairingRequest", str]:
        """Create a pending request. Returns ``(request, raw_poll_secret)``.

        The raw poll secret is returned ONCE and never persisted — the box stores it
        and presents it on every poll.
        """
        raw_secret = secrets.token_urlsafe(32)
        # A unique-constraint collision on user_code is astronomically unlikely but
        # trivially recoverable, so retry rather than surfacing an error to a box that
        # did nothing wrong.
        for _ in range(5):
            code = generate_user_code()
            if not cls.objects.filter(user_code=code).exists():
                break
        else:  # pragma: no cover - would require repeated 1-in-8.5e11 collisions
            code = generate_user_code()
        request = cls.objects.create(
            school=school,
            claimed_slug=(claimed_slug or "")[:100],
            user_code=code,
            poll_secret_hash=hash_poll_secret(raw_secret),
            device_id=(device_id or "")[:128],
            box_label=(box_label or "")[:120],
            box_hostname=(box_hostname or "")[:253],
            box_ip=box_ip or None,
            box_version=(box_version or "")[:64],
            expires_at=timezone.now() + timedelta(hours=pairing_ttl_hours()),
        )
        return request, raw_secret


__all__ = [
    "CODE_ALPHABET",
    "EdgeClaimTicket",
    "EdgeCloudBinding",
    "EdgePairingRequest",
    "PendingPushConfirmation",
    "generate_user_code",
    "hash_poll_secret",
    "normalize_user_code",
    "pairing_ttl_hours",
]


class EdgeCloudBinding(models.Model):
    """What a BOX knows about the cloud it is paired to. One row, on the box.

    THE PROBLEM THIS SOLVES. ``RMC_EDGE_OPERATOR_BASE`` and ``RMC_EDGE_CREDENTIAL``
    are read from the environment (``settings.py`` and ``sync_runner._edge_token``),
    which means the pairing lives in ``deploy/selfhost/.env`` on the host. That file
    is outside the container, is edited by hand, and is not part of any backup the
    product takes. A box rebuilt from the image — which is the normal way to take an
    update — comes back with whatever the compose file happens to say, and a box whose
    ``.env`` is lost is silently unpaired: sync simply stops, with an error that blames
    connectivity.

    Storing the binding in the box's own database puts it where the school's data
    already is, so it survives a container rebuild, is captured by any backup worth the
    name, and can be written by a pairing flow instead of a text editor.

    PRECEDENCE, and why this way round. A binding written here WINS over the
    environment. That is the opposite of the usual "env overrides everything" reflex,
    and it is deliberate: pairing is a recent, deliberate, human-approved act, whereas
    a stale env var baked into a compose file is exactly the artefact this replaces.
    A box with no binding still reads the environment unchanged, so every existing
    deployment keeps working with no migration step. To go back to the environment,
    clear the binding explicitly (``manage.py pair_box --unpair``) rather than hoping
    two sources of truth disagree in your favour.
    """

    SOURCE_PAIRING = "pairing"
    SOURCE_MANUAL = "manual"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    operator_base = models.CharField(max_length=255, blank=True, default="")
    school_slug = models.CharField(max_length=100, blank=True, default="")
    school_name = models.CharField(max_length=200, blank=True, default="")
    device_id = models.CharField(max_length=128, blank=True, default="")

    # Fernet at rest. The box database already holds the school's records, so an
    # attacker with the database does not NEED this token — but a credential is the
    # one field that grants access to a DIFFERENT system, and it should not sit in
    # plaintext in a backup that gets copied to a USB stick.
    credential = EncryptedCharField(max_length=512, blank=True, default="")
    credential_expires_at = models.DateTimeField(null=True, blank=True)

    paired_at = models.DateTimeField(null=True, blank=True)
    paired_via = models.CharField(max_length=16, blank=True, default=SOURCE_PAIRING)
    # Once a box has been paired, its pairing screen stops serving anonymous callers.
    # Claim-on-first-boot, then seal: re-pairing is an authenticated or on-box action.
    sealed = models.BooleanField(default=False)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        app_label = "sync_engine"
        verbose_name = "Edge cloud binding"
        verbose_name_plural = "Edge cloud binding"

    def __str__(self) -> str:  # pragma: no cover - admin/debug convenience
        return f"EdgeCloudBinding({self.school_slug or '-'},{self.operator_base or '-'})"

    @property
    def is_paired(self) -> bool:
        return bool(self.operator_base and self.credential)


class PendingPushConfirmation(models.Model):
    """A bundle this box pushed whose fate it never learned.

    Recorded when a push fails AMBIGUOUSLY -- a read timeout, a connection reset, or a
    gateway 502/503/504. Those all mean the request reached (or may have reached) the
    cloud and the answer was lost on the way back, so the cloud may well have applied
    the rows. A 400 or a 403 is NOT ambiguous: the cloud answered, and the answer was
    no, so nothing is recorded for those.

    On the next cycle the box asks ``/api/sync/bundle/receipt/`` whether this nonce was
    accepted. Yes -> advance the cursor over that page and skip the re-push. No ->
    re-ship exactly as before. Either way the row is deleted; it is a question waiting
    to be asked, not a queue.

    Note what this is NOT protecting against. Re-shipping was always CORRECT --
    ``export_delta_bundle`` regenerates the nonce per build, so a rebuilt bundle is new
    to the replay guard and the apply is idempotent. This saves the bandwidth of
    re-sending a whole page over a link that has just demonstrated it is unreliable,
    which on a metered village connection is the difference that matters.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    school = models.ForeignKey(
        "schools.School",
        on_delete=models.CASCADE,
        related_name="pending_push_confirmations",
    )
    nonce = models.CharField(max_length=64, db_index=True)
    # Where the cursor would move to if the cloud confirms it took this page.
    high_water = models.CharField(max_length=64, blank=True, default="")
    row_count = models.IntegerField(default=0)
    # Unix seconds from the bundle header, so the cloud can tell us whether its
    # "not seen" is confident or merely outside the pruning window.
    built_at = models.BigIntegerField(default=0)
    failure = models.CharField(max_length=120, blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    attempts = models.PositiveSmallIntegerField(default=0)

    class Meta:
        app_label = "sync_engine"
        ordering = ["created_at"]
        verbose_name = "Pending push confirmation"
        verbose_name_plural = "Pending push confirmations"
        constraints = [
            models.UniqueConstraint(
                fields=["school", "nonce"], name="uq_pendingpushconfirmation_nonce"
            )
        ]

    def __str__(self) -> str:  # pragma: no cover - admin/debug convenience
        return f"PendingPushConfirmation({self.nonce[:12]},{self.row_count} rows)"


class EdgeClaimTicket(models.Model):
    """A pre-authorised adoption, minted BEFORE the box exists.

    THE CASE THIS EXISTS FOR. A technician installs a box at a school with a scheduled
    visit and no way to reach anyone holding cloud admin — the school's admin is
    unreachable, or the school has just been provisioned and has no admin logged in
    anywhere. Deferred approval (72h) plus an emailed nudge covers "nobody is at a
    console right now"; it does not cover "the box must be syncing before I leave the
    site."

    HOW IT IS DIFFERENT FROM A CREDENTIAL, which is the whole reason it is acceptable
    at all. A ticket is not a bearer token for the sync API. It buys exactly one thing:
    the right to have ONE pairing request auto-approved for ONE named school. It is:

      * single-use — ``redeemed_at`` is set inside the same locked transaction that
        consumes it, so a second redemption cannot race the first;
      * self-invalidating — once redeemed it is permanently spent, not merely expired;
      * short-lived by comparison with a credential (days, against a credential's year);
      * scoped to one school, so it cannot adopt a box into any other tenant;
      * and — the property a leaked long-lived ``RMC_EDGE_CREDENTIAL`` can never give
        you — a SECOND attempt to redeem a spent ticket is a high-quality intrusion
        signal, because the legitimate box redeems exactly once and never again.

    So the tradeoff is real but bounded: a leaked ticket is useful only until the real
    box claims it, and its misuse is loud. A leaked credential is useful for a year and
    silent. That asymmetry is why this exists and why it is not simply "the old way
    with extra steps".

    The redemption still flows through ``EdgePairingRequest``, so an operator-issued
    box appears in the same audit trail as a human-approved one, carrying the name of
    whoever minted the ticket in ``approved_by``.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    school = models.ForeignKey(
        "schools.School",
        on_delete=models.CASCADE,
        related_name="edge_claim_tickets",
    )
    # Only the sha256 is stored, exactly as for the machine credential itself: an
    # operator who loses the printed ticket mints a new one, and a database leak does
    # not hand anyone a working ticket.
    ticket_hash = models.CharField(max_length=64, unique=True, db_index=True)
    label = models.CharField(max_length=120, blank=True, default="")

    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
    )
    expires_at = models.DateTimeField(db_index=True)

    redeemed_at = models.DateTimeField(null=True, blank=True)
    redeemed_by_request = models.ForeignKey(
        "sync_engine.EdgePairingRequest",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
    )
    revoked_at = models.DateTimeField(null=True, blank=True)
    # Every attempt to use a spent or revoked ticket. Not a counter for its own sake:
    # the legitimate box redeems once, so anything above zero here means someone else
    # has the ticket.
    misuse_attempts = models.PositiveIntegerField(default=0)
    last_misuse_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        app_label = "sync_engine"
        ordering = ["-created_at"]
        verbose_name = "Edge claim ticket"
        verbose_name_plural = "Edge claim tickets"
        indexes = [models.Index(fields=["school", "redeemed_at"])]

    def __str__(self) -> str:  # pragma: no cover - admin/debug convenience
        return f"EdgeClaimTicket({self.school_id},{'spent' if self.redeemed_at else 'open'})"

    @property
    def is_usable(self) -> bool:
        return (
            self.redeemed_at is None
            and self.revoked_at is None
            and timezone.now() < self.expires_at
        )

    @classmethod
    def mint(cls, *, school, created_by=None, days: int = 14, label: str = ""):
        """Create a ticket. Returns ``(raw_ticket, row)``; the raw is shown ONCE."""
        raw = f"RMC-{secrets.token_urlsafe(24)}"
        row = cls.objects.create(
            school=school,
            ticket_hash=hash_poll_secret(raw),
            label=(label or "")[:120],
            created_by=created_by,
            expires_at=timezone.now() + timedelta(days=max(1, int(days))),
        )
        return raw, row
