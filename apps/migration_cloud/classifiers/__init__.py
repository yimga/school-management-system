"""Source-system and domain classifiers — Phase U3.

Two independent classifiers, both operating on artifact profiles:

* :mod:`source` — best guess at the source system (PowerSchool, Blackbaud,
  Veracross, FACTS, Infinite Campus, Skyward, Alma, generic SIS, custom).
* :mod:`domain` — per-artifact ranking over the 23 canonical domains
  (students, guardians, attendance, grades, fees, ...).

Both return ranked candidates with confidence — never hard decisions.
The orchestrator escalates to operator review when top-1 confidence is
below the configured threshold (defaults live in
``apps.migration_cloud.defaults``).

The AI bridge is consulted only when deterministic signals don't reach
threshold; this keeps token spend tight and the pipeline fast.
"""

from __future__ import annotations

from .domain import classify_domain
from .source import classify_source

__all__ = ["classify_source", "classify_domain"]
