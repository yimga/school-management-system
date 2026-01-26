// Lightweight frontend orchestration helpers for CRUD APIs.
(function (window) {
  const CSRF_COOKIE = "csrftoken";

  function getCsrf() {
    const cookies = document.cookie ? document.cookie.split(";") : [];
    for (const raw of cookies) {
      const cookie = raw.trim();
      if (cookie.startsWith(`${CSRF_COOKIE}=`)) {
        return decodeURIComponent(cookie.substring(CSRF_COOKIE.length + 1));
      }
    }
    return "";
  }

  async function fetchJson(url, options = {}) {
    const headers = options.headers || {};
    headers["Content-Type"] = "application/json";
    if (!headers["X-CSRFToken"]) {
      headers["X-CSRFToken"] = getCsrf();
    }
    const resp = await fetch(url, { ...options, headers });
    const data = await resp.json().catch(() => ({}));
    if (!resp.ok) {
      const err = new Error(data.error || resp.statusText);
      err.status = resp.status;
      err.payload = data;
      throw err;
    }
    return data;
  }

  async function fetchSessionClaims() {
    return fetchJson("/api/session/claims/");
  }

  async function fetchClassrooms() {
    return fetchJson("/api/entities/classrooms/");
  }

  async function fetchStudents(params = "") {
    const qs = params ? `?${params}` : "";
    return fetchJson(`/api/entities/students/${qs}`);
  }

  async function updateStudent(id, payload) {
    return fetchJson(`/api/entities/students/${id}/`, {
      method: "PATCH",
      body: JSON.stringify(payload),
    });
  }

  async function deleteStudent(id) {
    return fetchJson(`/api/entities/students/${id}/`, {
      method: "DELETE",
    });
  }

  async function createStudent(payload) {
    return fetchJson("/api/entities/students/", {
      method: "POST",
      body: JSON.stringify(payload),
    });
  }

  async function bulkAssignStudents(payload) {
    return fetchJson("/api/entities/students/bulk-assign/", {
      method: "POST",
      body: JSON.stringify(payload),
    });
  }

  function parseIds(text) {
    return (text || "")
      .split(/[\s,]+/)
      .map((t) => parseInt(t, 10))
      .filter((n) => Number.isInteger(n));
  }

  async function populateClassrooms(selectId) {
    const select = document.getElementById(selectId);
    if (!select) return;
    select.innerHTML = `<option value=\"\">Loading...</option>`;
    try {
      const data = await fetchClassrooms();
      const items = Array.isArray(data.results) ? data.results : data;
      select.innerHTML = `<option value=\"\">Select classroom</option>`;
      items.forEach((item) => {
        const opt = document.createElement("option");
        opt.value = item.id;
        opt.textContent = `${item.name} (${item.code})`;
        select.appendChild(opt);
      });
    } catch (err) {
      select.innerHTML = `<option value=\"\">Failed to load</option>`;
    }
  }

  window.EntityOrchestrator = {
    fetchSessionClaims,
    fetchClassrooms,
    fetchStudents,
    createStudent,
    updateStudent,
    deleteStudent,
    bulkAssignStudents,
    parseIds,
    populateClassrooms,
  };
})(window);
