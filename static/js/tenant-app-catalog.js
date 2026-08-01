(function () {
  "use strict";

  function textElement(tag, className, value) {
    var node = document.createElement(tag);
    if (className) node.className = className;
    node.textContent = value == null ? "" : String(value);
    return node;
  }

  function sameOriginHref(value) {
    try {
      var url = new URL(value || "", window.location.origin);
      return url.origin === window.location.origin ? url.href : "#";
    } catch (_error) {
      return "#";
    }
  }

  function applyImageFallback(image, fallback) {
    if (!image || !fallback) return;
    image.addEventListener("error", function () {
      if (image.src !== fallback) image.src = fallback;
    }, { once: true });
  }

  function initialiseCatalog() {
    var bar = document.querySelector('[data-region="catalog-search-bar"]');
    var grid = document.getElementById("tenant-catalog-grid");
    if (!bar || !grid) return;
    var apiUrl = bar.getAttribute("data-catalog-api-url") || "/marketplace/api/v1/catalog/";
    var fallback = bar.getAttribute("data-catalog-fallback-url") || "";
    var counter = bar.querySelector("[data-catalog-result-count]");
    var serverCards = Array.from(grid.children);
    var debounce = null;

    document.querySelectorAll("[data-rmc-catalog-image]").forEach(function (image) {
      applyImageFallback(image, image.getAttribute("data-rmc-fallback-src") || fallback);
    });

    function render(apps) {
      var fragment = document.createDocumentFragment();
      if (counter) counter.textContent = apps.length + " result" + (apps.length === 1 ? "" : "s");
      if (!apps.length) fragment.appendChild(textElement("div", "text-muted small py-3", "No apps match your filters."));
      apps.forEach(function (app) {
        var card = document.createElement("a");
        card.className = "proof-app-card rmc-mkt-app-card rmc-reveal";
        card.href = sameOriginHref(app.detail_url);
        card.setAttribute("data-rmc-mkt-app-card-js", "1");
        var body = document.createElement("div");
        body.className = "proof-app-card-body";
        if (app.preview_image_url) {
          var image = document.createElement("img");
          image.src = String(app.preview_image_url);
          image.alt = "";
          image.className = "img-fluid mb-2";
          image.loading = "lazy";
          applyImageFallback(image, fallback);
          body.appendChild(image);
        }
        body.appendChild(textElement("h3", "h6 mb-1", app.name));
        body.appendChild(textElement("div", "small text-muted mb-1", app.publisher_name));
        if (app.short_description) body.appendChild(textElement("p", "small mb-2", app.short_description));
        body.appendChild(textElement("div", "small", "★ " + (app.rating_average || 0) + " (" + (app.rating_count || 0) + ") · " + (app.active_installs || 0) + " installs · v" + (app.current_version || "")));
        card.appendChild(body);
        fragment.appendChild(card);
      });
      grid.replaceChildren(fragment);
    }

    function restore() {
      grid.replaceChildren.apply(grid, serverCards);
    }

    function refresh() {
      var params = new URLSearchParams({
        q: bar.querySelector("[data-catalog-search-input]").value || "",
        pricing: bar.querySelector('[data-catalog-facet="pricing"]').value || "",
        sort: bar.querySelector('[data-catalog-facet="sort"]').value || "popular"
      });
      var minRating = bar.querySelector('[data-catalog-facet="min_rating"]').value || "";
      if (minRating) params.set("min_rating", minRating);
      fetch(apiUrl + "?" + params.toString(), { credentials: "same-origin", headers: { Accept: "application/json" } })
        .then(function (response) { if (!response.ok) throw new Error(String(response.status)); return response.json(); })
        .then(function (data) { render(Array.isArray(data.apps) ? data.apps : []); })
        .catch(restore);
    }

    bar.addEventListener("input", function () { window.clearTimeout(debounce); debounce = window.setTimeout(refresh, 220); });
    bar.addEventListener("change", refresh);
  }

  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", initialiseCatalog);
  else initialiseCatalog();
}());
