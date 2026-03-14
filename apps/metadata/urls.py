from django.urls import path
from .views import (
    metadata_governance_ui,
    metadata_lineage_api,
    metadata_lineage_graph_ui,
    metadata_search_api,
)

app_name = "metadata"

urlpatterns = [
    path("search/", metadata_search_api, name="metadata_search"),
    path("governance/", metadata_governance_ui, name="metadata_governance"),
    path("lineage/", metadata_lineage_api, name="metadata_lineage"),
    path("lineage/graph/", metadata_lineage_graph_ui, name="metadata_lineage_graph"),
]
