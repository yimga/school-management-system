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

  function surface() {
    var root = rootEl();
    return (root && root.getAttribute("data-deflection-surface")) || "support_ticket";
  }

  function csrfToken() {
    var input = document.querySelector("[name=csrfmiddlewaretoken]");
    return input ? input.value : "";
  }

  function panel() {
    return document.getElementById("rmc-support-deflection-panel");
  }

  function setBlocking(form, blocking) {
    if (!form) return;
    form.dataset.deflectionBlocking = blocking ? "1" : "0";
    var submit = form.querySelector('button[type="submit"]');
    if (submit) {
      submit.disabled = !!blocking;
      submit.setAttribute("aria-disabled", blocking ? "true" : "false");
    }
  }

  function renderArticles(data) {
    var el = panel();
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
        postAck(data, "opened");
        clearBlocking();
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
      postAck(data, "dismissed");
      clearBlocking();
    });
    el.appendChild(dismiss);
  }

  function clearBlocking() {
    document.querySelectorAll("form[data-deflection-form]").forEach(function (form) {
      setBlocking(form, false);
      var ack = form.querySelector("[data-deflection-ack]");
      if (ack) ack.value = "1";
    });
  }

  function postAck(data, outcome) {
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
        surface: surface(),
      }),
    }).catch(function () {});
  }

  function queryFromForm(form) {
    var subject = form.querySelector("[name=subject], [name=title]");
    var message = form.querySelector(
      "[name=message], [name=description], [name=body], [name=problem_statement]"
    );
    var q = form.querySelector("[name=q], [data-deflection-query]");
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
      renderArticles(null);
      setBlocking(form, false);
      return;
    }
    var params = new URLSearchParams({
      q: q,
      surface: surface(),
    });
    fetch(url + "?" + params.toString(), { credentials: "same-origin" })
      .then(function (r) {
        return r.json();
      })
      .then(function (data) {
        data.query = q;
        renderArticles(data);
        setBlocking(form, !!data.blocking);
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
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
