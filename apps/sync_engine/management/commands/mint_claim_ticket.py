"""Pre-authorise ONE box adoption, before the box exists (cloud side).

    python manage.py mint_claim_ticket --slug gilead-tech --user admin --days 14

For a scheduled install where nobody with cloud admin will be reachable while the
technician is on site. The printed ticket goes on the install sheet; the technician
runs `pair_box --claim <ticket>` and the box adopts itself with no approval step.

A ticket is NOT a credential. It buys exactly one auto-approved pairing for one named
school, it is spent the first time it is used, and every later attempt to use it is
counted and logged as an intrusion signal -- because the real box redeems once and
never again. That alarm is the property a long-lived RMC_EDGE_CREDENTIAL sitting in a
.env file can never give you.
"""
from __future__ import annotations

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError


def _refusal_text(result: dict, *, user, school) -> str:
    """Why the mint was refused, in the words the SERVICE chose.

    ``pairing_service.mint_claim_ticket`` does not return a bare code. When
    ``adoption_conflict`` refuses -- the one-box-per-school case, and the refusal an
    operator is most likely to meet here -- it returns a written sentence under
    ``message`` that names the release action (revoke the bound device), plus the
    device ids that are holding the school. All of that was being discarded and the
    technician saw ``Could not mint: school_already_paired``: a status with no reason,
    which is exactly the "diagnosis four days late" failure this pairing design exists
    to remove.

    So: the service's own message wins, a written line per known code is the fallback,
    and the code is always named so the message can still be grepped for. A refusal is
    never printed as a code alone.
    """
    code = str(result.get("error") or "unknown_error")
    detail = str(result.get("message") or "").strip() or {
        "forbidden": f"{user.username} does not administer {school.slug} and is not staff.",
        "school_required": "No school resolved.",
    }.get(code, "")
    bound = [str(d) for d in (result.get("bound_device_ids") or []) if str(d).strip()]
    parts = [f"Could not mint a claim ticket for {school.slug} ({code})."]
    if detail:
        parts.append(detail)
    if bound:
        parts.append(f"Bound device id(s): {', '.join(bound)}.")
    return " ".join(parts)


class Command(BaseCommand):
    help = "Mint a single-use claim ticket that pre-authorises one box adoption."

    def add_arguments(self, parser):
        parser.add_argument("--slug", required=True, help="School slug.")
        parser.add_argument("--user", required=True, help="Username minting the ticket (must administer the school, or be staff).")
        parser.add_argument("--days", type=int, default=14, help="Ticket lifetime (default 14).")
        parser.add_argument("--label", default="", help="Note shown to whoever reviews tickets later.")

    def handle(self, *args, **options):
        from apps.schools.models import School
        from apps.sync_engine.pairing_service import mint_claim_ticket

        school = School.objects.filter(slug=options["slug"].strip()).first()
        if school is None:
            raise CommandError(f"No school with slug {options['slug']!r}.")
        user = get_user_model().objects.filter(username=options["user"].strip()).first()
        if user is None:
            raise CommandError(f"No user named {options['user']!r}.")

        result = mint_claim_ticket(
            school=school, minted_by=user, days=int(options["days"]), label=options["label"]
        )
        if not result.get("ok"):
            raise CommandError(_refusal_text(result, user=user, school=school))

        self.stdout.write(self.style.SUCCESS(
            f"Claim ticket for {school.slug}, expires {result['expires_at']}."
        ))
        self.stdout.write("")
        self.stdout.write("Ticket (shown ONCE — single use):")
        self.stdout.write(result["ticket"])
        self.stdout.write("")
        self.stdout.write("On the box:  python manage.py pair_box --claim <ticket> --wait")
