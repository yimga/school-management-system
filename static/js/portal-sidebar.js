(function () {
  function ready(fn) {
    if (document.readyState === "loading") {
      document.addEventListener("DOMContentLoaded", fn);
      return;
    }
    fn();
  }

  function getCsrfToken() {
    var name = "csrftoken=";
    var cookies = document.cookie ? document.cookie.split(";") : [];
    for (var i = 0; i < cookies.length; i++) {
      var cookie = cookies[i].trim();
      if (cookie.indexOf(name) === 0) {
        return cookie.substring(name.length);
      }
    }
    return "";
  }

  function initRecentActivityCollapse() {
    var key = "portal-sidebar-recent-activity-collapsed";
    var collapsed = localStorage.getItem(key) === "true";

    function applyState(block, isCollapsed) {
      var header = block.querySelector(".recent-activity-toggle");
      var content = block.querySelector(".recent-activity-content");
      var chevron = block.querySelector(".recent-activity-chevron");
      if (!header || !content) return;
      content.classList.toggle("collapsed", isCollapsed);
      header.setAttribute("aria-expanded", String(!isCollapsed));
      if (chevron) chevron.classList.toggle("collapsed", isCollapsed);
    }

    var blocks = Array.from(document.querySelectorAll(".recent-activity-block"));
    if (!blocks.length) return;
    blocks.forEach(function (block) {
      applyState(block, collapsed);
      var header = block.querySelector(".recent-activity-toggle");
      if (!header) return;
      header.addEventListener("click", function () {
        collapsed = !collapsed;
        localStorage.setItem(key, collapsed ? "true" : "false");
        blocks.forEach(function (b) {
          applyState(b, collapsed);
        });
      });
    });
  }

  function initPinnedItems() {
    var buttons = Array.from(document.querySelectorAll(".sidebar-pin-btn[data-sidebar-id]"));
    if (!buttons.length) return;

    buttons.forEach(function (btn) {
      if (btn.dataset.pinBound === "1") return;
      btn.dataset.pinBound = "1";
      btn.addEventListener("click", function (e) {
        e.preventDefault();
        e.stopPropagation();
        var id = btn.getAttribute("data-sidebar-id");
        if (!id) return;
        var isPinned = btn.classList.contains("sidebar-pin-pinned");

        var prefsUrl = (window.RMCPlatformSurface && window.RMCPlatformSurface.url("portal_preferences")) || "";
        if (!prefsUrl) return;
        fetch(prefsUrl, {
          method: "GET",
          credentials: "same-origin",
          headers: { Accept: "application/json" },
        })
          .then(function (r) {
            return r.json();
          })
          .then(function (data) {
            var list = data && Array.isArray(data.pinned_sidebar_items) ? data.pinned_sidebar_items : [];
            if (isPinned) {
              list = list.filter(function (x) {
                return x !== id;
              });
            } else if (list.indexOf(id) === -1) {
              list.push(id);
            }

            return fetch(prefsUrl, {
              method: "PATCH",
              credentials: "same-origin",
              headers: {
                "Content-Type": "application/json",
                "X-CSRFToken": getCsrfToken(),
                Accept: "application/json",
              },
              body: JSON.stringify({ pinned_sidebar_items: list }),
            });
          })
          .then(function (r) {
            if (!r.ok) throw new Error("Failed to save sidebar preferences");
            return r.json();
          })
          .then(function () {
            window.location.reload();
          })
          .catch(function () {});
      });
    });
  }

  function initActiveLinkState() {
    var navs = Array.from(document.querySelectorAll("[data-sidebar-nav]"));
    if (!navs.length) return;
    var currentPath = window.location.pathname.replace(/\/+$/, "") || "/";
    navs.forEach(function (nav) {
      var links = Array.from(nav.querySelectorAll('a.nav-link.nav-pill[href]'));
      if (!links.length) return;

      var best = null;
      var bestScore = -1;
      links.forEach(function (link) {
        var href = link.getAttribute("href") || "";
        if (!href || href === "#" || href.indexOf("javascript:") === 0) return;

        var path = "";
        try {
          var url = new URL(href, window.location.origin);
          if (url.origin !== window.location.origin) return;
          path = (url.pathname || "/").replace(/\/+$/, "") || "/";
        } catch (err) {
          return;
        }

        var score = -1;
        if (path === currentPath) {
          score = path.length + 1000;
        } else if (path !== "/" && currentPath.indexOf(path + "/") === 0) {
          score = path.length;
        }

        if (score > bestScore) {
          bestScore = score;
          best = link;
        }
      });

      links.forEach(function (link) {
        link.classList.remove("active");
        if (link.getAttribute("aria-current") === "page") {
          link.removeAttribute("aria-current");
        }
      });

      if (best) {
        best.classList.add("active");
        best.setAttribute("aria-current", "page");
      }
    });
  }

  ready(function () {
    initRecentActivityCollapse();
    initPinnedItems();
    initActiveLinkState();
  });
})();
