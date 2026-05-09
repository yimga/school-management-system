  document.addEventListener('DOMContentLoaded', function() {
    const opacitySlider = document.getElementById('logoOpacitySlider');
    const opacityDarkSlider = document.getElementById('logoOpacityDarkSlider');
    const opacityValue = document.getElementById('opacityValue');
    const opacityDarkValue = document.getElementById('opacityDarkValue');
    const saveBtn = document.getElementById('saveLogoSettingsBtn');
    const resetBtn = document.getElementById('resetLogoBtn');

    // Load saved values
    const savedOpacity = localStorage.getItem('logo-opacity');
    const savedOpacityDark = localStorage.getItem('logo-opacity-dark');
    
    if (savedOpacity) {
      const opacityPercent = Math.round(parseFloat(savedOpacity) * 100);
      opacitySlider.value = opacityPercent;
      opacityValue.textContent = opacityPercent + '%';
    }

    if (savedOpacityDark) {
      const opacityDarkPercent = Math.round(parseFloat(savedOpacityDark) * 100);
      opacityDarkSlider.value = opacityDarkPercent;
      opacityDarkValue.textContent = opacityDarkPercent + '%';
    }

    // Update display value on slider change
    opacitySlider.addEventListener('input', function() {
      opacityValue.textContent = this.value + '%';
      updateLogoOpacity();
    });

    opacityDarkSlider.addEventListener('input', function() {
      opacityDarkValue.textContent = this.value + '%';
      updateLogoOpacity();
    });

    // Update logo in real-time
    function updateLogoOpacity() {
      const opacity = parseFloat(opacitySlider.value) / 100;
      const opacityDark = parseFloat(opacityDarkSlider.value) / 100;
      document.documentElement.style.setProperty('--logo-opacity', opacity);
      document.documentElement.style.setProperty('--logo-opacity-dark', opacityDark);
    }

    // Save settings
    saveBtn.addEventListener('click', function() {
      const opacity = parseFloat(opacitySlider.value) / 100;
      const opacityDark = parseFloat(opacityDarkSlider.value) / 100;
      
      localStorage.setItem('logo-opacity', opacity);
      localStorage.setItem('logo-opacity-dark', opacityDark);
      
      alert('✓ Logo settings saved successfully!');
    });

    // Reset to defaults
    resetBtn.addEventListener('click', function() {
      if (confirm('Reset logo settings to defaults?')) {
        localStorage.removeItem('logo-opacity');
        localStorage.removeItem('logo-opacity-dark');
        
        opacitySlider.value = 8;
        opacityDarkSlider.value = 12;
        opacityValue.textContent = '8%';
        opacityDarkValue.textContent = '12%';
        
        updateLogoOpacity();
        alert('✓ Logo settings reset to defaults!');
      }
    });

    // Initial update
    updateLogoOpacity();
  });
