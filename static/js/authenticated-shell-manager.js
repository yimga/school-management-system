(function () {
  function ready(fn) {
    if (document.readyState === "loading") {
      document.addEventListener("DOMContentLoaded", fn);
      return;
    }
    fn();
  }

  function wireManagerSearch() {
    var input =
      document.getElementById("cpSearchInput") ||
      document.getElementById("cpSearchInputAdmin");
    var results =
      document.getElementById("cpSearchResults") ||
      document.getElementById("cpSearchResultsAdmin");
    if (!input || !results) return;
    if (input.getAttribute("data-rmc-shell-search-wired") === "1") return;
    input.setAttribute("data-rmc-shell-search-wired", "1");

    var debounce = null;
    function esc(value) {
      return String(value || "")
        .replace(/&/g, "&amp;")
        .replace(/</g, "&lt;")
        .replace(/>/g, "&gt;");
    }
    function render(data) {
      var list = data && Array.isArray(data.results) ? data.results : [];
      if (!list.length) {
        results.innerHTML = '<div class="px-3 py-2 text-muted small">No results</div>';
      } else {
        results.innerHTML = list
          .map(function (item) {
            var url = item.url || "#";
            var title = esc(item.title);
            var desc = esc(item.description);
            return (
              '<a class="dropdown-item" href="' +
              url +
              '"><strong>' +
              title +
              "</strong>" +
              (desc ? '<br><span class="small text-secondary">' + desc + "</span>" : "") +
              "</a>"
            );
          })
          .join("");
      }
      results.classList.add("show");
    }
    function search() {
      var q = String(input.value || "").trim();
      if (!q.length) {
        fetch("/api/search/?q=", { headers: { Accept: "application/json" } })
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
        results.classList.remove("show");
        return;
      }
      fetch("/api/search/?q=" + encodeURIComponent(q), {
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

    input.addEventListener("input", function () {
      clearTimeout(debounce);
      debounce = setTimeout(search, 220);
    });
    input.addEventListener("focus", search);
    input.addEventListener("keydown", function (e) {
      if (e.key === "Escape") {
        results.classList.remove("show");
        input.blur();
      }
    });
    document.addEventListener("click", function (e) {
      if (!input.contains(e.target) && !results.contains(e.target)) {
        results.classList.remove("show");
      }
    });
    /* Ctrl+K is owned by rmc-command-palette.js on authenticated shells.
       Header search focuses on click; palette opens on Ctrl+K (Spotlight model). */
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
        a.className = "nav-link text-white d-flex align-items-center flex-grow-1 cp-nav-recent-link";
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
