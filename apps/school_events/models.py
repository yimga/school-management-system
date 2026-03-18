from django.conf import settings
from django.db import models
from django.utils.text import slugify


class EventVenue(models.Model):
    school = models.ForeignKey(
        "schools.School", on_delete=models.CASCADE, related_name="event_venues"
    )
    name = models.CharField(max_length=160)
    code = models.SlugField(max_length=80)
    location = models.CharField(max_length=255, blank=True)
    capacity = models.PositiveIntegerField(default=0)
    is_active = models.BooleanField(default=True)
    metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["name"]
        unique_together = [("school", "code")]
        verbose_name = "Event venue"
        verbose_name_plural = "Event venues"

    def __str__(self):
        return self.name


class EventSponsor(models.Model):
    class Tier(models.TextChoices):
        COMMUNITY = "community", "Community"
        BRONZE = "bronze", "Bronze"
        SILVER = "silver", "Silver"
        GOLD = "gold", "Gold"
        PLATINUM = "platinum", "Platinum"

    class Status(models.TextChoices):
        LEAD = "lead", "Lead"
        ACTIVE = "active", "Active"
        FULFILLED = "fulfilled", "Fulfilled"
        INACTIVE = "inactive", "Inactive"

    school = models.ForeignKey(
        "schools.School", on_delete=models.CASCADE, related_name="event_sponsors"
    )
    name = models.CharField(max_length=255)
    tier = models.CharField(max_length=24, choices=Tier.choices, default=Tier.COMMUNITY)
    status = models.CharField(
        max_length=24, choices=Status.choices, default=Status.LEAD
    )
    contact_name = models.CharField(max_length=160, blank=True)
    contact_email = models.EmailField(blank=True)
    website_url = models.URLField(blank=True)
    metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["name"]
        unique_together = [("school", "name")]
        verbose_name = "Event sponsor"
        verbose_name_plural = "Event sponsors"

    def __str__(self):
        return self.name


class SchoolEvent(models.Model):
    class Status(models.TextChoices):
        DRAFT = "draft", "Draft"
        PUBLISHED = "published", "Published"
        COMPLETED = "completed", "Completed"
        CANCELED = "canceled", "Canceled"

    school = models.ForeignKey(
        "schools.School", on_delete=models.CASCADE, related_name="school_events"
    )
    title = models.CharField(max_length=255)
    slug = models.SlugField(max_length=100)
    status = models.CharField(
        max_length=20, choices=Status.choices, default=Status.DRAFT, db_index=True
    )
    summary = models.CharField(max_length=255, blank=True)
    description = models.TextField(blank=True)
    venue = models.ForeignKey(
        EventVenue,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="events",
    )
    organizer_name = models.CharField(max_length=160, blank=True)
    start_at = models.DateTimeField(db_index=True)
    end_at = models.DateTimeField(null=True, blank=True)
    is_public = models.BooleanField(default=True)
    ticketing_enabled = models.BooleanField(default=False)
    sponsorship_enabled = models.BooleanField(default=False)
    fundraising_goal = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    metadata = models.JSONField(default=dict, blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["start_at", "title"]
        unique_together = [("school", "slug")]
        verbose_name = "School event"
        verbose_name_plural = "School events"

    def __str__(self):
        return self.title

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.title)[:100]
        super().save(*args, **kwargs)


class EventTicketTier(models.Model):
    event = models.ForeignKey(
        SchoolEvent, on_delete=models.CASCADE, related_name="ticket_tiers"
    )
    name = models.CharField(max_length=120)
    code = models.SlugField(max_length=40)
    price = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    currency_code = models.CharField(max_length=3, default="USD")
    capacity = models.PositiveIntegerField(default=0)
    sold_quantity = models.PositiveIntegerField(default=0)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["price", "name"]
        unique_together = [("event", "code")]
        verbose_name = "Event ticket tier"
        verbose_name_plural = "Event ticket tiers"

    def __str__(self):
        return f"{self.event.title} - {self.name}"

    @property
    def remaining_capacity(self) -> int:
        if self.capacity <= 0:
            return 0
        return max(self.capacity - self.sold_quantity, 0)


class EventSponsorCommitment(models.Model):
    class Status(models.TextChoices):
        PLEDGED = "pledged", "Pledged"
        ACTIVE = "active", "Active"
        FULFILLED = "fulfilled", "Fulfilled"
        CANCELED = "canceled", "Canceled"

    event = models.ForeignKey(
        SchoolEvent, on_delete=models.CASCADE, related_name="sponsor_commitments"
    )
    sponsor = models.ForeignKey(
        EventSponsor, on_delete=models.CASCADE, related_name="commitments"
    )
    status = models.CharField(
        max_length=20, choices=Status.choices, default=Status.PLEDGED
    )
    pledged_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-pledged_amount", "sponsor__name"]
        unique_together = [("event", "sponsor")]
        verbose_name = "Event sponsor commitment"
        verbose_name_plural = "Event sponsor commitments"

    def __str__(self):
        return f"{self.sponsor.name} @ {self.event.title}"


class EventRegistration(models.Model):
    class Status(models.TextChoices):
        RESERVED = "reserved", "Reserved"
        CONFIRMED = "confirmed", "Confirmed"
        CANCELED = "canceled", "Canceled"
        CHECKED_IN = "checked_in", "Checked in"

    event = models.ForeignKey(
        SchoolEvent, on_delete=models.CASCADE, related_name="registrations"
    )
    ticket_tier = models.ForeignKey(
        EventTicketTier,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="registrations",
    )
    purchaser = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="event_registrations",
    )
    attendee_name = models.CharField(max_length=255)
    attendee_email = models.EmailField(blank=True)
    quantity = models.PositiveIntegerField(default=1)
    amount_due = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    amount_paid = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    status = models.CharField(
        max_length=20, choices=Status.choices, default=Status.RESERVED
    )
    check_in_at = models.DateTimeField(null=True, blank=True)
    metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Event registration"
        verbose_name_plural = "Event registrations"

    def __str__(self):
        return f"{self.attendee_name} @ {self.event.title}"
