"""Vendor accelerators — Phase U9.

Each accelerator short-circuits the discovery + classifier + mapper layers
for a *known* source by handing the orchestrator pre-classified artifacts
with canonical mappings already attached. The orchestrator's apply step
runs identically whether the bundle came through the universal pipeline
or an accelerator.

Critical contract: **no accelerator gets its own ingest, profile, or
apply path past the entry point.** If an accelerator breaks (vendor
revokes API, schema drifts), the universal upload path is the safety net.

Accelerators implement :class:`Accelerator` and register themselves in
the module-level registry. Currently shipped:

* ``OneRosterV1p2InboundAccelerator`` — covers PowerSchool, Infinite
  Campus, Blackbaud, Veracross, FACTS, Skyward, Alma indirectly via the
  OneRoster export many districts already produce for Clever/ClassLink.
"""

from __future__ import annotations

from .base import (
    Accelerator,
    AcceleratorContract,
    AcceleratorError,
    AcceleratorRegistry,
    get_accelerator,
    register_accelerator,
)
from . import alma  # noqa: F401
from . import blackbaud  # noqa: F401
from . import facts  # noqa: F401
from . import oneroster_v1p2  # noqa: F401
from . import powerschool  # noqa: F401
from . import runmycampus_canonical  # noqa: F401  — long-tail canonical-template path
from . import skyward  # noqa: F401
from . import veracross  # noqa: F401  — side-effect registration

__all__ = [
    "Accelerator",
    "AcceleratorContract",
    "AcceleratorError",
    "AcceleratorRegistry",
    "get_accelerator",
    "register_accelerator",
]
