"""
Metadata Catalog domain (plan Workstream B — seven bounded domains).
Siteconfig’s dynamic field definitions/values (canonical catalog lives in apps.metadata).
Re-exports from .models. Import from here for new code when touching siteconfig-owned metadata.
"""
from .models import DynamicFieldDefinition, DynamicFieldValue

__all__ = ["DynamicFieldDefinition", "DynamicFieldValue"]
