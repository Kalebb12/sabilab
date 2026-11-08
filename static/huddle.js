/* Huddle timer and navigation */

function startHuddle() {
  showScreen("screen-huddle");
  state.huddleRemaining = 90;
  clearInterval(state.timerInterval);
  clearInterval(state.pollInterval);
  resetChat();
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

function proceedToTask() {
  if (!state.hasSentMessage) return;
  clearInterval(state.timerInterval);
  clearInterval(state.pollInterval);
  showScreen("screen-task");
  initTaskDraft();
}
