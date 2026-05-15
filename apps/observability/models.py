"""
Observability ORM models.

The concrete model classes are defined in ``monitoring.py`` because that module
also contains health-monitoring services and endpoints. Importing them here
registers the models under the app label so migrations can detect them.
"""

from .monitoring import (  # noqa: F401
    AnomalyDetection,
    HealthCheckAlert,
    PerformanceTrace,
    PlatformIncident,
    SystemHealthMetric,
)
from .models_friction import FrictionEvent  # noqa: F401
