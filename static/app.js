/* Navigation, state management, role, results, and card generation for SabiLab */

let state = {
  sessionId: localStorage.getItem("sabi_session_id") || null,
  userId: localStorage.getItem("sabi_user_id") || null,
  studentName: localStorage.getItem("sabi_student_name") || "Student",
  role: "", brief: "", roster: [], scenarioId: "adaeze",
  huddleRemaining: 90,
  timerInterval: null, pollInterval: null, autosaveInterval: null,
};

function showScreen(id) {
  document.querySelectorAll(".screen").forEach(s => s.classList.remove("active"));
  const target = document.getElementById(id);
  if (target) target.classList.add("active");
  document.querySelectorAll(".nav-item").forEach(item => {
    if (id === "screen-landing") item.setAttribute("aria-current", "page");
    else item.removeAttribute("aria-current");
  });
  window.scrollTo(0, 0);
}

async function onStartSession() {
  const consent = document.getElementById("consent-check").checked;
  const nameInput = document.getElementById("student-name-input").value.trim();
  if (!consent) return alert("Please accept consent to continue.");
  if (nameInput) state.studentName = nameInput;

  try {
    const data = await API.startSession(state.studentName, true, state.userId, state.scenarioId);
    state.sessionId = data.session_id;
    state.userId = data.user_id;
    state.role = data.student_role;
    state.brief = data.private_brief;
    state.roster = data.roster || [];
    localStorage.setItem("sabi_session_id", state.sessionId);
    localStorage.setItem("sabi_user_id", state.userId);
    localStorage.setItem("sabi_student_name", state.studentName);

    renderRoleScreen();
    showScreen("screen-role");
  } catch (err) { alert(err.message); }
}

function renderRoleScreen() {
  document.getElementById("role-title").textContent = state.role || "Accountant";
  document.getElementById("role-brief").textContent = state.brief;
  const rosterEl = document.getElementById("teammate-roster");
  rosterEl.innerHTML = state.roster.map(t =>
    `<div class="roster-item"><strong>${t.name}</strong> <span>(${t.role})</span></div>`
  ).join("");
}

async function showResultsScreen() {
  const data = await API.getResults(state.sessionId);
  renderResults(data);
  showScreen("screen-results");
}

function renderResults(data) {
  const skillsList = document.getElementById("results-skills");
  skillsList.innerHTML = (data.scores || []).map(s => {
    const hasQuote = s.evidence && s.evidence !== "Insufficient evidence";
    return `
      <div class="skill-card">
        <div class="skill-head"><strong>${s.criterion}</strong><span class="pill">${s.level}</span></div>
        <div class="quote-block ${hasQuote ? '' : 'insufficient'}">${hasQuote ? `&ldquo;${s.evidence}&rdquo;` : 'Insufficient evidence'}</div>
        <div class="confidence">Confidence: <strong>${s.confidence || 'Medium'}</strong></div>
      </div>`;
  }).join("");

  document.getElementById("did-well-text").textContent = data.did_well || "Clear factual awareness.";
  document.getElementById("improve-text").textContent = data.improve || "State explicit deadlines and cash balances.";
  const badgeEl = document.getElementById("badge-display");
  if (data.badge) {
    badgeEl.style.display = "block";
    badgeEl.innerHTML = `<strong>Badge Awarded:</strong> ${data.badge.name} (${data.badge.level}) - <em>${data.badge.tier}</em>`;
  } else { badgeEl.style.display = "none"; }
}

function onTryAgain() {
  showScreen("screen-consent");
}

function goToCardScreen() {
  showScreen("screen-card");
  document.getElementById("card-published-box").style.display = "none";
}

async function onPublishCard() {
  const fields = [];
  document.querySelectorAll(".card-field-check:checked").forEach(c => fields.push(c.value));
  try {
    const card = await API.publishCard(state.sessionId, fields);
    const box = document.getElementById("card-published-box");
    box.style.display = "block";
    const link = document.getElementById("card-link");
    link.href = card.card_url;
    link.textContent = window.location.origin + card.card_url;
  } catch (err) { alert(err.message); }
}

document.addEventListener("DOMContentLoaded", () => {
  showScreen("screen-landing");
});
