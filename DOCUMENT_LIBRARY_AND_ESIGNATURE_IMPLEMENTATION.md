# Document Library & E-Signature Implementation

## Summary

Implemented comprehensive document management system with file uploads and electronic signature capabilities for school forms.

---

## ✅ What Was Implemented

### 1. Enhanced Document Library Model (`apps/portal/models.py`)

**Added to `PortalFeatureItem`:**
- ✅ **File upload field** - `FileField` for uploading PDF, Word, Excel documents (max 10MB)
- ✅ **Document type** - Categories: General, Form, Policy, Handbook, Timetable, Announcement, Other
- ✅ **Requires signature flag** - Mark forms that need electronic signatures
- ✅ **Access control** - `visible_to_roles` JSONField to control who can see documents
- ✅ **File metadata** - Properties for file size, extension, etc.

**New Model: `FormSignature`**
- ✅ Tracks electronic signatures for forms
- ✅ Links form document, student, and parent
- ✅ Stores signature data, hash, IP, user agent for audit trail
- ✅ Supports expiry dates and reminders
- ✅ Status tracking: PENDING, SIGNED, REJECTED, EXPIRED

### 2. Admin Interface (`apps/portal/admin.py`)

**Enhanced `PortalFeatureItemAdmin`:**
- ✅ Better list display with file status, document type, signature requirement
- ✅ Organized fieldsets for better UX
- ✅ File upload support in admin

**New `FormSignatureAdmin`:**
- ✅ Full admin interface for managing signature requests
- ✅ Search and filter by status, form, student, parent
- ✅ Audit trail visibility

### 3. Backend UI Views (`apps/portal/views_documents.py`)

**Document Management:**
- ✅ `document_library_manage` - List all documents with filters and search
- ✅ `document_upload` - Upload/edit documents (beautiful UI, not admin)
- ✅ `document_delete` - Delete documents with permission checks
- ✅ `document_download` - Secure file download with access control

**Signature Management:**
- ✅ `signature_requests_manage` - Admin view of all signature requests
- ✅ `signature_request_create` - Create signature requests for parents
- ✅ `signature_pending_list` - Parent view of pending signatures
- ✅ `signature_sign` - E-signature interface for parents

### 4. Forms (`apps/portal/forms_documents.py`)

**`DocumentUploadForm`:**
- ✅ File upload or external link (not both)
- ✅ Document type selection
- ✅ Signature requirement toggle
- ✅ Role-based visibility control
- ✅ Validation for file types and sizes

**`SignatureRequestForm`:**
- ✅ Select form, student, parent
- ✅ Set expiry date (default 30 days)
- ✅ Prevent duplicate requests
- ✅ Validation for signature requirements

### 5. Updated Templates

**`templates/portal/feature_page.html`:**
- ✅ Shows download button for files
- ✅ Shows "Requires Signature" badge
- ✅ Shows document type badge
- ✅ Better visual distinction between files and links

### 6. URLs (`apps/portal/urls.py`)

**Added routes:**
- `/portal/backend/documents/` - Document management
- `/portal/backend/documents/upload/` - Upload document
- `/portal/backend/documents/upload/<id>/` - Edit document
- `/portal/backend/documents/delete/<id>/` - Delete document
- `/portal/backend/documents/download/<id>/` - Download document
- `/portal/backend/signatures/` - Signature requests management
- `/portal/backend/signatures/create/` - Create signature request
- `/portal/parent/signatures/` - Parent's pending signatures
- `/portal/parent/signatures/sign/<id>/` - Sign form

### 7. Migration

✅ Created migration: `0010_add_file_upload_and_signatures.py`
- Adds file field, document_type, requires_signature, visible_to_roles
- Creates FormSignature model with all fields and indexes
- Adds proper indexes for performance

---

## 🔒 Security & Access Control

### Document Access Control
- ✅ **Role-based visibility** - Admins can restrict documents to specific roles
- ✅ **Permission checks** - Only admins can upload/manage documents
- ✅ **File validation** - Only safe document types (PDF, Word, Excel) allowed
- ✅ **Size limits** - Max 10MB per file
- ✅ **Download protection** - `can_view()` method checks permissions before download

### Signature Security
- ✅ **Audit trail** - IP address, user agent, timestamp recorded
- ✅ **Signature hash** - SHA-256 hash for verification
- ✅ **Expiry dates** - Signature requests can expire
- ✅ **Unique constraints** - Prevents duplicate signature requests
- ✅ **Permission checks** - Only parent can sign their own forms

