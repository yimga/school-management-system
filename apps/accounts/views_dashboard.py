"""
Backend dashboard and status fragment.
Dashboard context and recommendation logic live in apps.dashboard.context and recommendation_service.
Re-exports from .views for URL wiring; implementations remain in views.py for now to avoid a large move.
"""

from .views import backend_dashboard, backend_dashboard_status_fragment

__all__ = ["backend_dashboard", "backend_dashboard_status_fragment"]
