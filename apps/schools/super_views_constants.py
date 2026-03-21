"""
Shared exception tuples for super admin / control-plane views (BR-12 split).

Used by super_views, super_views_command_center_data, and related modules.
"""

from django.core.exceptions import ValidationError
from django.db import DatabaseError

# Narrow catches for metrics / dashboard aggregation (no bare Exception).
CONTROL_PLANE_METRIC_FAILURES = (
    AttributeError,
    DatabaseError,
    ImportError,
    LookupError,
    TypeError,
    ValueError,
)
CONTROL_PLANE_AUDIT_FAILURES = (
    AttributeError,
    DatabaseError,
    ImportError,
    LookupError,
    TypeError,
    ValidationError,
    ValueError,
)
