(function () {
  "use strict";

  const LAYOUT_EL = document.getElementById("theme-builder-initial-layout");
  const blockList = document.getElementById("theme-builder-block-list");
  const canvas = document.getElementById("theme-builder-canvas");
  const statusEl = document.getElementById("theme-builder-status");
  const saveBtn = document.getElementById("theme-builder-save");
  const publishBtn = document.getElementById("theme-builder-publish");
  const rollbackBtn = document.getElementById("theme-builder-rollback");
  const publishLogEl = document.getElementById("theme-builder-publish-log");
  const previewBtn = document.getElementById("theme-builder-preview");
  const undoBtn = document.getElementById("theme-builder-undo");
  const redoBtn = document.getElementById("theme-builder-redo");
  const tokenPanel = document.getElementById("theme-builder-token-panel");
  const contrastMeter = document.getElementById("theme-builder-contrast-meter");
  const contrastValue = document.getElementById("theme-builder-contrast-value");
  const CONTRAST_PAIR_MIN = 1.6;
  const surfaceButtons = Array.from(
    document.querySelectorAll(".preview-surface-btn[data-preview-surface]")
  );

  const TOKEN_FIELDS = [
    { name: "primary_color", label: "Primary" },
    { name: "accent_color", label: "Accent" },
    { name: "header_bg_color", label: "Header" },
    { name: "footer_bg_color", label: "Content surface" },
  ];

  const API = {
    layout: "/siteconfig/theme-experience/builder/api/layout/",
    publish: "/siteconfig/theme-experience/builder/api/publish/",
    preview: "/siteconfig/theme-experience/builder/api/preview/",
    publishLog: "/siteconfig/theme-experience/builder/api/publish-log/",
    rollback: "/siteconfig/theme-experience/builder/api/rollback/",
  };

  const FALLBACK_BLOCKS = [
    { id: "sidebar", type: "sidebar", label: "Navigation sidebar", enabled: true },
    { id: "hero", type: "hero", label: "Hero header", enabled: true },
    { id: "metrics", type: "metrics", label: "Metric cards", enabled: true },
    { id: "chart", type: "chart", label: "Activity chart", enabled: true },
    { id: "announcement", type: "announcement", label: "Announcement bar", enabled: true },
    { id: "cta", type: "cta", label: "Call to action", enabled: true },
    { id: "footer", type: "footer", label: "Footer strip", enabled: false },
  ];
  let layout = { version: 1, surface: "light", blocks: FALLBACK_BLOCKS.map((b) => ({ ...b })) };
  let dragId = null;
  const history = [];
  let historyIndex = -1;
  let autoSaveTimer = null;

  const readLayout = () => {
    if (!LAYOUT_EL) return null;
    try {
      return JSON.parse(LAYOUT_EL.textContent || "{}");
    } catch (_e) {
      return null;
    }
  };

  const setStatus = (msg) => {
    if (statusEl) statusEl.textContent = msg || "";
  };

  const getCsrf = () =>
    document.cookie.match(/(?:^|;\s*)csrftoken=([^;]+)/)?.[1] ||
    document.querySelector("[name=csrfmiddlewaretoken]")?.value ||
    "";

  const getField = (name) => document.getElementById(`id_${name}`);

  const collectColors = () => {
    const colors = {};
    TOKEN_FIELDS.forEach(({ name }) => {
      const val = getField(name)?.value;
      if (val) colors[name] = val;
    });
    return colors;
  };

  const parseHex = (hex) => {
    let value = String(hex || "").trim().replace(/^#/, "");
    if (value.length === 3) value = value.split("").map((c) => c + c).join("");
    if (value.length !== 6) return null;
    return [
      parseInt(value.slice(0, 2), 16),
      parseInt(value.slice(2, 4), 16),
      parseInt(value.slice(4, 6), 16),
    ];
  };

  const luminance = (rgb) => {
    const channel = (c) => {
      const n = c / 255;
      return n <= 0.03928 ? n / 12.92 : ((n + 0.055) / 1.055) ** 2.4;
    };
    return 0.2126 * channel(rgb[0]) + 0.7152 * channel(rgb[1]) + 0.0722 * channel(rgb[2]);
  };

  const contrastRatio = (a, b) => {
    const rgbA = parseHex(a);
    const rgbB = parseHex(b);
    if (!rgbA || !rgbB) return 0;
    const l1 = luminance(rgbA);
    const l2 = luminance(rgbB);
    const lighter = Math.max(l1, l2);
    const darker = Math.min(l1, l2);
    return (lighter + 0.05) / (darker + 0.05);
  };

  const syncContrastMeter = () => {
    if (!contrastMeter || !contrastValue) return;
    const primary = getField("primary_color")?.value;
    const accent = getField("accent_color")?.value;
    if (!primary || !accent) {
      contrastMeter.hidden = true;
      return;
    }
    const ratio = contrastRatio(primary, accent);
    const ok = ratio >= CONTRAST_PAIR_MIN;
    contrastMeter.hidden = false;
    contrastMeter.dataset.ok = ok ? "true" : "false";
    contrastValue.textContent = `${ratio.toFixed(1)}:1`;
  };

  const ensureHiddenFields = () => {
    TOKEN_FIELDS.forEach(({ name }) => {
      if (getField(name)) return;
      const input = document.createElement("input");
      input.type = "color";
      input.id = `id_${name}`;
      input.name = name;
      input.value = "#0d6efd";
      input.className = "visually-hidden";
      input.setAttribute("aria-hidden", "true");
      document.body.appendChild(input);
    });
  };

  const buildTokenPanel = () => {
    if (!tokenPanel) return;
    tokenPanel.innerHTML = TOKEN_FIELDS.map(
      ({ name, label }) => `
        <label class="form-label small mb-1" for="tb_${name}">${label}</label>
        <input type="color" class="form-control form-control-color w-100 mb-2" id="tb_${name}" data-field="${name}" />
      `
    ).join("");
    TOKEN_FIELDS.forEach(({ name }) => {
      const tb = document.getElementById(`tb_${name}`);
      const hidden = getField(name);
      if (!tb || !hidden) return;
      tb.value = hidden.value || "#0d6efd";
      tb.addEventListener("input", () => {
        hidden.value = tb.value;
        hidden.dispatchEvent(new Event("input", { bubbles: true }));
        pushHistory();
        renderCanvas();
        scheduleAutoSave();
        document.dispatchEvent(new CustomEvent("rmc-theme-builder-colors"));
        syncContrastMeter();
      });
    });
    syncContrastMeter();
  };

  const cloneLayout = () => JSON.parse(JSON.stringify(layout));

  const pushHistory = () => {
    const snap = cloneLayout();
    if (historyIndex >= 0 && JSON.stringify(history[historyIndex]) === JSON.stringify(snap)) {
      return;
    }
    history.splice(historyIndex + 1);
    history.push(snap);
    if (history.length > 40) history.shift();
    historyIndex = history.length - 1;
    syncHistoryButtons();
  };

  const applyLayout = (snap) => {
    if (!snap || !Array.isArray(snap.blocks)) return;
    layout = snap;
    renderBlockList();
    setSurface(layout.surface || "light");
  };

  const syncHistoryButtons = () => {
    if (undoBtn) undoBtn.disabled = historyIndex <= 0;
    if (redoBtn) redoBtn.disabled = historyIndex < 0 || historyIndex >= history.length - 1;
  };

  const setSurface = (surface) => {
    const normalized = surface === "dark" ? "dark" : "light";
    layout.surface = normalized;
    if (canvas) canvas.dataset.previewSurface = normalized;
    const previewDevice = document.querySelector(".preview-device");
    if (previewDevice) previewDevice.dataset.previewTheme = normalized;
    surfaceButtons.forEach((btn) => {
      btn.classList.toggle("active", btn.dataset.previewSurface === normalized);
    });
    document.dispatchEvent(
      new CustomEvent("rmc-preview-surface-change", { detail: { surface: normalized } })
    );
    renderCanvas();
  };

  const renderBlockList = () => {
    if (!blockList) return;
    blockList.innerHTML = "";
    layout.blocks.forEach((block) => {
      const li = document.createElement("li");
      li.className = "theme-builder-block-item";
      li.draggable = true;
      li.dataset.blockId = block.id;
      li.innerHTML = `
        <span class="theme-builder-drag-handle" aria-hidden="true">⋮⋮</span>
        <span class="flex-grow-1">${block.label || block.type}</span>
        <button type="button" class="btn btn-link btn-sm p-0" data-toggle-block="${block.id}" aria-pressed="${block.enabled ? "true" : "false"}">
          ${block.enabled ? "On" : "Off"}
        </button>
      `;
      li.addEventListener("dragstart", (e) => {
        dragId = block.id;
        e.dataTransfer.effectAllowed = "move";
      });
      li.addEventListener("dragover", (e) => e.preventDefault());
      li.addEventListener("drop", (e) => {
        e.preventDefault();
        const targetId = li.dataset.blockId;
        if (!dragId || dragId === targetId) return;
        const from = layout.blocks.findIndex((b) => b.id === dragId);
        const to = layout.blocks.findIndex((b) => b.id === targetId);
        if (from < 0 || to < 0) return;
        const [moved] = layout.blocks.splice(from, 1);
        layout.blocks.splice(to, 0, moved);
        dragId = null;
        pushHistory();
        renderBlockList();
        renderCanvas();
        scheduleAutoSave();
      });
      li.querySelector("[data-toggle-block]")?.addEventListener("click", () => {
        block.enabled = !block.enabled;
        pushHistory();
        renderBlockList();
        renderCanvas();
        scheduleAutoSave();
      });
      blockList.appendChild(li);
    });
  };

  const blockHtml = (block) => {
    if (!block.enabled) return "";
    const primary =
      getField("primary_color")?.value ||
      getComputedStyle(document.documentElement).getPropertyValue("--school-primary").trim() ||
      "#0d6efd";
    const accent =
      getField("accent_color")?.value ||
      getComputedStyle(document.documentElement).getPropertyValue("--school-accent").trim() ||
      "#198754";
    const map = {
      sidebar: `<aside class="tb-sidebar" style="background:${primary}"><span>Nav</span><span>Students</span></aside>`,
      hero: `<header class="tb-hero"><strong>Welcome back</strong><p class="mb-0 small">District overview</p></header>`,
      metrics:
        '<div class="tb-metrics"><article>98% attendance</article><article>3 approvals</article><article>2 invoices</article></div>',
      chart:
        '<section class="tb-chart"><strong>Weekly activity</strong><div class="tb-bars" aria-hidden="true"><span></span><span></span><span></span></div></section>',
      announcement: `<div class="tb-announcement" style="border-color:${accent}">District announcement — review before publish</div>`,
      cta: `<section class="tb-cta" style="background:${accent}"><strong>Enroll for next term</strong><button type="button" class="btn btn-light btn-sm mt-2">Learn more</button></section>`,
      footer: `<footer class="tb-footer small">Powered by RunMyCampus</footer>`,
    };
    return map[block.type] || `<section class="tb-section">${block.label}</section>`;
  };

  const renderCanvas = () => {
    if (!canvas) return;
    canvas.dataset.previewSurface = layout.surface || "light";
    canvas.innerHTML = layout.blocks.map(blockHtml).join("");
  };

  const postJson = async (url, body) => {
    const resp = await fetch(url, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "X-CSRFToken": getCsrf(),
      },
      body: JSON.stringify(body),
      credentials: "same-origin",
    });
    const data = await resp.json().catch(() => ({}));
    if (!resp.ok) {
      const err = data.errors ? JSON.stringify(data.errors) : `HTTP ${resp.status}`;
      throw new Error(err);
    }
    return data;
  };

  const saveLayout = async (quiet) => {
    if (!quiet) setStatus("Saving…");
    try {
      await postJson(API.layout, { layout });
      if (!quiet) setStatus("Layout saved.");
    } catch (err) {
      if (!quiet) setStatus(`Save failed: ${err.message || err}`);
    }
  };

  const scheduleAutoSave = () => {
    if (autoSaveTimer) clearTimeout(autoSaveTimer);
    autoSaveTimer = setTimeout(() => saveLayout(true), 1800);
  };

  const renderPublishLog = (entries) => {
    if (!publishLogEl) return;
    const list = Array.isArray(entries) ? entries : [];
    if (!list.length) {
      publishLogEl.innerHTML = "<li class=\"text-muted\">No publishes yet.</li>";
      if (rollbackBtn) rollbackBtn.disabled = true;
      return;
    }
    const restorable = list.filter((e) => e && e.summary && e.summary.layout);
    if (rollbackBtn) rollbackBtn.disabled = restorable.length < 2;
    publishLogEl.innerHTML = list
      .slice(-5)
      .reverse()
      .map((entry) => {
        const at = (entry.at || "").replace("T", " ").slice(0, 16);
        const type = entry.type || "publish";
        const badge =
          type.indexOf("rollback") >= 0
            ? "text-bg-warning"
            : type.indexOf("tenant") >= 0 || type.indexOf("operator") >= 0
              ? "text-bg-primary"
              : "text-bg-secondary";
        return `<li><span class="badge ${badge} me-1">${type}</span><span class="text-muted">${at}</span></li>`;
      })
      .join("");
  };

  const refreshPublishLog = async () => {
    try {
      const resp = await fetch(API.publishLog, { credentials: "same-origin" });
      const data = await resp.json();
      if (resp.ok) renderPublishLog(data.entries);
    } catch (_e) {
      /* non-blocking */
    }
  };

  const publishLayout = async () => {
    setStatus("Publishing…");
    try {
      const data = await postJson(API.publish, {
        layout,
        colors: collectColors(),
        publish: true,
        preview_confirmed: true,
      });
      if (data.brand_adjusted) {
        setStatus("Published (contrast guard adjusted some tokens).");
      } else {
        setStatus("Published.");
      }
      await refreshPublishLog();
    } catch (err) {
      setStatus(`Publish failed: ${err.message || err}`);
    }
  };

  const rollbackPublish = async () => {
    if (
      rollbackBtn &&
      !window.confirm(
        "Restore the previous published theme on this plane? Unsaved draft changes stay in the editor."
      )
    ) {
      return;
    }
    setStatus("Rolling back…");
    try {
      const data = await postJson(API.rollback, {});
      if (data.layout) {
        layout = data.layout;
        pushHistory();
        renderBlockList();
        renderCanvas();
      }
      if (data.colors) {
        TOKEN_FIELDS.forEach(({ name }) => {
          const field = getField(name);
          if (field && data.colors[name]) field.value = data.colors[name];
        });
        document.dispatchEvent(new CustomEvent("rmc-theme-builder-colors"));
      }
      setStatus("Restored previous publish.");
      await refreshPublishLog();
    } catch (err) {
      setStatus(`Rollback failed: ${err.message || err}`);
    }
  };

  const openPreview = async () => {
    setStatus("Opening preview…");
    try {
      const data = await postJson(API.preview, {
        colors: collectColors(),
        surface: layout.surface || "light",
      });
      if (data.preview_url) window.open(data.preview_url, "_blank", "noopener,noreferrer");
      setStatus("Preview opened in a new tab.");
    } catch (err) {
      setStatus(`Preview failed: ${err.message || err}`);
    }
  };

  const wireHubHeroPreview = () => {
    const hero = document.querySelector("[data-rmc-theme-hub-hero]");
    const glance = document.getElementById("theme-hub-glance");
    if (!hero) return;
    const mini = hero.querySelector(".theme-hub-mini-preview");
    if (glance) {
      const primary = glance.style.getPropertyValue("--hub-preview-primary");
      const accent = glance.style.getPropertyValue("--hub-preview-accent");
      if (primary) hero.style.setProperty("--hub-preview-primary", primary.trim());
      if (accent) hero.style.setProperty("--hub-preview-accent", accent.trim());
    }
    hero.querySelectorAll(".preview-surface-btn[data-preview-surface]").forEach((btn) => {
      btn.addEventListener("click", () => {
        const surface = btn.dataset.previewSurface || "light";
        if (mini) mini.dataset.previewSurface = surface;
        hero.querySelectorAll(".preview-surface-btn").forEach((b) => {
          b.classList.toggle("active", b === btn);
        });
        if (glance) {
          glance.querySelectorAll(".preview-surface-btn").forEach((b) => {
            b.classList.toggle("active", b.dataset.previewSurface === surface);
          });
        }
      });
    });
    if (glance) {
      glance.querySelectorAll(".preview-surface-btn[data-preview-surface]").forEach((btn) => {
        btn.addEventListener("click", () => {
          const surface = btn.dataset.previewSurface || "light";
          if (mini) mini.dataset.previewSurface = surface;
          glance.querySelectorAll(".preview-surface-btn").forEach((b) => {
            b.classList.toggle("active", b === btn);
          });
          hero.querySelectorAll(".preview-surface-btn").forEach((b) => {
            b.classList.toggle("active", b.dataset.previewSurface === surface);
          });
        });
      });
    }
  };

  document.addEventListener("DOMContentLoaded", () => {
    const initial = readLayout();
    if (initial && typeof initial === "object") {
      layout = { ...layout, ...initial };
      if (Array.isArray(initial.blocks) && initial.blocks.length) {
        layout.blocks = initial.blocks.map((b) => ({ ...b }));
      }
    }
    if (!Array.isArray(layout.blocks) || !layout.blocks.length) {
      layout.blocks = FALLBACK_BLOCKS.map((b) => ({ ...b }));
    }
    ensureHiddenFields();
    buildTokenPanel();
    pushHistory();
    renderBlockList();
    setSurface(layout.surface || "light");
    surfaceButtons.forEach((btn) => {
      btn.addEventListener("click", () => {
        setSurface(btn.dataset.previewSurface || "light");
        pushHistory();
        scheduleAutoSave();
      });
    });
    if (saveBtn) saveBtn.addEventListener("click", () => saveLayout(false));
    if (publishBtn) publishBtn.addEventListener("click", publishLayout);
    if (rollbackBtn) rollbackBtn.addEventListener("click", rollbackPublish);
    if (previewBtn) previewBtn.addEventListener("click", openPreview);
    refreshPublishLog();
    if (undoBtn) {
      undoBtn.addEventListener("click", () => {
        if (historyIndex <= 0) return;
        historyIndex -= 1;
        applyLayout(history[historyIndex]);
        syncHistoryButtons();
        scheduleAutoSave();
      });
    }
    if (redoBtn) {
      redoBtn.addEventListener("click", () => {
        if (historyIndex >= history.length - 1) return;
        historyIndex += 1;
        applyLayout(history[historyIndex]);
        syncHistoryButtons();
        scheduleAutoSave();
      });
    }
    document.addEventListener("rmc-theme-builder-colors", () => {
      renderCanvas();
      syncContrastMeter();
    });
    wireHubHeroPreview();
  });
})();
