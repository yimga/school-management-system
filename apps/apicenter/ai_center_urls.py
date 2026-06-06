"""Super-operator AI Center URLconf (mounted under /super/ai-center/)."""

from django.urls import path

from . import views_ai_center_super as views

urlpatterns = [
    path("", views.ai_center_home, name="ai_center_home"),
    path("inventory/", views.ai_center_inventory, name="ai_center_inventory"),
    path("kb-drafts/", views.ai_center_kb_drafts, name="ai_center_kb_drafts"),
    path("friction/", views.ai_center_friction, name="ai_center_friction"),
    path("settings/", views.ai_center_settings, name="ai_center_settings"),
    path("query/", views.ai_center_query, name="ai_center_query"),
    path("generate-kb/", views.ai_center_generate_kb, name="ai_center_generate_kb"),
    path("faq-candidates/", views.ai_center_faq_candidates, name="ai_center_faq_candidates"),
    path("kb-tools/", views.ai_center_kb_tools, name="ai_center_kb_tools"),
    path("agentic/", views.ai_center_agentic, name="ai_center_agentic"),
    path("agentic/destructive/", views.ai_center_destructive, name="ai_center_destructive"),
]
