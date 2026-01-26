/**
 * Shared dashboard customizer: drag/drop, sidebar, tile styles, custom links.
 * Requires a container with id "dashboard-layout" and cards with data-widget-id.
 */
(function () {
  const container = document.getElementById("dashboard-layout");
  if (!container) return;

  const state = {
    settings: {
      show_sidebar: container.dataset.showSidebar === "true",
      tile_variant: container.dataset.tileVariant || "default",
      sidebar_items: JSON.parse(container.dataset.sidebarItems || "[]"),
      custom_links: JSON.parse(container.dataset.customLinks || "[]"),
    },
    endpoints: {
      save: container.dataset.saveUrl,
      load: container.dataset.loadUrl,
    },
  };

  let syncControls = () => {};
  let renderCustomLinks = () => {};

  const cards = Array.from(container.querySelectorAll("[data-widget-id]"));

  const getCsrf = () => {
    const match = document.cookie.match(/csrftoken=([^;]+)/);
    return match ? decodeURIComponent(match[1]) : "";
  };

  const applySavedLayout = (layout) => {
    if (!layout || typeof layout !== "object") return;
    const order = Object.entries(layout)
      .filter(([id]) => id !== "__settings__")
      .map(([id, meta]) => ({ id, pos: (meta && meta.position) || (meta && meta.order) || 0 }))
      .sort((a, b) => a.pos - b.pos);
    order.forEach(({ id }) => {
      const card = container.querySelector(`[data-widget-id="${id}"]`);
      if (card) container.appendChild(card);
    });
  };

  const loadLayout = async () => {
    if (!state.endpoints.load) return;
    try {
      const res = await fetch(state.endpoints.load, { credentials: "same-origin" });
      const data = await res.json();
      if (data && data.layout) {
        applySavedLayout(data.layout);
        const s = data.settings || data.layout.__settings__ || {};
        state.settings = {
          show_sidebar: !!s.show_sidebar,
          tile_variant: s.tile_variant || "default",
          sidebar_items: s.sidebar_items || [],
          custom_links: s.custom_links || [],
        };
        applySettings();
        syncControls();
      }
    } catch (_) {}
  };

  const persistLayout = async () => {
    if (!state.endpoints.save) return;
    const layout = {};
    container.querySelectorAll("[data-widget-id]").forEach((card, idx) => {
      layout[card.dataset.widgetId] = { position: idx };
    });
    try {
      await fetch(state.endpoints.save, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "X-CSRFToken": getCsrf(),
        },
        credentials: "same-origin",
        body: JSON.stringify({
          layout,
          visible_widgets: Object.keys(layout),
          settings: state.settings,
        }),
      });
    } catch (_) {}
  };

  const applySettings = () => {
    container.classList.remove("tile-variant-default", "tile-variant-compact", "tile-variant-flat");
    container.classList.add(`tile-variant-${state.settings.tile_variant || "default"}`);
  };

  const enableDrag = () => {
    container.classList.add("drag-mode");
    cards.forEach((card) => {
      card.setAttribute("draggable", "true");
      card.addEventListener("dragstart", onDragStart);
      card.addEventListener("dragover", onDragOver);
      card.addEventListener("drop", onDrop);
      card.addEventListener("dragend", onDragEnd);
    });
  };

  const disableDrag = () => {
    container.classList.remove("drag-mode");
    cards.forEach((card) => {
      card.removeAttribute("draggable");
      card.classList.remove("dragging");
      card.removeEventListener("dragstart", onDragStart);
      card.removeEventListener("dragover", onDragOver);
      card.removeEventListener("drop", onDrop);
      card.removeEventListener("dragend", onDragEnd);
    });
  };

  let dragSrc = null;
  function onDragStart(e) {
    dragSrc = this;
    this.classList.add("dragging");
    e.dataTransfer.effectAllowed = "move";
  }
  function onDragOver(e) {
    e.preventDefault();
    const target = e.target.closest("[data-widget-id]");
    if (!target || target === dragSrc) return;
    const cardsArr = Array.from(container.querySelectorAll("[data-widget-id]"));
    const srcIdx = cardsArr.indexOf(dragSrc);
    const tgtIdx = cardsArr.indexOf(target);
    if (srcIdx < tgtIdx) {
      target.after(dragSrc);
    } else {
      target.before(dragSrc);
    }
  }
  function onDrop(e) {
    e.preventDefault();
  }
  function onDragEnd() {
    this.classList.remove("dragging");
    persistLayout();
  }

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
      const show = !!state.settings.show_sidebar;
      shortcutsCard.classList.toggle("d-none", !show);
    };

    if (toggle) {
      toggle.addEventListener("change", (e) => {
        e.target.checked ? enableDrag() : disableDrag();
      });
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
  loadLayout();
  initControls();
})();
