/* Task submission and observable scoring-pipeline flow */

let scoringPollTimer = null;
let scoringTimeoutTimer = null;
let scoringTimedOut = false;

function initTaskDraft() {
  const draftKey = `sabi_draft_${state.sessionId}`;
  const textarea = document.getElementById("task-input");
  const saved = localStorage.getItem(draftKey);
  if (saved && !textarea.value) textarea.value = saved;
  clearInterval(state.autosaveInterval);
  state.autosaveInterval = setInterval(() => {
    const val = textarea.value;
    if (!val) return;
    localStorage.setItem(draftKey, val);
    API.saveDraft(state.sessionId, val);
    const indicator = document.getElementById("draft-indicator");
    if (indicator) indicator.textContent = "Draft autosaved locally.";
  }, 3000);
}

async function onSubmitTask() {
  const textarea = document.getElementById("task-input");
  const text = textarea.value.trim();
  if (!text) return alert("Please write your recommendation.");
  clearInterval(state.autosaveInterval);
  localStorage.removeItem(`sabi_draft_${state.sessionId}`);
  try {
    await API.submitTask(state.sessionId, text, state.userId);
    startScoringFlow();
  } catch (error) {
    alert(error.message);
  }
}

function stopScoringWatch() {
  clearInterval(scoringPollTimer);
  clearTimeout(scoringTimeoutTimer);
}

function showScoringFailure(message) {
  stopScoringWatch();
  document.querySelector("#scoring-loading .spinner").style.display = "none";
  document.getElementById("pipeline-stage").textContent = "";
  document.getElementById("scoring-error-message").textContent = message;
  document.getElementById("scoring-error").style.display = "block";
}

function updateScoringProgress(status) {
  const stages = ["reading", "gate", "scoring", "verification"];
  const stage = status.current_stage || "prepare";
  const current = stages.indexOf(stage);
  document.querySelectorAll("#scoring-steps li").forEach((item, index) => {
    item.classList.toggle("done", status.status === "done" || index < current);
    item.classList.toggle("active", status.status === "running" && index === current);
  });
  document.getElementById("pipeline-stage").textContent =
    status.status === "running" ? `Current stage: ${stage}` : "Finishing assessment…";
  if (status.status === "failed") showScoringFailure(status.error_message || "Assessment failed.");
}

async function pollScoringStatus() {
  try {
    const status = await API.getPipelineStatus(state.sessionId);
    updateScoringProgress(status);
  } catch (error) {
    console.error("Could not poll scoring status.", error);
  }
}

async function startScoringFlow() {
  showScreen("screen-scoring");
  const loading = document.getElementById("scoring-loading");
  loading.style.display = "block";
  loading.querySelector(".spinner").style.display = "block";
  document.getElementById("scoring-error").style.display = "none";
  document.getElementById("clarification-panel").style.display = "none";
  document.querySelectorAll("#scoring-steps li").forEach(item => item.classList.remove("active", "done"));
  stopScoringWatch();
  scoringTimedOut = false;
  pollScoringStatus();
  scoringPollTimer = setInterval(pollScoringStatus, 2000);
  scoringTimeoutTimer = setTimeout(() => {
    scoringTimedOut = true;
    showScoringFailure("Taking too long. You can retry the assessment.");
  }, 90_000);
  try {
    const result = await API.triggerScoring(state.sessionId);
    stopScoringWatch();
    if (scoringTimedOut) return;
    if (result.status === "awaiting_clarification") {
      loading.style.display = "none";
      renderClarification(result.clarification_requests || []);
    } else {
      document.querySelectorAll("#scoring-steps li").forEach(item => item.classList.add("done"));
      await showResultsScreen();
    }
  } catch (error) {
    showScoringFailure(error.message);
  }
}

function renderClarification(clarifications) {
  const panel = document.getElementById("clarification-panel");
  panel.style.display = "block";
  document.getElementById("clarification-list").innerHTML = clarifications.map(item => `
    <div class="clarify-item" data-mid="${item.message_id}">
      <p><strong>Question:</strong> ${item.question}</p>
      <input type="text" class="clarify-input" placeholder="Type clarification in English...">
    </div>`).join("");
}

async function onSubmitClarification() {
  const items = document.querySelectorAll(".clarify-item");
  for (const item of items) {
    const answer = item.querySelector(".clarify-input").value.trim();
    if (answer) await API.submitClarification(state.sessionId, item.getAttribute("data-mid"), answer);
  }
  startScoringFlow();
}
