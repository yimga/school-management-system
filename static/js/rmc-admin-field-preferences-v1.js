(function () {
  "use strict";

  const dataNode = document.getElementById("rmc-admin-field-contract");
  if (!dataNode) return;

  let contract;
  try {
    contract = JSON.parse(dataNode.textContent || "{}");
  } catch (_) {
    return;
  }

  const picker = document.querySelector("[data-rmc-admin-field-picker]");
  const status = picker && picker.querySelector("[data-rmc-field-picker-status]");
  const required = new Set(contract.required || []);
  const optional = new Set((contract.optional || []).map((item) => item.name));
  const recommended = new Set(contract.recommended || []);
  const recommendedLabel = contract.recommendedLabel || "Recommended";
  const systemHidden = new Set(contract.systemHidden || []);
  const pendingKey = [
    "rmc-admin-field-preferences-pending-v1",
    contract.host,
    contract.adminSite,
    contract.model,
    contract.mode,
  ].join(":");

  function escapeName(value) {
    if (window.CSS && typeof window.CSS.escape === "function") {
      return window.CSS.escape(value);
    }
    return String(value).replace(/[^a-zA-Z0-9_-]/g, "\\$&");
  }

  function fieldNodes(name) {
    return Array.from(
      document.querySelectorAll(
        '[data-rmc-admin-field-name="' + escapeName(name) + '"]'
      )
    );
  }

  function mustRemainVisible(name) {
    if (required.has(name)) return true;
    return fieldNodes(name).some((node) => {
      if (node.querySelector(".errors, .errorlist, [aria-invalid='true']")) return true;
      return Array.from(node.querySelectorAll("input, select, textarea")).some(
        (input) => input.required || input.getAttribute("aria-required") === "true"
      );
    });
  }

  function setFieldVisible(name, visible) {
    const safeVisible = visible || mustRemainVisible(name);
    fieldNodes(name).forEach((node) => {
      node.hidden = !safeVisible;
      node.setAttribute("aria-hidden", safeVisible ? "false" : "true");
      node.toggleAttribute("data-rmc-field-preference-hidden", !safeVisible);
    });
    const input =
      picker && picker.querySelector('[data-rmc-optional-field="' + escapeName(name) + '"]');
    if (input && mustRemainVisible(name)) {
      input.checked = true;
      input.disabled = true;
      input.title = "Required by the current form state";
    } else if (input) {
      input.disabled = false;
      input.removeAttribute("title");
    }
  }

  function decorateRecommendedFields() {
    recommended.forEach((name) => {
      fieldNodes(name).forEach((node) => {
        node.setAttribute("data-rmc-field-recommended", "true");
        const label = node.querySelector("label");
        if (!label || label.querySelector("[data-rmc-recommended-badge]")) return;
        const badge = document.createElement("span");
        badge.className = "rmc-admin-field-recommended-badge";
        badge.dataset.rmcRecommendedBadge = "1";
        badge.textContent = recommendedLabel;
        label.appendChild(badge);
      });
    });
  }

  function applyHidden(hiddenNames) {
    const hidden = new Set(hiddenNames || []);
    optional.forEach((name) => setFieldVisible(name, !hidden.has(name)));
    systemHidden.forEach((name) => setFieldVisible(name, false));
    document.dispatchEvent(
      new CustomEvent("rmc:admin-field-visibility", {
        detail: { model: contract.model, hidden: Array.from(hidden) },
      })
    );
  }

  function selectedHidden() {
    if (!picker) return [];
    return Array.from(picker.querySelectorAll("[data-rmc-optional-field]"))
      .filter((input) => !input.checked && !input.disabled)
      .map((input) => input.value)
      .filter((name) => optional.has(name) && !required.has(name));
  }

  function csrfToken() {
    const input = document.querySelector("input[name='csrfmiddlewaretoken']");
    return input ? input.value : "";
  }

  function report(message, state) {
    if (!status) return;
    status.textContent = message;
    status.dataset.state = state || "idle";
  }

  async function persist(hidden, reset) {
    const body = {
      model: contract.model,
      mode: contract.mode,
      hidden: hidden,
      reset: Boolean(reset),
    };
    applyHidden(reset ? [] : hidden);
    report("Saving…", "saving");
    try {
      const response = await fetch(contract.endpoint, {
        method: "POST",
        credentials: "same-origin",
        headers: {
          "Content-Type": "application/json",
          "X-CSRFToken": csrfToken(),
        },
        body: JSON.stringify(body),
      });
      const payload = await response.json();
      if (!response.ok || !payload.ok) {
        throw new Error(typeof payload.error === "string" ? payload.error : "Save failed");
      }
      localStorage.removeItem(pendingKey);
      applyHidden(payload.hidden || []);
      report("Saved for this admin surface.", "saved");
    } catch (error) {
      // The local edge database is authoritative. This envelope is only a retry
      // queue and never grants permission or bypasses server validation.
      localStorage.setItem(pendingKey, JSON.stringify(body));
      report("Saved locally; server sync will retry when online.", "pending");
    }
  }

  let timer = 0;
  function schedulePersist() {
    window.clearTimeout(timer);
    timer = window.setTimeout(() => persist(selectedHidden(), false), 180);
  }

  if (picker) {
    picker.querySelectorAll("[data-rmc-optional-field]").forEach((input) => {
      input.addEventListener("change", schedulePersist);
    });
    picker.querySelectorAll("[data-rmc-field-preset]").forEach((button) => {
      button.addEventListener("click", () => {
        const preset = button.dataset.rmcFieldPreset;
        const inputs = Array.from(
          picker.querySelectorAll("[data-rmc-optional-field]")
        );
        if (preset === "reset" || preset === "all") {
          inputs.forEach((input) => {
            input.checked = true;
          });
          persist([], preset === "reset");
          return;
        }
        if (preset === "recommended") {
          inputs.forEach((input) => {
            input.checked = recommended.has(input.value) || input.disabled;
          });
          persist(selectedHidden(), false);
        }
      });
    });
  }

  applyHidden(contract.hidden || []);
  decorateRecommendedFields();

  // Alpine/Unfold can change required state after a dependency changes. Re-run
  // the safety rule so a now-mandatory field is immediately restored.
  const form = document.querySelector("#content-main form");
  if (form && window.MutationObserver) {
    const observer = new MutationObserver(() => {
      applyHidden(selectedHidden());
      decorateRecommendedFields();
    });
    observer.observe(form, {
      subtree: true,
      attributes: true,
      attributeFilter: ["required", "aria-required", "class", "style"],
    });
  }

  async function retryPending() {
    const raw = localStorage.getItem(pendingKey);
    if (!raw || !navigator.onLine) return;
    try {
      const body = JSON.parse(raw);
      await persist(body.hidden || [], Boolean(body.reset));
    } catch (_) {
      localStorage.removeItem(pendingKey);
    }
  }
  window.addEventListener("online", retryPending);
  retryPending();
})();
