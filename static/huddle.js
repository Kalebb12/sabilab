/* Huddle chat, timer, draft autosave, and scoring flow for SabiLab */

function startHuddle() {
  showScreen("screen-huddle");
  state.huddleRemaining = 90;
  clearInterval(state.timerInterval);
  clearInterval(state.pollInterval);

  updateTimerDisplay();
  state.timerInterval = setInterval(() => {
    state.huddleRemaining = Math.max(0, state.huddleRemaining - 1);
    updateTimerDisplay();
    if (state.huddleRemaining === 0) clearInterval(state.timerInterval);
  }, 1000);

  pollMessages();
  state.pollInterval = setInterval(pollMessages, 3000);
}

function updateTimerDisplay() {
  const m = String(Math.floor(state.huddleRemaining / 60)).padStart(2, "0");
  const s = String(state.huddleRemaining % 60).padStart(2, "0");
  const el = document.getElementById("huddle-timer");
  if (el) el.textContent = `${m}:${s}`;
}

async function pollMessages() {
  if (!state.sessionId) return;
  try {
    const msgs = await API.getMessages(state.sessionId);
    renderMessages(msgs);
  } catch (e) {}
}

function renderMessages(msgs) {
  const container = document.getElementById("chat-stream");
  const banner = document.getElementById("twist-alert");
  let twistFound = false;

  container.innerHTML = msgs.map(m => {
    if (m.phase === "twist" || (m.sender === "Adaeze" && m.sequence_number >= 4)) {
      twistFound = true;
      if (banner) { banner.style.display = "block"; banner.textContent = `TWIST: ${m.text}`; }
      return `<div class="bubble twist"><strong>${m.sender}:</strong> ${m.text}</div>`;
    }
    const isMe = m.sender === state.studentName || m.sender === "Student";
    return `<div class="bubble ${isMe ? 'mine' : 'theirs'}"><strong>${m.sender}:</strong> ${m.text}</div>`;
  }).join("");

  if (!twistFound && banner) banner.style.display = "none";
  container.scrollTop = container.scrollHeight;
}

async function onSendMessage() {
  const input = document.getElementById("chat-input");
  const text = input.value.trim();
  if (!text) return;
  try {
    input.value = "";
    await API.sendMessage(state.sessionId, state.studentName, text);
    await pollMessages();
  } catch (err) { alert(err.message); }
}

function proceedToTask() {
  clearInterval(state.timerInterval);
  clearInterval(state.pollInterval);
  showScreen("screen-task");
  initTaskDraft();
}

function initTaskDraft() {
  const draftKey = `sabi_draft_${state.sessionId}`;
  const textarea = document.getElementById("task-input");
  const saved = localStorage.getItem(draftKey);
  if (saved && !textarea.value) textarea.value = saved;

  clearInterval(state.autosaveInterval);
  state.autosaveInterval = setInterval(() => {
    const val = textarea.value;
    if (val) {
      localStorage.setItem(draftKey, val);
      API.saveDraft(state.sessionId, val);
      const ind = document.getElementById("draft-indicator");
      if (ind) ind.textContent = "Draft autosaved locally.";
    }
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
  } catch (err) { alert(err.message); }
}

async function startScoringFlow() {
  showScreen("screen-scoring");
  document.getElementById("scoring-loading").style.display = "block";
  document.getElementById("clarification-panel").style.display = "none";

  try {
    const res = await API.triggerScoring(state.sessionId);
    if (res.status === "awaiting_clarification") {
      document.getElementById("scoring-loading").style.display = "none";
      renderClarification(res.clarifications || res.clarification_requests || []);
    } else {
      await showResultsScreen();
    }
  } catch (err) { alert(err.message); }
}

function renderClarification(clarifications) {
  const panel = document.getElementById("clarification-panel");
  panel.style.display = "block";
  const list = document.getElementById("clarification-list");
  list.innerHTML = clarifications.map(c => `
    <div class="clarify-item" data-mid="${c.message_id}">
      <p><strong>Question:</strong> ${c.question}</p>
      <input type="text" class="clarify-input" placeholder="Type clarification in English...">
    </div>
  `).join("");
}

async function onSubmitClarification() {
  const items = document.querySelectorAll(".clarify-item");
  for (const item of items) {
    const mid = item.getAttribute("data-mid");
    const ans = item.querySelector(".clarify-input").value.trim();
    if (ans) await API.submitClarification(state.sessionId, mid, ans);
  }
  startScoringFlow();
}
