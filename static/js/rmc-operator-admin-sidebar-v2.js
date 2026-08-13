(function () {
  "use strict";
  var root = document.querySelector('[data-rmc-operator-admin-sidebar-v2="1"]');
  if (!root || !document.body.classList.contains("admin-manager-shell")) return;
  var recentKey = "rmcOperatorAdminRecent:v2";
  var recentLimit = 4;

  function readRecent() {
    try { var value = JSON.parse(localStorage.getItem(recentKey) || "[]"); return Array.isArray(value) ? value : []; }
    catch (_error) { return []; }
  }
  function writeRecent(value) { try { localStorage.setItem(recentKey, JSON.stringify(value)); } catch (_error) { /* optional */ } }
  function normalized(value) { return String(value || "").replace(/\s+/g, " ").trim(); }
  function matchesQuery(label, query) {
    var haystack=normalized(label).toLocaleLowerCase();
    return query.split(/\s+/).every(function (term) {
      if (haystack.includes(term)) return true;
      if (term.endsWith("y") && haystack.includes(term.slice(0,-1) + "i")) return true;
      if (term.endsWith("s") && haystack.includes(term.slice(0,-1))) return true;
      return false;
    });
  }
  function focusables() { return Array.prototype.filter.call(root.querySelectorAll('a[href],button:not([disabled]),input:not([disabled]),[tabindex="0"]'), function (node) { return node.offsetParent !== null && !node.closest('[data-operator-search-hidden="1"]'); }); }
  function filterNavigation(query) {
    var value=normalized(query).toLocaleLowerCase(), matches=0;
    root.querySelectorAll("a.cp-sidebar__item, a.cp-sidebar__recent-item").forEach(function (link) {
      var hit=!value || matchesQuery(link.textContent,value);
      link.toggleAttribute("data-operator-search-hidden",!hit);
      if (value && hit) matches++;
    });
    root.querySelectorAll(".cp-sidebar__group").forEach(function (group) {
      group.toggleAttribute("data-operator-search-hidden",!!value && !group.querySelector('a:not([data-operator-search-hidden="1"])'));
    });
    var status=root.querySelector("#rmcOperatorAdminNavSearchStatus");
    if (status) status.textContent=value ? (matches === 1 ? "1 matching destination" : matches + " matching destinations") : "";
  }
  function currentEntry() {
    var current = root.querySelector('a.cp-sidebar__item[aria-current="page"], a.cp-sidebar__item--current');
    if (!current) return null;
    var label = current.querySelector(".cp-nav-label");
    return { url:current.href, path:current.pathname + current.search, label:(label ? label.textContent : current.textContent).trim().replace(/\s+/g," "), icon:(current.querySelector("i") || {}).className || "bi bi-clock-history" };
  }
  function renderRecent() {
    var wrap = root.querySelector("[data-operator-recent-wrap]");
    var list = root.querySelector("[data-operator-recent-list]");
    if (!wrap || !list) return;
    var currentPath = window.location.pathname + window.location.search;
    var entries = readRecent().filter(function (entry) { return entry && entry.path !== currentPath; }).slice(0,recentLimit);
    list.textContent = "";
    entries.forEach(function (entry) {
      var link=document.createElement("a"), icon=document.createElement("i"), label=document.createElement("span");
      link.className="cp-sidebar__recent-item"; link.href=entry.url; icon.className=entry.icon; icon.setAttribute("aria-hidden","true"); label.textContent=entry.label;
      link.appendChild(icon); link.appendChild(label); list.appendChild(link);
    });
    wrap.hidden = entries.length === 0;
  }
  function rememberCurrent() {
    var entry=currentEntry(); if (!entry) return;
    var entries=readRecent().filter(function (item) { return item && item.path !== entry.path; }); entries.unshift(entry); writeRecent(entries.slice(0,recentLimit + 1));
  }
  function updateConnection() {
    var status=root.querySelector("[data-operator-connection-status]"), label=root.querySelector("[data-operator-connection-label]"); if (!status || !label) return;
    var offline=navigator.onLine === false; status.classList.toggle("is-offline",offline); label.textContent=offline ? "Offline safe" : "Local ready";
    status.title=offline ? "Navigation preferences remain available on this device" : "Local navigation preferences are ready";
  }
  function csrfToken() {
    var match=(document.cookie || "").match(/(?:^|;\s*)csrftoken=([^;]+)/); return match ? decodeURIComponent(match[1]) : "";
  }
  function bindPins() {
    root.querySelectorAll(".cp-pin-btn[data-cp-pin-id]").forEach(function (button) {
      if (button.dataset.operatorPinBound === "1") return; button.dataset.operatorPinBound="1";
      button.addEventListener("click",function (event) {
        event.preventDefault(); event.stopPropagation();
        var id=button.getAttribute("data-cp-pin-id");
        var endpoint=window.RMCPlatformSurface && window.RMCPlatformSurface.url ? window.RMCPlatformSurface.url("control_plane_preferences") : "";
        if (!id || !endpoint || navigator.onLine === false) return;
        button.disabled=true;
        fetch(endpoint,{credentials:"same-origin",headers:{Accept:"application/json"}})
          .then(function (response) { if (!response.ok) throw new Error("Preference read failed"); return response.json(); })
          .then(function (data) {
            var values=Array.isArray(data.control_plane_pinned_items) ? data.control_plane_pinned_items.slice() : [];
            var pinned=button.classList.contains("cp-pin-pinned");
            values=pinned ? values.filter(function (value) { return value !== id; }) : values;
            if (!pinned && values.indexOf(id) === -1) values.push(id);
            return fetch(endpoint,{method:"PATCH",credentials:"same-origin",headers:{"Content-Type":"application/json","X-CSRFToken":csrfToken(),Accept:"application/json"},body:JSON.stringify({control_plane_pinned_items:values})});
          })
          .then(function (response) { if (!response.ok) throw new Error("Preference save failed"); window.location.reload(); })
          .catch(function () { button.disabled=false; button.title="Could not update Quick access. Try again when connected."; });
      });
    });
  }
  var clear=root.querySelector("[data-operator-recent-clear]"); if (clear) clear.addEventListener("click",function () { writeRecent([]); renderRecent(); });
  var search=root.querySelector("#rmcOperatorAdminNavSearch");
  if (search) {
    search.addEventListener("input",function () { filterNavigation(search.value); });
    document.addEventListener("keydown",function (event) {
      if (event.key === "/" && !event.ctrlKey && !event.metaKey && !event.altKey && !/input|textarea|select/i.test(event.target.tagName)) { event.preventDefault(); search.focus(); }
    });
  }
  root.addEventListener("keydown",function (event) {
    if (event.altKey || event.ctrlKey || event.metaKey) return;
    var nodes=focusables(), index=nodes.indexOf(event.target), next;
    if (event.key === "ArrowDown") next=nodes[Math.min(nodes.length-1,index+1)];
    else if (event.key === "ArrowUp") next=nodes[Math.max(0,index-1)];
    else if (event.key === "Home") next=nodes[0];
    else if (event.key === "End") next=nodes[nodes.length-1];
    if (next) { event.preventDefault(); next.focus(); }
  });
  window.addEventListener("online",updateConnection); window.addEventListener("offline",updateConnection);
  renderRecent(); rememberCurrent(); updateConnection(); bindPins();
})();
