/**
 * Shared dashboard customizer: drag/drop, sidebar, tile styles, custom links.
 * Requires a container with id "dashboard-layout" and cards with data-widget-id.
 */
(function () {
  const container = document.getElementById("dashboard-layout");
  if (!container) return;

  const safeParseJson = (value, fallback = {}) => {
    if (!value) return fallback;
    try {
      const parsed = JSON.parse(value);
      return parsed;
    } catch (_) {
      return fallback;
    }
  };

  let widgetConfig = safeParseJson(container.dataset.widgetConfig, {});
  // Drag/reorder is handled only by dashboard-layout.js (Sortable.js). This script handles settings and widget meta.
  const state = {
    settings: {
      show_sidebar: container.dataset.showSidebar === "true",
      tile_variant: container.dataset.tileVariant || "default",
      sidebar_items: safeParseJson(container.dataset.sidebarItems, []),
      custom_links: safeParseJson(container.dataset.customLinks, []),
      widget_meta: safeParseJson(container.dataset.widgetMeta, {}),
    },
    endpoints: {
      save: container.dataset.saveUrl,
      load: container.dataset.loadUrl,
    },
  };

  let syncControls = () => {};
  let renderCustomLinks = () => {};

  const cards = Array.from(container.querySelectorAll("[data-widget-id]"));

  const sizeClasses = ["widget-size-sm", "widget-size-md", "widget-size-lg"];
  const variantClasses = ["widget-variant-default", "widget-variant-compact", "widget-variant-flat"];

  const injectCustomizerStyles = () => {
    if (document.getElementById("dashboard-customizer-meta-styles")) return;
    const style = document.createElement("style");
    style.id = "dashboard-customizer-meta-styles";
    style.textContent = `
      #dashboard-layout [data-widget-id] {
        position: relative;
      }
      #dashboard-layout .widget-meta-control {
        position: absolute;
        top: 8px;
        right: 8px;
        display: flex;
        gap: 0.25rem;
        opacity: 0;
        pointer-events: none;
        transition: opacity 0.2s ease;
        z-index: 5;
      }
      #dashboard-layout.drag-mode .widget-meta-control {
        opacity: 1;
        pointer-events: auto;
      }
      #dashboard-layout .widget-meta-control select {
        min-width: 70px;
        padding: 0.2rem 0.35rem;
        font-size: 0.7rem;
      }
      #dashboard-layout .widget-size-sm .card-body {
        padding: 0.75rem;
      }
      #dashboard-layout .widget-size-lg .card-body {
        padding: 1.4rem;
      }
      #dashboard-layout .widget-variant-compact .card-body {
        border-radius: 16px;
      }
      #dashboard-layout .widget-variant-flat {
        background: rgba(255, 255, 255, 0.9);
        box-shadow: none;
        border-color: rgba(15, 23, 42, 0.08);
      }
    `;
    document.head.appendChild(style);
  };

  const ensureWidgetMetaEntry = (widgetId) => {
    if (!widgetId) return null;
    const config = widgetConfig[widgetId] || {};
    const existing = state.settings.widget_meta[widgetId] || {};
    const defaultSize = (config.default_size || "md").toLowerCase();
    const defaultVariant = (config.default_variant || "default").toLowerCase();
    let size = (existing.size || defaultSize).toLowerCase();
    let variant = (existing.variant || defaultVariant).toLowerCase();
    if (!sizeClasses.includes(`widget-size-${size}`) && !["sm","md","lg"].includes(size)) {
      size = "md";
    }
    if (!["sm","md","lg"].includes(size)) {
      size = "md";
    }
    if (!["default","compact","flat"].includes(variant)) {
      variant = "default";
    }
    state.settings.widget_meta[widgetId] = { size, variant };
    return state.settings.widget_meta[widgetId];
  };

  const applyWidgetMeta = () => {
    cards.forEach((card) => {
      const widgetId = card.dataset.widgetId;
      const meta = ensureWidgetMetaEntry(widgetId);
      if (!meta) return;
      sizeClasses.forEach((cls) => card.classList.remove(cls));
      variantClasses.forEach((cls) => card.classList.remove(cls));
      card.classList.add(`widget-size-${meta.size}`);
      card.classList.add(`widget-variant-${meta.variant}`);
      card.dataset.widgetSize = meta.size;
      card.dataset.widgetVariant = meta.variant;
    });
  };

  const attachMetaControls = () => {
    cards.forEach((card) => {
      if (card.querySelector(".widget-meta-control")) return;
      const widgetId = card.dataset.widgetId;
      if (!widgetId) return;
      const meta = ensureWidgetMetaEntry(widgetId);
      const config = widgetConfig[widgetId] || {};
      const allowedSizes = Array.isArray(config.allowed_sizes) && config.allowed_sizes.length
        ? config.allowed_sizes
        : ["sm", "md", "lg"];
      const allowedVariants = Array.isArray(config.allowed_variants) && config.allowed_variants.length
        ? config.allowed_variants
        : ["default", "compact", "flat"];

      const control = document.createElement("div");
      control.className = "widget-meta-control";
      const sizeSelect = document.createElement("select");
      sizeSelect.className = "form-select form-select-sm size-select";
      sizeSelect.setAttribute("aria-label", "Widget size");
      allowedSizes.forEach((size) => {
        const normalizedSize = String(size).toLowerCase();
        const option = document.createElement("option");
        option.value = normalizedSize;
        option.textContent = normalizedSize.charAt(0).toUpperCase() + normalizedSize.slice(1);
        option.selected = meta.size === normalizedSize;
        sizeSelect.appendChild(option);
      });
      sizeSelect.addEventListener("change", (event) => {
        meta.size = event.target.value;
        applyWidgetMeta();
        persistLayout();
      });

      const variantSelect = document.createElement("select");
      variantSelect.className = "form-select form-select-sm variant-select";
      variantSelect.setAttribute("aria-label", "Widget style");
      allowedVariants.forEach((variant) => {
        const normalizedVariant = String(variant).toLowerCase();
        const option = document.createElement("option");
        option.value = normalizedVariant;
        option.textContent = normalizedVariant.charAt(0).toUpperCase() + normalizedVariant.slice(1);
        option.selected = meta.variant === normalizedVariant;
        variantSelect.appendChild(option);
      });
      variantSelect.addEventListener("change", (event) => {
        meta.variant = event.target.value;
        applyWidgetMeta();
        persistLayout();
      });

      control.appendChild(sizeSelect);
      control.appendChild(variantSelect);
      card.appendChild(control);
    });
  };

  injectCustomizerStyles();

  const getCsrf = () => {
    const match = document.cookie.match(/csrftoken=([^;]+)/);
    return match ? decodeURIComponent(match[1]) : "";
  };

  const applySavedLayout = (layout) => {
    if (!layout || !Array.isArray(layout.items)) return;
    const sorted = layout.items
      .slice()
      .sort((a, b) => (a.order || 0) - (b.order || 0));
    sorted.forEach((item) => {
      if (!item || !item.id) return;
      const card = container.querySelector(`[data-widget-id="${item.id}"]`);
      if (!card) return;
      const targetCol =
        document.querySelector(`[data-dashboard-column-key="${item.column}"]`) ||
        document.querySelector(`[data-dashboard-column="${item.column}"]`);
      if (targetCol) {
        targetCol.appendChild(card);
      } else {
        container.appendChild(card);
      }
    });
  };

  const loadLayout = async () => {
    if (!state.endpoints.load) return;
    try {
      const res = await fetch(state.endpoints.load, { credentials: "same-origin" });
      const data = await res.json();
      if (!data) return;
      const layoutPayload = data.layout || {};
      if (Array.isArray(layoutPayload.items)) {
        applySavedLayout(layoutPayload);
      }
      const s = layoutPayload.__settings__ || data.settings || {};
      state.settings = {
        show_sidebar: s.hasOwnProperty("show_sidebar") ? !!s.show_sidebar : !!state.settings.show_sidebar,
        tile_variant: s.tile_variant || state.settings.tile_variant || "default",
        sidebar_items: Array.isArray(s.sidebar_items) ? s.sidebar_items : state.settings.sidebar_items,
        custom_links: Array.isArray(s.custom_links) ? s.custom_links : state.settings.custom_links,
        widget_meta: s.widget_meta || state.settings.widget_meta || {},
      };
      if (Array.isArray(data.widgets)) {
        const updatedConfig = {};
        data.widgets.forEach((widget) => {
          updatedConfig[widget.id] = {
            allowed_sizes:
              Array.isArray(widget.allowed_sizes) && widget.allowed_sizes.length
                ? widget.allowed_sizes
                : ["sm", "md", "lg"],
            allowed_variants:
              Array.isArray(widget.allowed_variants) && widget.allowed_variants.length
                ? widget.allowed_variants
                : ["default", "compact", "flat"],
            default_size: widget.default_size || "md",
            default_variant: widget.default_variant || "default",
          };
        });
        widgetConfig = { ...widgetConfig, ...updatedConfig };
      }
      applySettings();
      syncControls();
      attachMetaControls();
    } catch (_) {}
  };

  const persistLayout = async () => {
    if (!state.endpoints.save) return;
    const layoutItems = [];
    container.querySelectorAll("[data-widget-id]").forEach((card, idx) => {
      const column =
        card.dataset.dashboardColumn ||
        card.closest("[data-dashboard-column]")?.dataset.dashboardColumn ||
        "main";
      layoutItems.push({
        id: card.dataset.widgetId,
        column,
        order: idx,
        size: card.dataset.widgetSize,
        variant: card.dataset.widgetVariant,
      });
    });
    const layoutPayload = {
      items: layoutItems,
      __settings__: state.settings,
    };
    try {
      await fetch(state.endpoints.save, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "X-CSRFToken": getCsrf(),
        },
        credentials: "same-origin",
        body: JSON.stringify({
          layout: layoutPayload,
        }),
      });
    } catch (_) {}
  };

  const applySettings = () => {
    container.classList.remove("tile-variant-default", "tile-variant-compact", "tile-variant-flat");
    container.classList.add(`tile-variant-${state.settings.tile_variant || "default"}`);
    applyWidgetMeta();
  };

  // Event wiring for controls (if present)
  const initControls = () => {
    const toggle = document.getElementById("toggleCustomize");
    const toggleSidebar = document.getElementById("toggleSidebar");
    const tileVariantSelect = document.getElementById("tileVariantSelect");
    const sidebarPicker = document.getElementById("sidebarItemsPicker");
    const addLinkBtn = document.getElementById("addCustomLink");
    const linkLabelInput = document.getElementById("customLinkLabel");
    const linkUrlInput = document.getElementById("customLinkUrl");
    const linkList = document.getElementById("customLinkList");
    const shortcutsCard = document.getElementById("customShortcuts");

    const updateShortcutsVisibility = () => {
      if (!shortcutsCard) return;
      const hasLinks =
        (state.settings.custom_links || []).length > 0 ||
        (state.settings.sidebar_items || []).length > 0;
      const show = !!state.settings.show_sidebar || hasLinks;
      shortcutsCard.classList.toggle("d-none", !show);
    };

    // Drag/reorder is handled by dashboard-layout.js (Sortable.js). Toggle state is used there.
    if (toggle) {
      toggle.addEventListener("change", () => {
        container.classList.toggle("drag-mode", toggle.checked);
      });
      container.classList.toggle("drag-mode", !!toggle.checked);
    }

    if (toggleSidebar) {
      toggleSidebar.addEventListener("change", (e) => {
        state.settings.show_sidebar = e.target.checked;
        updateShortcutsVisibility();
        persistLayout();
      });
    }

    if (tileVariantSelect) {
      tileVariantSelect.addEventListener("change", (e) => {
        state.settings.tile_variant = e.target.value || "default";
        applySettings();
        persistLayout();
      });
    }

    if (sidebarPicker) {
      sidebarPicker.querySelectorAll('input[type="checkbox"]').forEach((cb) => {
        cb.addEventListener("change", () => {
          const selected = Array.from(sidebarPicker.querySelectorAll('input[type="checkbox"]:checked')).map((el) => el.value);
          state.settings.sidebar_items = selected;
          updateShortcutsVisibility();
          persistLayout();
        });
      });
    }

    renderCustomLinks = () => {
      if (!linkList) return;
      linkList.innerHTML = "";
      const links = state.settings.custom_links || [];
      if (!links.length) {
        const empty = document.createElement("li");
        empty.className = "text-muted small";
        empty.textContent = "No custom links yet.";
        linkList.appendChild(empty);
        return;
      }
      links.forEach((link, idx) => {
        const li = document.createElement("li");
        li.className = "d-flex justify-content-between align-items-center mb-1";
        li.innerHTML = `<span><i class="bi ${link.icon || "bi-link"}"></i> ${link.label}</span>`;
        const btn = document.createElement("button");
        btn.className = "btn btn-sm btn-outline-danger";
        btn.textContent = "Remove";
        btn.addEventListener("click", () => {
          state.settings.custom_links.splice(idx, 1);
          persistLayout();
          renderCustomLinks();
        });
        li.appendChild(btn);
        linkList.appendChild(li);
      });
      updateShortcutsVisibility();
    };

    syncControls = () => {
      if (toggleSidebar) {
        toggleSidebar.checked = !!state.settings.show_sidebar;
      }
      if (tileVariantSelect) {
        tileVariantSelect.value = state.settings.tile_variant || "default";
      }
      if (sidebarPicker) {
        const selected = new Set(state.settings.sidebar_items || []);
        sidebarPicker.querySelectorAll('input[type="checkbox"]').forEach((cb) => {
          cb.checked = selected.has(cb.value);
        });
      }
      renderCustomLinks();
      updateShortcutsVisibility();
    };

    if (addLinkBtn && linkLabelInput && linkUrlInput) {
      addLinkBtn.addEventListener("click", () => {
        const label = (linkLabelInput.value || "").trim();
        const url = (linkUrlInput.value || "").trim();
        if (!label || !url) return;
        state.settings.custom_links = state.settings.custom_links || [];
        state.settings.custom_links.push({ label, url, icon: "bi-link" });
        linkLabelInput.value = "";
        linkUrlInput.value = "";
        persistLayout();
        renderCustomLinks();
      });
    }

    renderCustomLinks();
    syncControls();
  };

  applySettings();
  attachMetaControls();
  loadLayout();
  initControls();
})();
