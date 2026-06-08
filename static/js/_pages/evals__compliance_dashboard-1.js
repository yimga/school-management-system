(function(){
  var pageDataEl=document.getElementById("page-data-evals__compliance_dashboard-1");
  window.__RMC_PAGE_DATA__=window.__RMC_PAGE_DATA__||{};
  if(pageDataEl){try{window.__RMC_PAGE_DATA__["evals__compliance_dashboard-1"]=JSON.parse(pageDataEl.textContent||"{}")}catch(_e){}}
  window.EVALS_EXTEND_DEADLINE_URL_BASE = ((window.__RMC_PAGE_DATA__["evals__compliance_dashboard-1"] || {})["url_evals_extend_deadline"]);
function showTeacherDetails(teacherId, teacherName, deadlines) {
    document.getElementById('teacherName').textContent = teacherName;
    
    const tbody = document.getElementById('deadlinesList');
    tbody.innerHTML = '';
    
    deadlines.forEach(deadline => {
        const row = tbody.insertRow();
        const daysBadge = deadline.days_left < 0 ? 'badge-danger' : deadline.days_left <= 3 ? 'badge-warning' : 'badge-success';
        const statusBadge = deadline.submission_status === 'on_track' ? 'badge-success' : deadline.submission_status === 'at_risk' ? 'badge-warning' : 'badge-danger';
        row.innerHTML = `
            <td>${deadline.subject_name}</td>
            <td>
                <div>${deadline.deadline_date}</div>
                <span class="badge ${daysBadge}">${deadline.days_left} days</span>
            </td>
            <td>
                <span class="badge ${statusBadge}">${deadline.submission_status}</span>
                <div class="small text-muted mt-1">${deadline.submitted_count}/${deadline.total_students}</div>
            </td>
            <td>
                <a href="${(window.EVALS_EXTEND_DEADLINE_URL_BASE || '/evals/compliance/deadline/0/extend/').replace('/0/', '/' + deadline.subject_assignment_id + '/')}" class="btn btn-xs btn-warning">
                    Extend
                </a>
            </td>
        `;
    });
}
})();
