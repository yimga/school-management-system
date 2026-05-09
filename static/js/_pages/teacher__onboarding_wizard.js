  // Auto-focus on first input
  document.addEventListener('DOMContentLoaded', function() {
    const firstInput = document.querySelector('#wizardForm input[type="text"], #wizardForm input[type="email"], #wizardForm select');
    if (firstInput && !firstInput.value) {
      firstInput.focus();
    }
  });
