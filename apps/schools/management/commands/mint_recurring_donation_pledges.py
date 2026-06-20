from django.core.management.base import BaseCommand

from apps.schools.recurring_giving_services import mint_due_recurring_pledges


class Command(BaseCommand):
    help = (
        "Mint DonationPledges for due recurring giving schedules. The platform has no "
        "card-on-file auto-charge, so recurring giving produces expected-gift pledges."
    )

    def handle(self, *args, **options):
        result = mint_due_recurring_pledges()
        self.stdout.write(
            self.style.SUCCESS(
                f"Recurring giving: minted {result.get('minted', 0)} pledge(s)."
            )
        )
