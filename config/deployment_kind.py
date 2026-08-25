"""Is this process a school's own appliance, or the cloud?

Pure and dependency-free on purpose: ``config/settings.py`` calls it while it is
still being defined, so it can import nothing from Django and touch nothing that
needs settings to exist. That also makes it directly testable, which the previous
shape was not -- the answer was computed inline in settings, so the only way to
exercise it was to reload the settings module, which trips the production secret
guards and mutates global state for every test that runs afterwards.
"""

from __future__ import annotations

from typing import Mapping

TRUTHY = frozenset({"1", "true", "yes", "on"})

#: The label the selfhost compose file puts on every box, without anyone setting it.
SELFHOST_LABEL = "selfhost"


def selfhost_box_from_env(
    environ: Mapping[str, str],
    is_cloud_deployed: bool,
) -> bool:
    """True when this process is a sovereign single-school box.

    Derived from every marker a box actually carries rather than from one env var
    somebody has to remember. The previous answer was ``SINGLE_TENANT`` alone, and
    that was fail-OPEN: a box whose .env omitted it was served ``config.urls``, the
    developer urlconf, which mounts the operator control plane. A school then saw
    operator chrome and a page offering to request access INTO that control plane,
    on their own appliance, after logging in with their own credentials.

    ``is_cloud_deployed`` wins outright and is checked first. The flag can leak into
    a hosted environment -- copied into a shared .env, inherited from a template,
    set while debugging -- and a cloud process that believed it was a single-school
    appliance would serve every operator the wrong surface entirely.
    """
    if is_cloud_deployed:
        return False
    label = str(environ.get("ENVIRONMENT", "") or "").strip().lower()
    if label == SELFHOST_LABEL:
        return True
    return str(environ.get("SINGLE_TENANT", "") or "").strip().lower() in TRUTHY
