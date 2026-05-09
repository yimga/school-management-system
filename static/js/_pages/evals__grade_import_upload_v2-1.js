(function(){
  var pageDataEl=document.getElementById("page-data-evals__grade_import_upload_v2-1");
  window.__RMC_PAGE_DATA__=window.__RMC_PAGE_DATA__||{};
  if(pageDataEl){try{window.__RMC_PAGE_DATA__["evals__grade_import_upload_v2-1"]=JSON.parse(pageDataEl.textContent||"{}")}catch(_e){}}
let currentFile = null;
let validationData = null;

// Initialize Dropzone
Dropzone.options.gradeImportDropzone = {
    maxFilesize: 50, // MB
    acceptedFiles: '.csv',
    uploadMultiple: false,
    autoProcessQueue: true,
    init: function() {
        this.on('sending', function(file, xhr, formData) {
            document.querySelector('.progress-wrapper').style.display = 'block';
        });
        
        this.on('uploadprogress', function(file, progress) {
            document.getElementById('uploadProgress').style.width = progress + '%';
            document.getElementById('uploadProgressText').textContent = Math.round(progress) + '%';
        });
        
        this.on('success', function(file, response) {
            currentFile = file;
            validationData = response;
            displayValidationResults(response);
        });
        
        this.on('error', function(file, errorMessage) {
            showError('Upload Error: ' + errorMessage);
        });
    }
};

function displayValidationResults(data) {
    // Update summary counts
    document.getElementById('totalRowsCount').textContent = data.total_rows;
    document.getElementById('validRowsCount').textContent = data.valid_rows;
    document.getElementById('invalidRowsCount').textContent = data.invalid_rows;
    document.getElementById('warningRowsCount').textContent = data.total_rows - data.valid_rows - data.invalid_rows;
    
    // Display file errors
    if (data.file_errors && data.file_errors.length > 0) {
        const errorContainer = document.getElementById('fileErrorsContainer');
        errorContainer.innerHTML = '<div class="alert alert-danger"><strong>File Errors:</strong><ul class="mb-0 mt-2">' +
            data.file_errors.map(e => '<li>' + e + '</li>').join('') + '</ul></div>';
    }
    
    // Populate validation table
    const tbody = document.getElementById('validationTableBody');
    tbody.innerHTML = '';
    data.preview.forEach((row, idx) => {
        const tr = document.createElement('tr');
        tr.className = row.is_valid ? 'success-row' : row.errors.length > 0 ? 'error-row' : 'warning-row';
        
        const issues = [];
        if (row.errors.length > 0) issues.push(...row.errors);
        if (row.warnings.length > 0) issues.push(...row.warnings.map(w => '⚠ ' + w));
        
        tr.innerHTML = `
            <td><strong>${idx + 2}</strong></td>
            <td>${row.student_code}</td>
            <td>${row.subject_assignment_id}</td>
            <td>
                <small>
                    Seq1: ${row.seq1} | Seq2: ${row.seq2} | Exam: ${row.exam}
                </small>
            </td>
            <td>
                ${row.is_valid ? '<span class="badge badge-success">✓ Valid</span>' : 
                  row.errors.length > 0 ? '<span class="badge badge-danger">✗ Error</span>' : 
                  '<span class="badge badge-warning">⚠ Warning</span>'}
            </td>
            <td>
                ${issues.length > 0 ? '<small>' + issues.join('<br>') + '</small>' : '-'}
            </td>
        `;
        tbody.appendChild(tr);
    });
    
    // Move to validation step
    document.getElementById('uploadStep').style.display = 'none';
    document.getElementById('validationStep').style.display = 'block';
    document.getElementById('step1').classList.remove('active');
    document.getElementById('step1').classList.add('completed');
    document.getElementById('step2').classList.add('active');
    
    // Disable proceed if all invalid
    if (data.valid_rows === 0) {
        document.getElementById('proceedButton').disabled = true;
        document.getElementById('proceedButton').title = 'Cannot proceed: no valid rows';
    }
}

function moveToStep3() {
    // Calculate review summary
    const validRows = validationData.preview.filter(r => r.is_valid).length;
    document.getElementById('reviewCreatedCount').textContent = validRows;
    document.getElementById('reviewUpdatedCount').textContent = 0;
    document.getElementById('reviewIgnoredCount').textContent = validationData.total_rows - validRows;
    
    document.getElementById('validationStep').style.display = 'none';
    document.getElementById('reviewStep').style.display = 'block';
    document.getElementById('step2').classList.remove('active');
    document.getElementById('step2').classList.add('completed');
    document.getElementById('step3').classList.add('active');
}

function backToValidation() {
    document.getElementById('reviewStep').style.display = 'none';
    document.getElementById('validationStep').style.display = 'block';
    document.getElementById('step3').classList.remove('active');
    document.getElementById('step2').classList.remove('completed');
    document.getElementById('step2').classList.add('active');
}

function applyImport() {
    // Filter valid rows only
    const validRows = validationData.preview.filter(r => r.is_valid);
    if (validRows.length === 0) {
        showError('No valid rows to import');
        return;
    }
    
    document.getElementById('reviewStep').style.display = 'none';
    document.getElementById('progressStep').style.display = 'block';
    document.getElementById('step3').classList.remove('active');
    document.getElementById('step3').classList.add('completed');
    document.getElementById('step4').classList.add('active');
    
    // Simulate progress
    let progress = 0;
    const progressInterval = setInterval(() => {
        progress += Math.random() * 20;
        if (progress >= 90) progress = 90;
        document.getElementById('importProgress').style.width = progress + '%';
        document.getElementById('importProgressText').textContent = Math.round(progress) + '%';
    }, 500);
    
    // Call import API (placeholder - would POST to actual endpoint)
    fetch('(window.__RMC_PAGE_DATA__["evals__grade_import_upload_v2-1"]||{})["url_evals_grade_import_apply_api"]', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
            'X-CSRFToken': '(window.__RMC_PAGE_DATA__["evals__grade_import_upload_v2-1"]||{})["var_csrf_token"]'
        },
        body: JSON.stringify({ rows: validRows })
    })
    .then(response => response.json())
    .then(data => {
        clearInterval(progressInterval);
        document.getElementById('importProgress').style.width = '100%';
        document.getElementById('importProgressText').textContent = '100%';
        
        // Show complete step
        setTimeout(() => {
            document.getElementById('progressStep').style.display = 'none';
            document.getElementById('completeStep').style.display = 'block';
            document.getElementById('step4').classList.remove('active');
            document.getElementById('step4').classList.add('completed');
            
            document.getElementById('completeCreatedCount').textContent = data.created;
            document.getElementById('completeUpdatedCount').textContent = data.updated;
            document.getElementById('completeDuration').textContent = data.duration_seconds;
        }, 500);
    })
    .catch(error => {
        clearInterval(progressInterval);
        showError('Import failed: ' + error.message);
        document.getElementById('progressStep').style.display = 'none';
        document.getElementById('reviewStep').style.display = 'block';
    });
}

function resetUpload() {
    location.reload();
}

function showError(message) {
    alert('Error: ' + message);
}
})();
