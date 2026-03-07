# FAQ and Knowledge Base System - Implementation Guide

## Overview
A comprehensive FAQ and Knowledge Base system has been developed for the school management platform with support for user contributions, moderation workflow, and rich content management.

## Features Implemented

### 1. Database Models (`apps/portal/models_kb.py`)

#### FAQCategory
- Category organization for FAQs
- Customizable icons and ordering
- Active/inactive status

#### FAQ
- Questions and answers (text + HTML formats)
- User contribution tracking
- Status workflow: DRAFT → PENDING → APPROVED/REJECTED → ARCHIVED
- Engagement metrics: view count, helpful/unhelpful votes
- Featured FAQs support
- Tagging for search
- Moderation workflow with reviewer tracking

#### KBCategory
- Hierarchical category system (parent-child)
- Icon and description support
- Slug-based URLs

#### KBArticle
- Full-featured knowledge base articles
- Rich content with HTML support
- Difficulty levels: BEGINNER, INTERMEDIATE, ADVANCED
- Estimated read time
- Multiple authors/contributors
- Related articles linking
- Status: DRAFT → PENDING → PUBLISHED → UPDATED → ARCHIVED
- Engagement metrics
- Featured articles support

#### KBArticleAttachment
- Screenshot and file attachments
- File type and size tracking
- Captions and display ordering
- Upload tracking

#### KBComment
- Threaded comments on articles
- Moderation workflow
- "Helpful" marking by moderators
- Reply support

#### UserContribution
- Gamification tracking
- Point system for contributions:
  - FAQ Submit: 5 points
  - FAQ Approved: Bonus points
  - Article Submit: 20 points
  - Article Approved: Bonus points
  - Comment: 1 point
  - Helpful Vote: Points to original author

### 2. Admin Interfaces (`apps/portal/admin_kb.py`)

All models have full Django admin support with:
- List views with filtering and search
- Bulk actions for approval/rejection
- Inline editing where appropriate
- Read-only fields for metrics
- Custom actions:
  - Approve/reject FAQs and articles
  - Feature content
  - Publish/archive articles
  - Mark comments as helpful

### 3. Views and URLs (`apps/portal/views_kb.py`, `apps/portal/urls_kb.py`)

#### Public Views
- `faq_list`: Browse FAQs by category with search
- `faq_detail`: View single FAQ with related questions
- `kb_home`: Knowledge base homepage with featured/recent/popular articles
- `kb_category`: Browse articles by category
- `kb_article`: View full article with comments
- `kb_search`: Unified search across FAQs and articles

#### User Contribution Views
- `faq_submit`: Submit new FAQ (requires login)
- `kb_article_submit`: Submit new KB article (requires login)
- `kb_comment_add`: Add comment to article (requires login)
- `user_contributions`: View personal contribution history and points

#### AJAX Views
- `faq_vote`: Vote on FAQ helpfulness
- `kb_article_vote`: Vote on article helpfulness

### 4. Initial Content (`apps/portal/management/commands/seed_faqs.py`)

Management command to populate database with **40+ comprehensive FAQs** covering:

1. **Getting Started** (4 FAQs)
   - Login and authentication
   - User roles and permissions
   - Dashboard navigation
   - Browser compatibility

2. **Student Management** (4 FAQs)
   - Adding students
   - Admission number format
   - Bulk import
   - Parent linking

3. **Grading & Evaluations** (5 FAQs)
   - Entering grades
   - Assessment weights
   - Grade import
   - Ranking calculation
   - Grading deadlines

4. **Report Cards** (3 FAQs)
   - Generating reports
   - Customization
   - Publishing to parents

5. **Finance & Fees** (4 FAQs)
   - Fee structure setup
   - Payment methods
   - Online payments
   - Installment plans

6. **Parent Portal** (3 FAQs)
   - Access and login
   - Available features
   - Multiple children linking

7. **Teachers & Staff** (3 FAQs)
   - Teaching schedule
   - Leave requests
   - Paystubs

8. **Communication** (2 FAQs)
   - Messaging parents
   - Virtual classrooms

9. **System Settings** (2 FAQs)
   - Branding customization
   - Academic year/term setup

