"""
Phase 10 — 10.4: Document Library lifecycle states (stub).
Use these constants when adding a state field to document/folder models or filters.
Lifecycle: DRAFT → PUBLISHED → optional ARCHIVED / RETRACTED.
"""
from django.utils.translation import gettext_lazy as _

# Lifecycle states for document library items (future: add to PortalFeatureItem or document model).
DOCUMENT_LIFECYCLE_DRAFT = "draft"
DOCUMENT_LIFECYCLE_PUBLISHED = "published"
DOCUMENT_LIFECYCLE_ARCHIVED = "archived"
DOCUMENT_LIFECYCLE_RETRACTED = "retracted"

DOCUMENT_LIFECYCLE_CHOICES = [
    (DOCUMENT_LIFECYCLE_DRAFT, _("Draft")),
    (DOCUMENT_LIFECYCLE_PUBLISHED, _("Published")),
    (DOCUMENT_LIFECYCLE_ARCHIVED, _("Archived")),
    (DOCUMENT_LIFECYCLE_RETRACTED, _("Retracted")),
]

DOCUMENT_LIFECYCLE_VALID_TRANSITIONS = {
    DOCUMENT_LIFECYCLE_DRAFT: (DOCUMENT_LIFECYCLE_PUBLISHED,),
    DOCUMENT_LIFECYCLE_PUBLISHED: (DOCUMENT_LIFECYCLE_ARCHIVED, DOCUMENT_LIFECYCLE_RETRACTED),
    DOCUMENT_LIFECYCLE_ARCHIVED: (DOCUMENT_LIFECYCLE_PUBLISHED,),
    DOCUMENT_LIFECYCLE_RETRACTED: (),  # No transition out of retracted
}
