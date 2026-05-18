document.getElementById('photoLinkCopyBtn')?.addEventListener('click', function() {
  var input = document.getElementById('photoLinkUrl');
  var btn = document.getElementById('photoLinkCopyBtn');
  var orig = btn.innerHTML;
  var copiedText = btn.getAttribute('data-copied-text') || 'Copied!';
  function showCopied() {
    btn.innerHTML = '<i class="bi bi-check me-1"></i> ' + copiedText;
    setTimeout(function() { btn.innerHTML = orig; }, 2000);
  }
  input.select();
  input.setSelectionRange(0, 99999);
  if (navigator.clipboard && navigator.clipboard.writeText) {
    navigator.clipboard.writeText(input.value).then(showCopied).catch(function() {
      try { document.execCommand('copy'); showCopied(); } catch (e) { }
    });
  } else {
    try { document.execCommand('copy'); showCopied(); } catch (e) { }
  }
});
