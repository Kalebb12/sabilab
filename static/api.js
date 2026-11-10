/* API client wrapper for SabiLab backend endpoints */

const API = {
  async getScenarios() {
    const res = await fetch("/scenarios");
    if (!res.ok) throw new Error("Failed to load scenarios.");
    return res.json();
  },

  async startSession(firstName, consent, userId = null, scenarioId = "adaeze") {
    const res = await fetch("/session", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        first_name: firstName || "Student",
        consent: Boolean(consent),
        scenario_id: scenarioId,
        mode: "demo",
        user_id: userId || undefined,
      }),
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(err.detail || "Failed to start session.");
    }
    return res.json();
  },

  async sendMessage(sessionId, sender, text) {
    const res = await fetch(`/session/${sessionId}/message`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ sender: sender || "Student", text }),
    });
    if (res.status === 429) throw new Error("Rate limit: please wait a moment.");
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(err.detail || "Failed to send message.");
    }
    return res.json();
  },

  async getMessages(sessionId) {
    const res = await fetch(`/session/${sessionId}/messages`);
    return res.json();
  },

  async saveDraft(sessionId, text) {
    await fetch(`/session/${sessionId}/draft`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ text }),
    }).catch(() => {});
  },

  async submitTask(sessionId, text, userId) {
    const res = await fetch("/task", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ session_id: sessionId, text, user_id: userId }),
    });
    if (!res.ok) throw new Error("Failed to submit task.");
    return res.json();
  },

  async triggerScoring(sessionId) {
    const res = await fetch(`/session/${sessionId}/score`, { method: "POST" });
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(err.detail || "Scoring pipeline failed.");
    }
    return res.json();
  },

  async getPipelineStatus(sessionId) {
    const res = await fetch(`/session/${sessionId}/pipeline-status`);
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(err.detail || "Failed to fetch pipeline status.");
    }
    return res.json();
  },

  async submitClarification(sessionId, messageId, answer) {
    const res = await fetch(`/session/${sessionId}/clarify`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ message_id: messageId, answer }),
    });
    if (!res.ok) throw new Error("Failed to submit clarification.");
    return res.json();
  },

  async getResults(sessionId) {
    const res = await fetch(`/session/${sessionId}/results`);
    return res.json();
  },

  async publishCard(sessionId, visibleFields) {
    const res = await fetch(`/session/${sessionId}/card`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ visible_fields: visibleFields }),
    });
    if (!res.ok) throw new Error("Failed to publish card.");
    return res.json();
  },
};
