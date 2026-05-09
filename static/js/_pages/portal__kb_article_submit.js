// File upload handling
const uploadArea = document.getElementById('uploadArea');
const fileInput = document.getElementById('fileInput');

uploadArea.addEventListener('click', () => fileInput.click());

uploadArea.addEventListener('dragover', (e) => {
    e.preventDefault();
    uploadArea.classList.add('dragover');
});

uploadArea.addEventListener('dragleave', () => {
    uploadArea.classList.remove('dragover');
});

uploadArea.addEventListener('drop', (e) => {
    e.preventDefault();
    uploadArea.classList.remove('dragover');
    fileInput.files = e.dataTransfer.files;
    updateFileList();
});

fileInput.addEventListener('change', updateFileList);

function updateFileList() {
    const fileList = document.getElementById('fileList');
    fileList.innerHTML = '';
    
    Array.from(fileInput.files).forEach((file, index) => {
        const item = document.createElement('div');
        item.className = 'alert alert-light mb-2';
        item.innerHTML = `
            <i class="fas fa-file"></i> ${file.name} (${formatFileSize(file.size)})
            <button type="button" class="btn btn-sm btn-outline-danger float-right" onclick="removeFile(${index})">
                <i class="fas fa-trash"></i>
            </button>
        `;
        fileList.appendChild(item);
    });
}

function removeFile(index) {
    const dt = new DataTransfer();
    Array.from(fileInput.files).forEach((file, i) => {
        if (i !== index) dt.items.add(file);
    });
    fileInput.files = dt.files;
    updateFileList();
}

function formatFileSize(bytes) {
    if (bytes === 0) return '0 Bytes';
    const k = 1024;
    const sizes = ['Bytes', 'KB', 'MB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return Math.round(bytes / Math.pow(k, i) * 100) / 100 + ' ' + sizes[i];
}

var DRAFT_KEY = 'kb_article_draft';
function saveDraft() {
    var titleEl = document.querySelector('[name="title"]');
    var summaryEl = document.querySelector('[name="summary"]');
    var contentEl = document.querySelector('[name="content"]');
    var categoryEl = document.querySelector('[name="category"]');
    var draft = {
        title: titleEl ? titleEl.value : '',
        summary: summaryEl ? summaryEl.value : '',
        content: contentEl ? contentEl.value : '',
        category: categoryEl ? categoryEl.value : ''
    };
    try {
        localStorage.setItem(DRAFT_KEY, JSON.stringify(draft));
        alert('Draft saved locally! Your article is not yet submitted.');
    } catch (e) {
        alert('Could not save draft (storage full or disabled).');
    }
}
function restoreDraft() {
    try {
        var raw = localStorage.getItem(DRAFT_KEY);
        if (!raw) return;
        var draft = JSON.parse(raw);
        var titleEl = document.querySelector('[name="title"]');
        var summaryEl = document.querySelector('[name="summary"]');
        var contentEl = document.querySelector('[name="content"]');
        var categoryEl = document.querySelector('[name="category"]');
        if (draft.title && titleEl) titleEl.value = draft.title;
        if (draft.summary && summaryEl) summaryEl.value = draft.summary;
        if (draft.content && contentEl) contentEl.value = draft.content;
        if (draft.category && categoryEl) categoryEl.value = draft.category;
    } catch (e) {}
}
document.addEventListener('DOMContentLoaded', restoreDraft);
