/**
 * Pre-ticket KB deflection gate (vector similarity >= server threshold).
 * Unified across support, help center, and contact surfaces (batch 1339+).
 */
(function () {
  "use strict";

  function rootEl() {
    return document.querySelector("[data-support-deflection-url]");
  }

  function deflectionUrl() {
    var root = rootEl();
    return root ? root.getAttribute("data-support-deflection-url") : "";
  }

  function ackUrl() {
    var root = rootEl();
    return root ? root.getAttribute("data-support-deflection-ack-url") : "";
  }

  function surfaceForForm(form) {
    if (!form) return surface();
    var wrap = form.closest("[data-support-deflection-url]");
    if (wrap && wrap.getAttribute("data-deflection-surface")) {
      return wrap.getAttribute("data-deflection-surface");
    }
    return surface();
  }

  function surface() {
    var root = rootEl();
    return (root && root.getAttribute("data-deflection-surface")) || "support_ticket";
  }

  function csrfToken() {
    var input = document.querySelector("[name=csrfmiddlewaretoken]");
    return input ? input.value : "";
  }

  function panelForForm(form) {
    var wrap =
      (form && form.closest("[data-support-deflection-url]")) || rootEl();
    return wrap ? wrap.querySelector(".rmc-support-deflection-panel") : null;
  }

  function setBlocking(form, blocking) {
    if (!form) return;
    if (form.getAttribute("method") && form.getAttribute("method").toLowerCase() === "get") {
      return;
    }
    form.dataset.deflectionBlocking = blocking ? "1" : "0";
    var submit = form.querySelector('button[type="submit"]');
    if (submit) {
      submit.disabled = !!blocking;
      submit.setAttribute("aria-disabled", blocking ? "true" : "false");
    }
  }

  function renderArticles(form, data) {
    var el = panelForForm(form);
    if (!el) return;
    el.innerHTML = "";
    if (!data || !data.articles || !data.articles.length) {
      el.classList.add("d-none");
      return;
    }
    el.classList.remove("d-none");
    var title = document.createElement("p");
    title.className = "fw-semibold mb-2";
    title.textContent = "These articles may answer your question:";
    el.appendChild(title);
    var list = document.createElement("ul");
    list.className = "list-unstyled mb-2";
    data.articles.forEach(function (row) {
      var li = document.createElement("li");
      li.className = "mb-1";
      var a = document.createElement("a");
      a.href = row.url || "#";
      a.textContent = (row.title || "Article") + (row.score ? " (" + row.score + ")" : "");
      a.addEventListener("click", function () {
        postAck(form, data, "opened");
        clearBlocking(form);
      });
      li.appendChild(a);
      list.appendChild(li);
    });
    el.appendChild(list);
    var dismiss = document.createElement("button");
    dismiss.type = "button";
    dismiss.className = "btn btn-sm btn-outline-secondary";
    dismiss.textContent = "Continue anyway";
    dismiss.addEventListener("click", function () {
      postAck(form, data, "dismissed");
      clearBlocking(form);
    });
    el.appendChild(dismiss);
  }

  function clearBlocking(form) {
    if (form) {
      setBlocking(form, false);
      var ack = form.querySelector("[data-deflection-ack]");
      if (ack) ack.value = "1";
      return;
    }
    document.querySelectorAll("form[data-deflection-form]").forEach(function (f) {
      setBlocking(f, false);
      var ack = f.querySelector("[data-deflection-ack]");
      if (ack) ack.value = "1";
    });
  }

  function postAck(form, data, outcome) {
    var url = ackUrl();
    if (!url) return;
    fetch(url, {
      method: "POST",
      credentials: "same-origin",
      headers: {
        "Content-Type": "application/json",
        "X-CSRFToken": csrfToken(),
      },
      body: JSON.stringify({
        outcome: outcome,
        query: data.query || "",
        articles: data.articles || [],
        surface: surfaceForForm(form),
      }),
    }).catch(function () {});
  }

  function queryFromForm(form) {
    var subject = form.querySelector("[name=subject], [name=title]");
    var message = form.querySelector(
      "[name=message], [name=description], [name=body], [name=problem_statement]"
    );
    var q = form.querySelector("[name=q], [data-deflection-query], [data-rmc-help-search-input]");
    var parts = [];
    if (subject && subject.value) parts.push(subject.value);
    if (message && message.value) parts.push(message.value);
    if (q && q.value) parts.push(q.value);
    return parts.filter(Boolean).join(" ");
  }

  function fetchDeflection(form) {
    var url = deflectionUrl();
    if (!url || !form) return;
    var q = queryFromForm(form);
    if (q.length < 12) {
      renderArticles(form, null);
      setBlocking(form, false);
      return;
    }
    var params = new URLSearchParams({
      q: q,
      surface: surfaceForForm(form),
    });
    fetch(url + "?" + params.toString(), { credentials: "same-origin" })
      .then(function (r) {
        return r.json();
      })
      .then(function (data) {
        data.query = q;
        renderArticles(form, data);
        var block = !!data.blocking;
        if (form.getAttribute("method") && form.getAttribute("method").toLowerCase() === "get") {
          block = false;
        }
        setBlocking(form, block);
      })
      .catch(function () {
        setBlocking(form, false);
      });
  }

  function initForm(form) {
    if (!form || form.dataset.deflectionBound === "1") return;
    form.dataset.deflectionBound = "1";
    form.setAttribute("data-deflection-form", "1");
    var debounce;
    form.addEventListener("input", function () {
      clearTimeout(debounce);
      debounce = setTimeout(function () {
        fetchDeflection(form);
      }, 450);
    });
    form.addEventListener("submit", function (ev) {
      if (form.getAttribute("method") && form.getAttribute("method").toLowerCase() === "get") {
        return;
      }
      if (form.dataset.deflectionBlocking === "1") {
        var ack = form.querySelector("[data-deflection-ack]");
        if (!ack || ack.value !== "1") {
          ev.preventDefault();
        }
      }
    });
  }

  function init() {
    var supportForm = document.getElementById("support-request-form");
    if (supportForm) initForm(supportForm);
    document.querySelectorAll("form[data-deflection-form-auto]").forEach(initForm);
    document.querySelectorAll("form[data-rmc-help-search-input]").forEach(function (form) {
      if (!form.querySelector("[data-rmc-help-search-input]")) return;
      if (!form.dataset.deflectionBound) {
        if (!form.querySelector("[data-deflection-ack]")) {
          var ack = document.createElement("input");
          ack.type = "hidden";
          ack.name = "deflection_acknowledged";
          ack.setAttribute("data-deflection-ack", "1");
          ack.value = "0";
          form.appendChild(ack);
        }
        initForm(form);
      }
    });
    document.querySelectorAll("form").forEach(function (form) {
      if (form.querySelector("[data-rmc-help-search-input]") && !form.dataset.deflectionBound) {
        initForm(form);
      }
    });
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
