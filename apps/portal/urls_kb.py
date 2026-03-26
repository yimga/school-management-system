"""
URL patterns for FAQ and Knowledge Base
"""

from django.urls import path
from . import views_kb, views_office

app_name = "kb"

urlpatterns = [
    # FAQ URLs
    path("faq/", views_kb.faq_list, name="faq_list"),
    path("faq/<int:faq_id>/", views_kb.faq_detail, name="faq_detail"),
    path("faq/<int:faq_id>/vote/", views_kb.faq_vote, name="faq_vote"),
    path("faq/submit/", views_kb.faq_submit, name="faq_submit"),
    # Knowledge Base URLs
    path("", views_kb.kb_home, name="kb_home"),
    path("category/<slug:category_slug>/", views_kb.kb_category, name="kb_category"),
    path("article/<slug:article_slug>/", views_kb.kb_article, name="kb_article"),
    path(
        "article/<slug:article_slug>/download-odt/",
        views_kb.kb_article_download_odt,
        name="kb_article_download_odt",
    ),
    path(
        "article/<slug:article_slug>/download-docx/",
        views_kb.kb_article_download_docx,
        name="kb_article_download_docx",
    ),
    path(
        "article/<slug:article_slug>/download-pdf/",
        views_kb.kb_article_download_pdf,
        name="kb_article_download_pdf",
    ),
    path(
        "article/<slug:article_slug>/vote/",
        views_kb.kb_article_vote,
        name="kb_article_vote",
    ),
    path(
        "article/<slug:article_slug>/comment/",
        views_kb.kb_comment_add,
        name="kb_comment_add",
    ),
    path("article/submit/", views_kb.kb_article_submit, name="kb_article_submit"),

    # Office docs / Collabora (T4)
    path("office/", views_office.office_document_list, name="office_document_list"),
    path(
        "office/<int:document_id>/open/",
        views_office.office_document_open,
        name="office_document_open",
    ),
    path(
        "wopi/files/<int:document_id>",
        views_office.wopi_check_file_info,
        name="wopi_check_file_info",
    ),
    path(
        "wopi/files/<int:document_id>/contents",
        views_office.wopi_file_contents,
        name="wopi_file_contents",
    ),
    # Search
    path("search/", views_kb.kb_search, name="kb_search"),
    # User contributions
    path("my-contributions/", views_kb.user_contributions, name="user_contributions"),
]
