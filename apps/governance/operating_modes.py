"""Registry for school governance operating modes (Phase 2A)."""

from django.db import models


class GovernanceOperatingMode(models.TextChoices):
    """How a tenant relates to an optional Organization overlay."""

    STANDALONE = "standalone", "Standalone (no group membership)"
    GROUP_MEMBER = "group_member", "Group member (inherits per governance_inherit map)"
    GROUP_MEMBER_SOVEREIGN = (
        "group_member_sovereign",
        "Group member with local sovereignty (opt-in inheritance only)",
    )


DEFAULT_GOVERNANCE_OPERATING_MODE = GovernanceOperatingMode.STANDALONE
