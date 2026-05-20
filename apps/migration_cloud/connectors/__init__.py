"""Migration Cloud source-platform connectors."""

from .base import ConnectorAdapter, get_connector, list_connectors
from .registry import bootstrap_connectors

bootstrap_connectors()

__all__ = [
    "ConnectorAdapter",
    "get_connector",
    "list_connectors",
    "bootstrap_connectors",
]
