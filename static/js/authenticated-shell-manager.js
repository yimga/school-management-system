(function () {
  function readPlatformSearchUrl() {
    if (window.RMCPlatformSurface && window.RMCPlatformSurface.url) {
      return window.RMCPlatformSurface.url("search");
    }
    return "";
  }

  function ready(fn) {
    if (document.readyState === "loading") {
      document.addEventListener("DOMContentLoaded", fn);
      return;
    }
    fn();
  }

  function wireOneSearch(input, results) {
    if (!input || !results) return;
    if (input.getAttribute("data-rmc-shell-search-wired") === "1") return;
    input.setAttribute("data-rmc-shell-search-wired", "1");

    var debounce = null;
    var activeIndex = -1;

    function esc(value) {
      return String(value || "")
        .replace(/&/g, "&amp;")
        .replace(/</g, "&lt;")
        .replace(/>/g, "&gt;");
    }

    function optionNodes() {
      return Array.prototype.slice.call(
        results.querySelectorAll(".cp-search-result-item, .dropdown-item")
      );
    }

    function openPanel() {
      results.classList.add("show");
      results.setAttribute("aria-hidden", "false");
      input.setAttribute("aria-expanded", "true");
    }

    function closePanel() {
      results.classList.remove("show");
      results.setAttribute("aria-hidden", "true");
      input.setAttribute("aria-expanded", "false");
      activeIndex = -1;
      input.removeAttribute("aria-activedescendant");
    }

    function setActive(index) {
      var options = optionNodes();
      options.forEach(function (el, i) {
        var on = i === index;
        el.classList.toggle("is-active", on);
        el.setAttribute("aria-selected", on ? "true" : "false");
        if (on) {
          if (!el.id) el.id = results.id + "-opt-" + i;
          input.setAttribute("aria-activedescendant", el.id);
          el.scrollIntoView({ block: "nearest" });
        }
      });
      activeIndex = index;
    }

    function render(data) {
      var list = data && Array.isArray(data.results) ? data.results : [];
      if (!list.length) {
        results.innerHTML =
          '<div class="cp-search-empty px-3 py-2 text-muted small" role="status">No results</div>';
      } else {
        results.innerHTML = list
          .map(function (item, idx) {
            var url = item.url || "#";
            var title = esc(item.title);
            var desc = esc(item.description);
            var id = results.id + "-opt-" + idx;
            return (
              '<a id="' +
              id +
              '" class="dropdown-item cp-search-result-item" role="option" aria-selected="false" href="' +
              url +
              '"><strong>' +
              title +
              "</strong>" +
              (desc
                ? '<br><span class="small text-secondary">' + desc + "</span>"
                : "") +
              "</a>"
            );
          })
          .join("");
      }
      openPanel();
      activeIndex = -1;
    }

    function search() {
      var base = readPlatformSearchUrl();
      if (!base) return;
      var sep = base.indexOf("?") >= 0 ? "&" : "?";
      var q = String(input.value || "").trim();
      if (!q.length) {
        fetch(base + sep + "q=", { headers: { Accept: "application/json" } })
          .then(function (res) {
            return res.json();
          })
          .then(render)
          .catch(function () {
            render({ results: [] });
          });
        return;
      }
      if (q.length < 2) {
        results.innerHTML = "";
        closePanel();
        return;
      }
      results.innerHTML =
        '<div class="cp-search-empty px-3 py-2 text-muted small" role="status">Searching…</div>';
      openPanel();
      fetch(base + sep + "q=" + encodeURIComponent(q), {
        headers: { Accept: "application/json" },
      })
        .then(function (res) {
          return res.json();
        })
        .then(render)
        .catch(function () {
          render({ results: [] });
        });
    }

    input.setAttribute("role", "combobox");
    input.setAttribute("aria-autocomplete", "list");
    input.setAttribute("aria-controls", results.id);
    input.setAttribute("aria-expanded", "false");
    results.setAttribute("role", "listbox");
    results.setAttribute("aria-hidden", "true");

    input.addEventListener("input", function () {
      clearTimeout(debounce);
      debounce = setTimeout(search, 220);
    });
    input.addEventListener("focus", search);
    input.addEventListener("keydown", function (e) {
      var options = optionNodes();
      if (e.key === "Escape") {
        closePanel();
        input.blur();
        return;
      }
      if (e.key === "ArrowDown") {
        if (!options.length) return;
        e.preventDefault();
        setActive(activeIndex < options.length - 1 ? activeIndex + 1 : 0);
        return;
      }
      if (e.key === "ArrowUp") {
        if (!options.length) return;
        e.preventDefault();
        setActive(activeIndex > 0 ? activeIndex - 1 : options.length - 1);
        return;
      }
      if (e.key === "Enter") {
        var target = activeIndex >= 0 ? options[activeIndex] : options[0];
        if (target && results.classList.contains("show")) {
          e.preventDefault();
          target.click();
          closePanel();
        }
      }
    });
    document.addEventListener("click", function (e) {
      if (!input.contains(e.target) && !results.contains(e.target)) {
        closePanel();
      }
    });
    /* Ctrl+K opens the Spotlight command palette (rmc-command-palette.js).
       Header typeahead stays under-input; kbd chip on the field is "/" focus. */
  }

  function wireManagerSearch() {
    var pairs = [
      [
        document.getElementById("cpSearchInput"),
        document.getElementById("cpSearchResults"),
      ],
      [
        document.getElementById("cpSearchInputAdmin"),
        document.getElementById("cpSearchResultsAdmin"),
      ],
      [
        document.getElementById("cpSearchInputMobile") ||
          document.querySelector('[data-cp-search-mobile="1"]'),
        document.getElementById("cpSearchResultsMobile"),
      ],
    ];
    pairs.forEach(function (pair) {
      wireOneSearch(pair[0], pair[1]);
    });
  }

  function wireManagerRecentNav() {
    var wrap = document.getElementById("cpNavRecentWrap");
    var list = document.getElementById("cpNavRecentList");
    if (!wrap || !list) return;

    var RECENT_KEY = "runmycampus-cp-recent";
    var RECENT_MAX = 5;

    function isTrackedSurfacePath(path) {
      if (!path) return false;
      if (path === "/super" || path.indexOf("/super/") === 0) return true;
      if (path === "/studio" || path.indexOf("/studio/") === 0) return true;
      if (path === "/admin" || path.indexOf("/admin/") === 0) return true;
      return false;
    }
    function getRecent() {
      try {
        var raw = sessionStorage.getItem(RECENT_KEY);
        if (!raw) return [];
        var arr = JSON.parse(raw);
        return Array.isArray(arr) ? arr.slice(0, RECENT_MAX) : [];
      } catch (e) {
        return [];
      }
    }
    function setRecent(arr) {
      try {
        sessionStorage.setItem(RECENT_KEY, JSON.stringify(arr.slice(0, RECENT_MAX)));
      } catch (e) {}
    }
    function pushRecent(path, title) {
      if (!isTrackedSurfacePath(path)) return;
      var items = getRecent().filter(function (it) {
        return it.url !== path;
      });
      items.unshift({ url: path, label: (title || path).trim() });
      setRecent(items);
    }
    function renderRecent() {
      var items = getRecent();
      list.innerHTML = "";
      items.forEach(function (it) {
        var li = document.createElement("li");
        li.className = "nav-item";
        var a = document.createElement("a");
        a.className =
          "nav-link text-white d-flex align-items-center flex-grow-1 cp-nav-recent-link";
        a.href = it.url;
        a.textContent = it.label || it.url;
        if (window.location.pathname === it.url) a.classList.add("active");
        li.appendChild(a);
        list.appendChild(li);
      });
      wrap.style.display = items.length ? "block" : "none";
    }

    pushRecent(window.location.pathname, document.title);
    renderRecent();
    window.cpRenderRecent = renderRecent;
  }

  ready(function () {
    wireManagerSearch();
    wireManagerRecentNav();
  });
})();
