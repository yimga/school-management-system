(function () {
  const TRACKED_COLOR_FIELDS = [
    "primary_color",
    "accent_color",
    "header_bg_color",
    "footer_bg_color",
    "success_color",
    "warning_color",
    "danger_color",
  ];

  const previewDevice = document.querySelector(".preview-device");
  const contrastHint = document.getElementById("contrastHint");
  const roleSelect = document.getElementById("previewRoleSelect");
  const roleLabel = document.getElementById("previewRoleLabel");

  const getField = (name) => document.getElementById(`id_${name}`);

  const getColorValue = (name, fallback = "") => {
    const field = getField(name);
    if (!field) return fallback;
    const value = (field.value || "").trim();
    return value || fallback;
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
    if (Number.isNaN(value)) return null;
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
    if (!a || !b) return null;
    const lumA = luminance(a);
    const lumB = luminance(b);
    const lighter = Math.max(lumA, lumB);
    const darker = Math.min(lumA, lumB);
    return (lighter + 0.05) / (darker + 0.05);
  };

  const pickReadableText = (backgroundHex) => {
    const bg = toRgb(backgroundHex);
    const white = toRgb("#ffffff");
    const dark = toRgb("#0f172a");
    const whiteRatio = contrastRatio(bg, white) || 0;
    const darkRatio = contrastRatio(bg, dark) || 0;
    return whiteRatio >= darkRatio ? "#ffffff" : "#0f172a";
  };

  const updateRoleLabel = () => {
    if (!roleSelect || !roleLabel) return;
    const fallback = roleSelect.dataset.currentRole || "Administrator";
    const value = roleSelect.value || fallback;
    roleLabel.textContent = `Inherits ${value} access.`;
  };

  const updateContrastHint = (primaryHex, previewTextHex) => {
    if (!contrastHint) return;

    const metrics = [
      {
        label: "Primary vs preview text",
        bgHex: primaryHex,
        fgHex: previewTextHex,
      },
      {
        label: "Accent vs preview text",
        bgHex: getColorValue("accent_color", "#38bdf8"),
        fgHex: previewTextHex,
      },
      {
        label: "Header vs preview text",
        bgHex: getColorValue("header_bg_color", primaryHex),
        fgHex: previewTextHex,
      },
    ];

    const lines = metrics.map(({ label, bgHex, fgHex }) => {
      const ratio = contrastRatio(toRgb(bgHex), toRgb(fgHex));
      if (ratio === null) {
        return { label, ratio: "n/a", status: "warn" };
      }
      return {
        label,
        ratio: `${ratio.toFixed(1)}:1`,
        status: ratio < 4.5 ? "warn" : "good",
      };
    });

    const hasWarning = lines.some((line) => line.status === "warn");
    contrastHint.classList.toggle("unsafe", hasWarning);
    contrastHint.innerHTML = `
      <strong>${hasWarning ? "Contrast check" : "Contrast OK"}</strong>
      ${lines
        .map(
          ({ label, ratio, status }) =>
            `<span class="contrast-line ${status}"><em>${label}:</em> ${ratio}</span>`
        )
        .join("")}
    `;
  };

  const updatePreview = () => {
    if (!previewDevice) return;

    const primary = getColorValue("primary_color", "#0b0f14");
    const headerSurface = getColorValue("header_bg_color", primary);
    const contentSurface = getColorValue("footer_bg_color", headerSurface);
    const accent = getColorValue("accent_color", "#38bdf8");
    const text = pickReadableText(primary);

    previewDevice.style.setProperty("--preview-sidebar-bg", primary);
    previewDevice.style.setProperty("--preview-sidebar-surface", headerSurface);
    previewDevice.style.setProperty("--preview-content-bg", contentSurface);
    previewDevice.style.setProperty("--preview-text-color", text);
    previewDevice.style.setProperty("--preview-accent-color", accent);
    updateContrastHint(primary, text);
  };

  const collectTrackedInputs = () => {
    const inputs = [];
    TRACKED_COLOR_FIELDS.forEach((name) => {
      const field = getField(name);
      if (field) inputs.push(field);
    });
    if (inputs.length) return inputs;
    return Array.from(document.querySelectorAll('input[type="color"]'));
  };

  document.addEventListener("DOMContentLoaded", () => {
    const inputs = collectTrackedInputs();

    inputs.forEach((input) => {
      input.addEventListener("input", updatePreview);
      input.addEventListener("change", updatePreview);
    });

    const resetButton = document.getElementById("preview-reset");
    if (resetButton) {
      resetButton.addEventListener("click", () => {
        inputs.forEach((input) => {
          input.dispatchEvent(new Event("input", { bubbles: true }));
          input.dispatchEvent(new Event("change", { bubbles: true }));
        });
        if (resetButton.dataset.resetMessage) {
          resetButton.textContent = resetButton.dataset.resetMessage;
        }
        updatePreview();
      });
    }

    if (roleSelect) {
      roleSelect.addEventListener("change", updateRoleLabel);
      updateRoleLabel();
    }

    document.addEventListener("theme-pack-selected", updatePreview);

    updatePreview();
  });
})();
