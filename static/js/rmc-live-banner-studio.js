(function () {
  "use strict";

  function byId(id) {
    return document.getElementById(id);
  }

  function setCheckboxes(name, values) {
    var boxes = document.querySelectorAll('input[name="' + name + '"]');
    var selected = new Set((values || []).map(String));
    boxes.forEach(function (box) {
      box.checked = selected.has(box.value);
    });
  }

  function appendAnnouncementTextarea(fieldId, announcement) {
    var field = byId(fieldId);
    if (!field || !announcement || !announcement.text) {
      return;
    }
    var audiences = (announcement.audiences || ["all"]).join(",");
    var row = [
      announcement.text,
      announcement.kind || "emergency",
      announcement.severity || "danger",
      announcement.pin ? "yes" : "no",
      announcement.starts_at || "",
      announcement.ends_at || "",
      audiences,
    ].join(" | ");
    field.value = field.value ? field.value + "\n" + row : row;
  }

  function applyProgram(program) {
    if (!program || typeof program !== "object") {
      return;
    }
    var sources = program.sources_enabled || {};
    setCheckboxes("atk_manager_sources", sources.manager || []);
    setCheckboxes("atk_tenant_sources", sources.tenant || []);
    if (program.live_badge_label) {
      var badge = byId("id_atk_live_badge_label");
      if (badge) {
        badge.value = program.live_badge_label;
      }
    }
    if (program.scroll_seconds) {
      var scroll = byId("id_atk_scroll_seconds");
      if (scroll) {
        scroll.value = program.scroll_seconds;
      }
    }
    (program.announcements || []).forEach(function (item) {
      appendAnnouncementTextarea("id_atk_tenant_announcements", item);
    });
  }

  function fetchJson(url, options) {
    return fetch(url, options || {}).then(function (response) {
      return response.json().then(function (payload) {
        if (!response.ok || !payload.ok) {
          throw new Error((payload && payload.error) || "request_failed");
        }
        return payload;
      });
    });
  }

  document.addEventListener("DOMContentLoaded", function () {
    var suggestBtn = byId("rmc-live-banner-suggest-program");
    var emergencyBtn = byId("rmc-live-banner-draft-emergency");

    if (suggestBtn) {
      suggestBtn.addEventListener("click", function () {
        suggestBtn.disabled = true;
        fetchJson("/siteconfig/super/configure/cockpit/live-banner/suggest-program/")
          .then(function (payload) {
            applyProgram(payload.program || {});
          })
          .catch(function () {
            window.alert("Unable to generate a live banner program right now.");
          })
          .finally(function () {
            suggestBtn.disabled = false;
          });
      });
    }

    if (emergencyBtn) {
      emergencyBtn.addEventListener("click", function () {
        var topic = window.prompt("Emergency topic (optional):", "Campus safety update");
        if (topic === null) {
          return;
        }
        emergencyBtn.disabled = true;
        fetchJson("/siteconfig/super/configure/cockpit/live-banner/draft-emergency/", {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
            "X-CSRFToken": (document.querySelector("[name=csrfmiddlewaretoken]") || {}).value || "",
          },
          body: JSON.stringify({ topic: topic }),
        })
          .then(function (payload) {
            appendAnnouncementTextarea("id_atk_tenant_announcements", payload.announcement || {});
            appendAnnouncementTextarea("id_atk_manager_announcements", payload.announcement || {});
          })
          .catch(function () {
            window.alert("Unable to draft an emergency announcement right now.");
          })
          .finally(function () {
            emergencyBtn.disabled = false;
          });
      });
    }
  });
})();
