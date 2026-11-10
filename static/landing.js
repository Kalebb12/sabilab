/* Scenario loading and selection for the SabiLab landing screen */

function selectScenario(scenarioId) {
  state.scenarioId = scenarioId;
  showScreen("screen-consent");
}

function escapeHTML(value) {
  return String(value).replace(/[&<>"']/g, char => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
  })[char]);
}

function renderScenarios(scenarios) {
  const list = document.getElementById("scenario-list");
  const available = scenarios.filter(scenario => scenario.status === "full");
  list.replaceChildren();
  document.getElementById("scenario-empty").hidden = available.length > 0;
  available.forEach(scenario => {
    const card = document.createElement("article");
    card.className = "card-item live scenario-card";
    card.tabIndex = 0;
    card.setAttribute("role", "button");
    card.dataset.scenarioId = scenario.id;
    const title = escapeHTML(scenario.title);
    const role = escapeHTML(scenario.student_role);
    const art = scenario.id === "adaeze"
      ? `<img src="/static/img/shop-scene-sm.webp" alt="Illustration of the fabrics shop" onerror="this.hidden=true">`
      : "";
    card.innerHTML = `
      <div class="scenario-art">${art}</div>
      <div class="scenario-copy">
        <div class="scenario-card-head"><h3>${title}</h3><span class="tag live">Available</span></div>
        <p class="scenario-role">Role: ${role}</p>
      </div>`;
    card.addEventListener("click", () => selectScenario(scenario.id));
    card.addEventListener("keydown", event => {
      if (event.key === "Enter" || event.key === " ") {
        event.preventDefault();
        selectScenario(scenario.id);
      }
    });
    list.append(card);
  });
}

async function loadScenarios() {
  const list = document.getElementById("scenario-list");
  const error = document.getElementById("scenario-error");
  const empty = document.getElementById("scenario-empty");
  error.hidden = true;
  empty.hidden = true;
  list.innerHTML = '<div class="scenario-skeleton" aria-label="Loading scenarios"><div class="skeleton-art"></div><div class="skeleton-lines"><span></span><span></span></div></div>';
  try {
    renderScenarios(await API.getScenarios());
  } catch (err) {
    list.replaceChildren();
    document.getElementById("scenario-error-message").textContent = err.message;
    error.hidden = false;
  }
}

document.addEventListener("DOMContentLoaded", loadScenarios);