10. **Troubleshooting** (4 FAQs)
    - Password reset
    - Permission issues
    - Performance problems
    - Grade corrections

## Installation Steps

### 1. Run Migrations
```bash
python manage.py makemigrations portal
python manage.py migrate
```

### 2. Update Apps Configuration
Add to `apps/portal/admin.py`:
```python
from .admin_kb import *
```

### 3. Update URL Configuration
Add to `config/urls.py`:
```python
from django.urls import path, include

urlpatterns = [
    # ... existing patterns ...
    path('kb/', include('apps.portal.urls_kb')),
]
```

### 4. Seed Initial Data
```bash
python manage.py seed_faqs
```

### 5. Create KB Articles Management Command (Next Step)
The knowledge base article seeding command should be created to populate detailed how-to guides.

## Templates Needed

Create these templates in `templates/portal/`:

1. **faq_list.html** - FAQ listing with categories
2. **faq_detail.html** - Single FAQ view with voting
3. **faq_submit.html** - User FAQ submission form
4. **kb_home.html** - KB homepage with featured articles
5. **kb_category.html** - Articles in category
6. **kb_article.html** - Full article view with comments
7. **kb_article_submit.html** - User article submission form
8. **kb_search.html** - Search results
9. **user_contributions.html** - User's contribution dashboard

## Screenshot Placeholders

KB articles support attachments with these features:
- Upload path: `media/kb/attachments/YYYY/MM/`
- Automatic file size tracking
- File type detection
- Display ordering
- Caption support
- Screenshot flag

Administrators can upload screenshots through:
1. Django admin: KB Articles → [Article] → Attachments (inline)
2. Or directly via KBArticleAttachment admin

## User Contribution Workflow

### For Users:
1. Submit FAQ or article
2. Status set to "PENDING"
3. Earn points immediately
4. Receive notification when approved/rejected

### For Moderators:
1. Review submissions in Django admin
2. Approve good content → Status: APPROVED/PUBLISHED
3. Reject poor quality → Status: REJECTED (with reason)
4. Edit if needed before approval
5. Feature high-quality content

### Point System:
- FAQ Submit: 5 points
- Article Submit: 20 points
- Comment: 1 point
- Helpful Vote: 1-2 points to author
- Bonuses awarded when content approved

## Next Steps

1. **Create Templates**: Build responsive HTML templates for all views
2. **Seed KB Articles**: Create management command with detailed how-to articles
3. **Add Screenshots**: Upload screenshots for KB articles
4. **Test Workflows**: Test submission, approval, and publishing workflows
5. **Email Notifications**: Add email notifications for approvals/rejections
6. **Search Optimization**: Add full-text search indexing
7. **Analytics**: Track which FAQs/articles are most helpful
8. **Mobile App Integration**: Expose FAQ/KB via mobile API

## URLs

Once deployed, access via:
- FAQs: `/kb/faq/`
- Knowledge Base: `/kb/`
- Search: `/kb/search/`
- Submit FAQ: `/kb/faq/submit/`
- Submit Article: `/kb/article/submit/`
- My Contributions: `/kb/my-contributions/`

## Admin Access

Access via Django admin:
- `/admin/portal/faqcategory/`
- `/admin/portal/faq/`
- `/admin/portal/kbcategory/`
- `/admin/portal/kbarticle/`
- `/admin/portal/kbarticleattachment/`
- `/admin/portal/kbcomment/`
- `/admin/portal/usercontribution/`

## Security Features

- User contributions require login
- Moderation workflow prevents spam
- Admin approval required for publishing
- Audit trails track all changes
- Comment moderation
- Vote tracking to prevent abuse

## Extensibility

The system is designed to be flexible:
- Add new FAQ categories easily
- Create custom KB categories with hierarchy
- Tag system for organization
- Related articles for cross-referencing
- Multiple authors/contributors support
- Rich HTML content support
- File attachments for any media type

## Success Metrics

Track these metrics to measure success:
- View counts per FAQ/article
- Helpful vote percentages
- User contribution rates
- Search query analysis
- Most popular topics
- User engagement time
- Conversion rate (how many users find answers)
