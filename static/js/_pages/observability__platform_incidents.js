  function getCookie(name) {
    const cookies = document.cookie ? document.cookie.split(";") : [];
    for (const cookie of cookies) {
      const trimmed = cookie.trim();
      if (trimmed.startsWith(name + "=")) {
        return decodeURIComponent(trimmed.slice(name.length + 1));
      }
    }
    return "";
  }

  async function updateIncidentStatus(button) {
    const incidentId = button.dataset.incidentId;
    const action = button.dataset.action;
    const response = await fetch(`/api/observability/incidents/${incidentId}/status/`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "X-CSRFToken": getCookie("csrftoken"),
      },
      body: JSON.stringify({ action }),
      credentials: "same-origin",
    });

    if (!response.ok) {
      return;
    }

    const payload = await response.json();
    const row = document.getElementById(`incident-${incidentId}`);
    if (!row || !payload.incident) {
      return;
    }

    const badge = row.querySelector(".incident-status");
    if (badge) {
      badge.textContent = payload.incident.status;
    }
  }

  document.querySelectorAll(".incident-action").forEach((button) => {
    button.addEventListener("click", () => {
      updateIncidentStatus(button);
    });
  });
