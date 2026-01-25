(function () {
  const contrastCombos = [
    {
      label: "Sidebar background vs text",
      bg: "admin_sidebar_bg_color",
      fg: "admin_sidebar_text_color",
    },
    {
      label: "Surface color vs text",
      bg: "admin_sidebar_surface_color",
      fg: "admin_sidebar_text_color",
    },
    {
      label: "Child background vs border",
      bg: "admin_sidebar_child_bg_start",
      fg: "admin_sidebar_child_border_color",
    },
  ];

  const colorInputSelector = 'input[type="color"]';
  const previewDevice = document.querySelector(".preview-device");
  const contrastHint = document.getElementById("contrastHint");
  const previewCards = document.querySelectorAll(".preview-card strong");
  const roleSelect = document.getElementById("previewRoleSelect");
  const roleLabel = document.getElementById("previewRoleLabel");

  const getColorValue = (name) => {
    const field = document.getElementById(`id_${name}`);
    if (field && field.value) {
      return field.value;
    }
    return "";
  };

  const toRgb = (hex) => {
    if (!hex) return null;
    const normalized = hex.replace("#", "").trim();
    const expanded =
      normalized.length === 3
        ? normalized
            .split("")
            .map((char) => char + char)
            .join("")
        : normalized;
    if (expanded.length !== 6) return null;
    const value = parseInt(expanded, 16);
    return {
      r: (value >> 16) & 255,
      g: (value >> 8) & 255,
      b: value & 255,
    };
  };

  const luminance = (rgb) => {
    if (!rgb) return 0;
    const channel = (c) => {
      const normalized = c / 255;
      return normalized <= 0.03928
        ? normalized / 12.92
        : Math.pow((normalized + 0.055) / 1.055, 2.4);
    };
    return 0.2126 * channel(rgb.r) + 0.7152 * channel(rgb.g) + 0.0722 * channel(rgb.b);
  };

  const contrastRatio = (a, b) => {
    const lumA = luminance(a);
    const lumB = luminance(b);
    const lighter = Math.max(lumA, lumB);
    const darker = Math.min(lumA, lumB);
    if (darker === 0) {
      return lighter === 0 ? 1 : 1 / darker;
    }
    return (lighter + 0.05) / (darker + 0.05);
  };

  const updatePreview = () => {
    if (!previewDevice) return;
    const sidebarBg = getColorValue("admin_sidebar_bg_color") || "#0b0f14";
    const sidebarSurface = getColorValue("admin_sidebar_surface_color") || "#111827";
    const text = getColorValue("admin_sidebar_text_color") || "#e2e8f0";
    const accent = getColorValue("admin_sidebar_child_active_color") || "#38bdf8";
    previewDevice.style.setProperty("--preview-sidebar-bg", sidebarBg);
    previewDevice.style.setProperty("--preview-sidebar-surface", sidebarSurface);
    previewDevice.style.setProperty("--preview-text-color", text);
    previewDevice.style.setProperty("--preview-accent-color", accent);
    if (contrastHint) {
      updateContrastHint();
    }
  };

  const updateRoleLabel = () => {
    if (!roleSelect || !roleLabel) return;
    const fallback = roleSelect.dataset.currentRole || "Administrator";
    const value = roleSelect.value || fallback;
    roleLabel.textContent = `Inherits ${value} access.`;
  };

  const updateContrastHint = () => {
    if (!contrastHint) return;
    const messages = contrastCombos.map(({ label, bg, fg }) => {
      const bgValue = toRgb(getColorValue(bg));
      const fgValue = toRgb(getColorValue(fg));
      let ratioText = "n/a";
      let status = "good";
      if (bgValue && fgValue) {
        const ratio = contrastRatio(bgValue, fgValue);
        ratioText = `${ratio.toFixed(1)}:1`;
        if (ratio < 4.5) {
          status = "warn";
        }
      }
      return { label, ratio: ratioText, status };
    });
    const hasWarning = messages.some((message) => message.status === "warn");
    contrastHint.classList.toggle("unsafe", hasWarning);
    contrastHint.innerHTML = `
      <strong>${hasWarning ? "Contrast check" : "Contrast OK"}</strong>
      ${messages
        .map(
          ({ label, ratio, status }) =>
            `<span class="contrast-line ${status}"><em>${label}:</em> ${ratio}</span>`
        )
        .join("")}
    `;
  };

  document.addEventListener("DOMContentLoaded", () => {
    const inputs = Array.from(document.querySelectorAll(colorInputSelector));
    if (!inputs.length) return;
    inputs.forEach((input) => {
      input.addEventListener("input", () => {
        updatePreview();
      });
    });
    const resetButton = document.getElementById("preview-reset");
    if (resetButton) {
      resetButton.addEventListener("click", () => {
        inputs.forEach((input) => input.dispatchEvent(new Event("input")));
        if (resetButton.dataset.resetMessage) {
          resetButton.textContent = resetButton.dataset.resetMessage;
        }
      });
    }
    if (roleSelect) {
      roleSelect.addEventListener("change", updateRoleLabel);
      updateRoleLabel();
    }
    updatePreview();
  });
})();
