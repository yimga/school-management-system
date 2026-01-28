# Importing Documentation into Knowledge Base

## Overview

This guide explains how to import documentation files from the `docs/` directory into the Knowledge Base (KB) system, making them accessible to users through the portal.

## Quick Start

### 1. Import All Documentation

```bash
python manage.py import_docs_to_kb
```

This will:
- Read all `.md` files from the `docs/` directory
- Convert them to KB articles
- Organize them into appropriate categories
- Skip files that are already in KB format or developer-only docs

### 2. Import to Specific Category

```bash
python manage.py import_docs_to_kb --category student-management
```

### 3. Dry Run (Preview)

```bash
python manage.py import_docs_to_kb --dry-run
```

This shows what would be imported without actually creating articles.

### 4. Overwrite Existing Articles

```bash
python manage.py import_docs_to_kb --overwrite
```

This updates existing articles with the same slug.

## How It Works

### File Organization

The command automatically maps documentation files to KB categories:

- **Student Management**: Admission guides, student management docs
- **Getting Started**: Onboarding, testing checklists, setup guides
- **System Administration**: Customization, configuration, admin guides
- **Finance**: Payment guides, payroll documentation
- **Reports**: Report generation and localization guides
- **Communication**: UX guides, communication features

### What Gets Imported

✅ **Imported**:
- User-facing guides (e.g., `ADMISSION_NUMBER_GUIDE.md`)
- Configuration guides (e.g., `customization.md`)
- Feature documentation (e.g., `finance-payments.md`)

❌ **Skipped**:
- Files starting with `KB_` (already in KB format)
- Implementation guides (for developers)
- Roadmaps and completion reports
- Testing checklists (internal use)
- Analysis documents

### Article Structure

Each imported article includes:
- **Title**: Extracted from first H1 or filename
- **Summary**: First paragraph or description
- **Content**: Original markdown (preserved)
- **Content HTML**: Converted and sanitized HTML
- **Category**: Automatically assigned based on file mapping
- **Difficulty**: BEGINNER, INTERMEDIATE, or ADVANCED
- **Tags**: Relevant keywords for search
- **Status**: PUBLISHED (ready to view)

## Customizing the Import

### Adding New File Mappings

Edit `apps/portal/management/commands/import_docs_to_kb.py`:

```python
def _get_doc_mapping(self):
    return {
        'YOUR_FILE.md': {
            'category': 'student-management',
            'difficulty': 'INTERMEDIATE',
            'tags': 'your, tags, here',
            'icon': 'fa-icon-name',
            'order': 1,
        },
        # ... existing mappings
    }
```

### Creating New Categories

Categories are created automatically if they don't exist. To pre-create:

1. Go to `/admin/portal/kbcategory/`
2. Create category with desired slug
3. Run import command with `--category your-slug`

## Viewing Imported Articles

After import, articles are available at:
- **KB Home**: `/kb/` or `/portal/kb/`
- **By Category**: `/kb/category/your-category/`
- **Individual Article**: `/kb/article/article-slug/`

## Markdown Conversion

The command converts markdown to HTML using:

1. **If `markdown` library is installed**: Full markdown conversion with extensions
   - Code highlighting
   - Tables
   - Fenced code blocks
   - Lists and formatting

2. **If `markdown` library is not available**: Simple conversion
   - Headers, bold, italic
   - Code blocks
   - Links
   - Basic lists

**Recommendation**: Install markdown for better formatting:
```bash
pip install markdown
```

## HTML Sanitization

All HTML content is sanitized using the KB sanitizer to:
- Remove unsafe tags and attributes
- Prevent XSS attacks
- Ensure only allowed HTML elements remain

Allowed tags include: headings, paragraphs, lists, links, code blocks, and basic formatting.

## Troubleshooting

### "No articles imported"

**Check**:
1. Files exist in `docs/` directory
2. Files are `.md` format
3. Files aren't in skip list (KB_*, IMPLEMENTATION_GUIDE, etc.)

### "Article already exists"

**Solution**: Use `--overwrite` flag to update existing articles

### "Markdown conversion errors"

**Solution**: 
- Install markdown library: `pip install markdown`
- Or check markdown syntax in source files

### "Category not found"

**Solution**: Category is created automatically. Check slug spelling.

## Best Practices

1. **Keep Documentation Updated**: Re-run import after updating docs
2. **Use Descriptive Filenames**: They become article slugs
3. **Add H1 Headers**: First `# Title` becomes article title
4. **Write Clear Summaries**: First paragraph should be descriptive
5. **Tag Appropriately**: Add relevant tags for searchability

## Manual Article Creation

For articles that need special handling:

1. Go to `/admin/portal/kbarticle/add/`
2. Fill in article details
3. Paste markdown in "Content" field
4. HTML is auto-generated on save
5. Set status to "PUBLISHED"

## Related Documentation

- [KB Implementation Guide](./FAQ_KB_IMPLEMENTATION_GUIDE.md) - KB system overview
- [Admission Number Guide](./ADMISSION_NUMBER_GUIDE.md) - Example imported article
