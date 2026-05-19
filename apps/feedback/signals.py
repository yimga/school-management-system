"""Move 4 — close the help-center loop.

Emits transactional emails on ReleaseNote / FeedbackSubmission state changes.
The handlers are wired in apps/feedback/apps.py via ready().
"""

from __future__ import annotations

import logging
from typing import Iterable

from django.contrib.auth import get_user_model
from django.core.mail import send_mail
from django.db.models.signals import post_save
from django.dispatch import receiver

from apps.feedback.models import (
    FeatureRequest,
    FeedbackSubmission,
    FeedbackVote,
    ReleaseNote,
)

logger = logging.getLogger(__name__)
User = get_user_model()


def _user_emails(users: Iterable[User]) -> list[str]:
    seen = set()
    out = []
    for u in users:
        email = (getattr(u, "email", "") or "").strip().lower()
        if email and email not in seen:
            seen.add(email)
            out.append(email)
    return out


def _send_quiet(*, subject: str, body: str, recipients: list[str]) -> int:
    if not recipients:
        return 0
    try:
        return send_mail(
            subject=subject,
            message=body,
            from_email=None,
            recipient_list=recipients,
            fail_silently=False,
        )
    except Exception as exc:
        logger.warning("feedback signal email failed (%s recipients): %s", len(recipients), exc)
        return 0


@receiver(post_save, sender=ReleaseNote)
def _email_submitters_on_release(sender, instance: ReleaseNote, created, **kwargs):
    """When a ReleaseNote is saved with notify_submitters=True, email everyone:

    1) Whose FeedbackSubmission resolved to a FeatureRequest linked to the release
    2) Who voted on those FeatureRequests
    """

    if not getattr(instance, "notify_submitters", False):
        return

    feature_request_ids = set(instance.feature_requests.values_list("id", flat=True))
    # Also pull through the RoadmapItem's linked requests.
    if instance.roadmap_item_id:
        rm_ids = FeatureRequest.objects.filter(  # tenant-isolation-allow: public-feature-request-vote-aggregate
            roadmap_items=instance.roadmap_item_id
        ).values_list("id", flat=True)
        feature_request_ids.update(rm_ids)
    if not feature_request_ids:
        return

    submitter_ids = set(
        FeatureRequest.objects.filter(id__in=feature_request_ids)  # tenant-isolation-allow: public-feature-request-status-notify
        .values_list("submitted_by_id", flat=True)
    )
    voter_ids = set(
        FeedbackVote.objects.filter(feature_request_id__in=feature_request_ids)  # tenant-isolation-allow: public-feedback-vote-dedup-global
        .values_list("user_id", flat=True)
    )
    recipient_ids = (submitter_ids | voter_ids) - {None}
    users = User.objects.filter(id__in=recipient_ids)
    recipients = _user_emails(users)
    if not recipients:
        return

    title = (instance.title or "an update you asked about").strip()
    summary = (instance.summary or "").strip()
    body = (
        "Hi,\n\n"
        f"You asked for or voted on a feature that just shipped: {title}.\n\n"
        f"{summary or 'See the release notes for details.'}\n\n"
        "— RunMyCampus\n"
    )
    _send_quiet(
        subject=f"Shipped: {title}",
        body=body,
        recipients=recipients,
    )


@receiver(post_save, sender=FeedbackSubmission)
def _email_submitter_on_state_change(sender, instance: FeedbackSubmission, created, **kwargs):
    """When a FeedbackSubmission's status changes from new -> something else,
    drop the submitter a confirmation email.

    We avoid the post_save spam loop by only firing on rows that have an
    `updated_at - created_at > 1s` heuristic; the goal is to acknowledge real
    triage state-changes, not the initial create.
    """

    if created:
        return
    try:
        delta = (instance.updated_at - instance.created_at).total_seconds() if instance.updated_at and instance.created_at else 0
    except TypeError:
        delta = 0
    if delta < 1:
        return
    user = getattr(instance, "user", None)
    if user is None or not getattr(user, "email", None):
        return
    body = (
        "Hi,\n\n"
        f"Your feedback ({instance.title or 'submission'}) is now: {instance.status}.\n\n"
        "We'll keep you posted as it moves through triage.\n\n"
        "— RunMyCampus\n"
    )
    _send_quiet(
        subject=f"Feedback update: {instance.title[:80]}",
        body=body,
        recipients=[user.email],
    )
