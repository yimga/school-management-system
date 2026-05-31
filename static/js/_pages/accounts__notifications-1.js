(function(){
  var pageDataEl=document.getElementById("page-data-accounts__notifications-1");
  window.__RMC_PAGE_DATA__=window.__RMC_PAGE_DATA__||{};
  if(pageDataEl){try{window.__RMC_PAGE_DATA__["accounts__notifications-1"]=JSON.parse(pageDataEl.textContent||"{}")}catch(_e){}}
async function markAsRead(notifId) {
  try {
    const readUrl =
      (window.RMCPlatformSurface &&
        window.RMCPlatformSurface.templated("notification_read", {
          notification_id: notifId,
        })) ||
      "";
    if (!readUrl) return;
    const response = await fetch(readUrl, {
      method: 'POST',
      headers: {
        'X-CSRFToken': ((window.__RMC_PAGE_DATA__["accounts__notifications-1"] || {})["var_csrf_token"]),
        'Content-Type': 'application/json',
      },
    });
    
    if (response.ok) {
      // Reload page to show updated status
      window.location.reload();
    } else {
      alert('Failed to mark notification as read');
    }
  } catch (error) {
    console.error('Error marking notification as read:', error);
    alert('An error occurred');
  }
}
})();
