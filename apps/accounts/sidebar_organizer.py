"""
Sidebar Organization Helper
Organizes sidebar items into logical categories for better UX
"""

from typing import Dict, List, Optional
from apps.accounts.models import User


def organize_sidebar_items(items: List[Dict], user: User) -> Dict[str, List[Dict]]:
    """
    Organize sidebar items into logical categories.
    
    Returns:
        {
            "quick_actions": [...],
            "people": [...],
            "academic": [...],
            "reports": [...],
            "communication": [...],
            "settings": [...],
        }
    """
    organized = {
        "quick_actions": [],
        "people": [],
        "academic": [],
        "reports": [],
        "communication": [],
        "settings": [],
    }
    
    # Category mappings
    quick_action_ids = {"backend", "workflow", "portal"}
    people_ids = {"students", "teachers", "parents", "guardians"}
    academic_ids = {"classrooms", "subjects", "years", "terms", "certification"}
    reports_ids = {"reports", "report_builder", "report_library", "bulk_letters", "analytics"}
    communication_ids = {"messages", "notifications", "groups", "announcements"}
    settings_ids = {"preferences", "admin", "kb", "documents", "signatures"}
    
    for item in items:
        item_id = item.get("id", "").lower()
        
        if item_id in quick_action_ids:
            organized["quick_actions"].append(item)
        elif item_id in people_ids:
            organized["people"].append(item)
        elif item_id in academic_ids:
            organized["academic"].append(item)
        elif item_id in reports_ids:
            organized["reports"].append(item)
        elif item_id in communication_ids:
            organized["communication"].append(item)
        elif item_id in settings_ids:
            organized["settings"].append(item)
        else:
            # Default to settings if unknown
            organized["settings"].append(item)
    
    # Remove empty categories
    return {k: v for k, v in organized.items() if v}


def get_sidebar_category_labels() -> Dict[str, str]:
    """Get display labels for sidebar categories"""
    return {
        "quick_actions": "Quick Actions",
        "people": "People Management",
        "academic": "Academic Management",
        "reports": "Reports & Analytics",
        "communication": "Communication",
        "settings": "Settings & Tools",
    }
