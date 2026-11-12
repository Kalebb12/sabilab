/* Huddle message display with one-at-a-time teammate typing animation */

let chatShownIds = new Set();
let chatQueuedIds = new Set();
let chatQueue = [];
let chatMessages = [];
let chatOptimistic = [];
let chatTyping = null;
let chatTypingTimer = null;

function resetChat() {
  chatShownIds = new Set();
  chatQueuedIds = new Set();
  chatQueue = [];
  chatMessages = [];
  chatOptimistic = [];
  chatTyping = null;
  clearTimeout(chatTypingTimer);
  state.hasSentMessage = false;
  renderChat();
}

function isStudentMessage(message) {
  return message.sender === state.studentName || message.sender === "Student";
}

async function pollMessages() {
  if (!state.sessionId) return;
  try {
    chatMessages = await API.getMessages(state.sessionId);
    chatMessages.forEach(message => {
      if (isStudentMessage(message)) {
        chatShownIds.add(message.id);
        state.hasSentMessage = true;
      } else if (!chatQueuedIds.has(message.id) && !chatShownIds.has(message.id)) {
        chatQueuedIds.add(message.id);
        chatQueue.push(message);
      }
    });
    const stored = new Set(chatMessages.map(message => `${message.sender}\n${message.text}`));
    chatOptimistic = chatOptimistic.filter(message => !stored.has(`${message.sender}\n${message.text}`));
    renderChat();
    showNextTeammateMessage();
  } catch (error) {
    console.error("Could not refresh huddle messages.", error);
  }
}

function showNextTeammateMessage() {
  if (chatTyping || !chatQueue.length) return;
  chatTyping = chatQueue.shift();
  renderChat();
  chatTypingTimer = setTimeout(() => {
    if (!chatTyping.typingOnly) chatShownIds.add(chatTyping.id);
    chatTyping = null;
    renderChat();
    showNextTeammateMessage();
  }, 1000 + Math.random() * 1000);
}

function escapeChatText(text) {
  return String(text).replace(/[&<>"']/g, char => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
  })[char]);
}

function messageRole(sender) {
  if (sender === state.studentName || sender === "Student") return state.role || "Student";
  if (sender === "Adaeze") return "Owner";
  const teammate = (state.roster || []).find(person => person.name === sender);
  return teammate ? teammate.role : "Teammate";
}

function bubbleMarkup(message, typing = false) {
  const mine = isStudentMessage(message);
  const twist = message.phase === "twist";
  const role = escapeChatText(messageRole(message.sender));
  const sender = escapeChatText(message.sender);
  const initial = escapeChatText(sender.trim().charAt(0).toUpperCase() || "?");
  const body = typing
    ? '<span class="typing-dots" aria-label="typing"><span></span><span></span><span></span></span>'
    : escapeChatText(message.text);
  return `<div class="bubble ${mine ? "mine" : "theirs"} ${twist && !typing ? "twist" : ""}">
    <div class="bubble-head"><span class="chat-avatar">${initial}</span>
      <span><span class="bubble-name">${sender}</span><span class="bubble-role">${role}</span></span></div>${body}</div>`;
}

function renderChat() {
  const container = document.getElementById("chat-stream");
  if (!container) return;
  const visible = chatMessages
    .filter(message => chatShownIds.has(message.id))
    .concat(chatOptimistic)
    .sort((a, b) => (a.sequence_number || 0) - (b.sequence_number || 0));
  container.innerHTML = visible.map(message => bubbleMarkup(message)).join("");
  if (chatTyping) container.insertAdjacentHTML("beforeend", bubbleMarkup(chatTyping, true));
  container.scrollTop = container.scrollHeight;
  const twist = chatMessages.find(message =>
    message.phase === "twist"
  );
  const banner = document.getElementById("twist-alert");
  if (banner) {
    banner.style.display = twist ? "block" : "none";
    if (twist) banner.textContent = `TWIST: ${twist.text}`;
  }
  const proceed = document.getElementById("proceed-task-button");
  if (proceed) proceed.disabled = !state.hasSentMessage;
}

async function onSendMessage() {
  const input = document.getElementById("chat-input");
  const text = input.value.trim();
  if (!text) return;
  const optimistic = {
    id: `local-${Date.now()}`, sender: state.studentName, text,
    sequence_number: Number.MAX_SAFE_INTEGER,
  };
  chatOptimistic.push(optimistic);
  const ownerTyping = {
    id: `owner-typing-${Date.now()}`, sender: "Adaeze", text: "",
    sequence_number: Number.MAX_SAFE_INTEGER, typingOnly: true,
  };
  chatQueuedIds.add(ownerTyping.id);
  chatQueue.unshift(ownerTyping);
  state.hasSentMessage = true;
  input.value = "";
  renderChat();
  showNextTeammateMessage();
  try {
    await API.sendMessage(state.sessionId, state.studentName, text);
    chatOptimistic = chatOptimistic.filter(message => message.id !== optimistic.id);
    await pollMessages();
  } catch (error) {
    chatOptimistic = chatOptimistic.filter(message => message.id !== optimistic.id);
    state.hasSentMessage = chatMessages.some(isStudentMessage);
    renderChat();
    alert(error.message);
  }
}
