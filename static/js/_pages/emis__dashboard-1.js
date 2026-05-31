(function(){
  var pageDataEl=document.getElementById("page-data-emis__dashboard-1");
  window.__RMC_PAGE_DATA__=window.__RMC_PAGE_DATA__||{};
  if(pageDataEl){try{window.__RMC_PAGE_DATA__["emis__dashboard-1"]=JSON.parse(pageDataEl.textContent||"{}")}catch(_e){}}
  window.EMIS_DOWNLOAD_URL_BASE = ((window.__RMC_PAGE_DATA__["emis__dashboard-1"] || {})["url_emis_download"]);
document.addEventListener('DOMContentLoaded', function() {
  // Load initial data
  loadCountryInfo();
  loadRecentExports();
  loadStats();

  // Update country info when country changes
  document.getElementById('country_code')?.addEventListener('change', loadCountryInfo);

  // Update terms when academic year changes
  document.getElementById('academic_year')?.addEventListener('change', loadTerms);
});

function loadCountryInfo() {
  const countryCode = document.getElementById('country_code')?.value;
  const infoDiv = document.getElementById('country-info');

  var complianceTpl = ((window.__RMC_PAGE_DATA__["emis__dashboard-1"] || {})["url_emis_compliance"]) || "";
  var complianceUrl = complianceTpl ? complianceTpl.replace("__CC__", encodeURIComponent(countryCode || "")) : "";
  if (!complianceUrl) return;
  fetch(complianceUrl)
    .then(response => response.json())
    .then(data => {
      if (data.error) {
        infoDiv.innerHTML = '<p class="text-muted mb-0">Country information not available</p>';
        return;
      }

      infoDiv.innerHTML = `
        <h6>${data.country_name}</h6>
        <p class="mb-2"><strong>Ministry:</strong> ${data.ministry_name}</p>
        <p class="mb-2"><strong>EMIS Version:</strong> ${data.emis_version}</p>
        ${data.requirements_url ? `<p class="mb-0"><a href="${data.requirements_url}" target="_blank" rel="noopener noreferrer" class="btn btn-sm btn-outline-primary">View Requirements</a></p>` : ''}
      `;
    })
    .catch(error => {
      console.error('Error loading country info:', error);
      infoDiv.innerHTML = '<p class="text-danger mb-0">Error loading country information</p>';
    });
}

function loadRecentExports() {
  var statusUrl = ((window.__RMC_PAGE_DATA__["emis__dashboard-1"] || {})["url_emis_status"]) || "";
  if (!statusUrl) return;
  fetch(statusUrl)
    .then(response => response.json())
    .then(data => {
      const container = document.getElementById('recent-exports');

      if (data.exports.length === 0) {
        container.innerHTML = '<p class="text-muted mb-0">No recent exports</p>';
        return;
      }

      let html = '<div class="table-responsive"><table class="table table-sm">';
      html += '<thead><tr><th>Type</th><th>Records</th><th>Date</th><th>Status</th><th>Actions</th></tr></thead><tbody>';

      data.exports.forEach(export_item => {
        const statusClass = export_item.status === 'completed' ? 'success' : 'warning';
        html += `
          <tr>
            <td>${export_item.type}</td>
            <td>${export_item.record_count}</td>
            <td>${new Date(export_item.export_date).toLocaleDateString()}</td>
            <td><span class="badge bg-${statusClass}">${export_item.status}</span></td>
            <td>
              ${export_item.status === 'completed' ?
                `<a href="${(window.EMIS_DOWNLOAD_URL_BASE || '/emis/download/0/').replace('/0/', '/' + export_item.id + '/')}" class="btn btn-sm btn-outline-primary">Download</a>` :
                '-'}
            </td>
          </tr>
        `;
      });

      html += '</tbody></table></div>';
      container.innerHTML = html;
    })
    .catch(error => {
      console.error('Error loading exports:', error);
      document.getElementById('recent-exports').innerHTML = '<p class="text-danger mb-0">Error loading exports</p>';
    });
}

function loadStats() {
  var statsUrl = (window.RMCPlatformSurface && window.RMCPlatformSurface.url('admin_dashboard')) || '';
  if (!statsUrl) return;
  fetch(statsUrl)
    .then(response => response.json())
    .then(data => {
      document.getElementById('total-students').textContent = data.total_students != null ? data.total_students : '-';
      document.getElementById('total-teachers').textContent = data.total_teachers != null ? data.total_teachers : '-';
      document.getElementById('total-subjects').textContent = data.total_subjects != null ? data.total_subjects : '-';
      document.getElementById('total-classes').textContent = data.total_classes != null ? data.total_classes : '-';
    })
    .catch(error => {
      console.error('Error loading stats:', error);
      // Set defaults
      document.getElementById('total-students').textContent = '-';
      document.getElementById('total-teachers').textContent = '-';
      document.getElementById('total-subjects').textContent = '-';
      document.getElementById('total-classes').textContent = '-';
    });
}

function loadTerms() {
  const academicYearId = document.getElementById('academic_year')?.value;
  const termSelect = document.getElementById('term');

  if (!academicYearId) {
    termSelect.innerHTML = '<option value="">All Terms</option>';
    return;
  }

  // In a real implementation, fetch terms for the selected academic year
  // For now, just reset
  termSelect.innerHTML = '<option value="">All Terms</option>';
}

function refreshExports() {
  const button = event.target.closest('button');
  const originalHtml = button.innerHTML;
  button.innerHTML = '<i class="bi bi-arrow-clockwise spinning"></i>';
  button.disabled = true;

  loadRecentExports().finally(() => {
    button.innerHTML = originalHtml;
    button.disabled = false;
  });
}
})();
