function toggleJobDetails(button) {
    const card = button.closest('.job-card');
    const details = card.querySelector('.job-details');
    
    if (details.style.display === 'none') {
        details.style.display = 'block';
        button.innerHTML = '<i class="fas fa-chevron-up"></i>';
    } else {
        details.style.display = 'none';
        button.innerHTML = '<i class="fas fa-chevron-down"></i>';
    }
}

function refreshJobList() {
    const btn = document.getElementById('refreshBtn');
    const icon = btn.querySelector('i');
    icon.classList.remove('stopped');
    
    setTimeout(() => {
        location.reload();
    }, 500);
}

function pollJobStatus(jobId) {
    // Fetch latest job status
    fetch(`/api/import-jobs/${jobId}/`)
        .then(response => response.json())
        .then(data => {
            // Update card
            const card = document.querySelector(`[data-job-id="${jobId}"]`);
            if (data.status === 'completed' || data.status === 'failed') {
                location.reload();
            } else {
                alert('Job still processing... Refreshing page.');
                setTimeout(() => location.reload(), 2000);
            }
        });
}

function exportJobResults(jobId) {
    // Export job results as CSV
    window.location.href = `/evals/import-job/${jobId}/export/`;
}

function retryJob(jobId) {
    if (confirm('Are you sure you want to retry this job?')) {
        fetch(`/api/import-jobs/${jobId}/retry/`, { 
            method: 'POST',
            headers: {
                'X-CSRFToken': document.querySelector('[name=csrfmiddlewaretoken]')?.value
            }
        })
            .then(response => response.json())
            .then(data => {
                if (data.success) {
                    alert('Job queued for retry');
                    location.reload();
                }
            });
    }
}

// Auto-refresh if there are processing jobs
window.addEventListener('load', function() {
    const processingCards = document.querySelectorAll('.job-card-processing');
    if (processingCards.length > 0) {
        setInterval(() => location.reload(), 5000);
    }
});