---

## 📋 Use Cases Supported

### 1. Upload Common Documents
**Admin can upload:**
- ✅ Registration forms
- ✅ Consent forms
- ✅ Extra fee forms
- ✅ School handbook
- ✅ Timetables
- ✅ Policy documents
- ✅ Announcements

### 2. Electronic Form Signing
**Workflow:**
1. Admin uploads form (e.g., "Registration Form 2026")
2. Admin marks it as "Requires Signature"
3. Admin creates signature request for specific student + parent
4. Parent receives notification (via pending signatures list)
5. Parent views form and signs electronically
6. Signed PDF is generated and stored
7. Admin can view signed forms

### 3. Access Control
**Admin can:**
- ✅ Make documents visible to all authenticated users
- ✅ Restrict to specific roles (Admin, Teacher, Parent, Student)
- ✅ Control who sees sensitive documents

---

## 🎯 Next Steps (Templates Needed)

The following templates need to be created:

1. **`templates/portal/document_library_manage.html`**
   - List all documents
   - Filter by type, search
   - Upload/Edit/Delete buttons
   - Stats dashboard

2. **`templates/portal/document_upload.html`**
   - Form for uploading/editing documents
   - File upload widget
   - Document type selector
   - Signature requirement toggle
   - Role visibility selector

3. **`templates/portal/signature_requests_manage.html`**
   - List all signature requests
   - Filter by status
   - Create new request button
   - View signed forms

4. **`templates/portal/signature_request_create.html`**
   - Form to create signature request
   - Select form, student, parent
   - Set expiry date

5. **`templates/portal/signature_pending_list.html`**
   - Parent's view of pending signatures
   - List forms that need signing
   - Link to sign each form

6. **`templates/portal/signature_sign.html`**
   - E-signature interface
   - Show form document
   - Signature canvas/input
   - Submit signature

---

## 🔗 Integration Points

### Backend Dashboard
Add to sidebar:
```python
_item("documents", "Document Library", "portal:document_library_manage", icon="bi-file-earmark-text")
```

### Parent Dashboard
Add pending signatures widget:
- Show count of pending signatures
- Link to signature list

### Notifications
- Notify parents when signature request is created
- Remind parents of pending signatures

---

## 📊 Database Schema

### `PortalFeatureItem` (Enhanced)
- `file` - FileField (upload_to="portal/documents/%Y/%m/")
- `document_type` - CharField (choices: GENERAL, FORM, POLICY, etc.)
- `requires_signature` - BooleanField
- `visible_to_roles` - JSONField (list of role codes)

### `FormSignature` (New)
- `form_document` - ForeignKey to PortalFeatureItem
- `student` - ForeignKey to StudentProfile
- `parent` - ForeignKey to User (PARENT role)
- `status` - CharField (PENDING, SIGNED, REJECTED, EXPIRED)
- `signed_at` - DateTimeField
- `signature_data` - TextField (Base64 signature)
- `signature_hash` - CharField (SHA-256)
- `signed_pdf` - FileField (final signed document)
- `expires_at` - DateTimeField
- `signature_ip` - GenericIPAddressField
- `signature_user_agent` - CharField

---

## ✅ Migration Status

Migration created: `apps/portal/migrations/0010_add_file_upload_and_signatures.py`

**To apply:**
```bash
python manage.py migrate portal
```

---

## 🎨 UI/UX Improvements Needed

1. **Backend Document Management UI**
   - Beautiful, user-friendly interface (NOT admin UI)
   - Drag-and-drop file upload
   - Preview documents
   - Bulk operations

2. **E-Signature Interface**
   - Signature canvas (draw signature)
   - Or type signature
   - Preview before submitting
   - Mobile-friendly

3. **Parent Signature Dashboard**
   - Clear list of pending signatures
   - Visual indicators (urgent, expiring soon)
   - One-click signing

---

## 📝 Summary

✅ **File uploads** - Admins can now upload documents (not just links)  
✅ **E-signatures** - Forms can require electronic signatures  
✅ **Access control** - Role-based document visibility  
✅ **Backend UI** - Custom UI for document management (not admin)  
✅ **Security** - Proper validation, permissions, audit trail  

**What's Left:**
- Create templates for the new views
- Add signature canvas/input widget
- Add notifications for signature requests
- Add to sidebar navigation
- Test end-to-end workflow
