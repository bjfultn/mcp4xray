/* mcp4xray - Chat UI Application */

(function () {
  "use strict";

  // ---------------------------------------------------------------------------
  // State
  // ---------------------------------------------------------------------------

  let currentConversationId = null;
  let isStreaming = false;
  let abortController = null;

  // ---------------------------------------------------------------------------
  // Auth helpers
  // ---------------------------------------------------------------------------

  function getToken() {
    return localStorage.getItem("token");
  }

  function getUsername() {
    return localStorage.getItem("username") || "";
  }

  function getRole() {
    return localStorage.getItem("role") || "user";
  }

  function authHeaders() {
    return { Authorization: "Bearer " + getToken() };
  }

  function requireAuth() {
    if (!getToken()) {
      window.location.href = "/login.html";
      return false;
    }
    return true;
  }

  function logout() {
    localStorage.removeItem("token");
    localStorage.removeItem("username");
    localStorage.removeItem("role");
    window.location.href = "/login.html";
  }

  // ---------------------------------------------------------------------------
  // DOM references
  // ---------------------------------------------------------------------------

  const $ = (sel) => document.querySelector(sel);
  const serverSelect = () => $("#server-select");
  const modelSelect = () => $("#model-select");
  const messagesEl = () => $("#messages");
  const messageArea = () => $("#message-area");
  const messageInput = () => $("#message-input");
  const chatForm = () => $("#chat-form");
  const sendBtn = () => $("#send-btn");
  const convList = () => $("#conversation-list");
  const emptyState = () => $("#empty-state");
  const usernameDisplay = () => $("#username-display");
  const adminLink = () => $("#admin-link");

  // ---------------------------------------------------------------------------
  // Initialization
  // ---------------------------------------------------------------------------

  async function init() {
    if (!requireAuth()) return;

    // Display user info
    usernameDisplay().textContent = getUsername();
    if (getRole() === "admin") {
      adminLink().style.display = "";
    }

    // Set up event listeners
    chatForm().addEventListener("submit", onSubmit);
    $("#new-chat-btn").addEventListener("click", newChat);
    $("#logout-btn").addEventListener("click", logout);

    // Allow Shift+Enter for newline, Enter to send
    messageInput().addEventListener("keydown", function (e) {
      if (e.key === "Enter" && !e.shiftKey) {
        e.preventDefault();
        chatForm().dispatchEvent(new Event("submit", { cancelable: true }));
      }
    });

    // Fetch config and conversations
    await Promise.all([fetchConfig(), loadConversations()]);
  }

  async function fetchConfig() {
    try {
      const res = await fetch("/api/config", { headers: authHeaders() });
      if (res.status === 401) {
        logout();
        return;
      }
      const data = await res.json();

      const sSel = serverSelect();
      sSel.innerHTML = "";
      (data.servers || []).forEach(function (s) {
        const opt = document.createElement("option");
        opt.value = s.name;
        opt.textContent = s.name;
        sSel.appendChild(opt);
      });

      const mSel = modelSelect();
      mSel.innerHTML = "";
      (data.models || []).forEach(function (m) {
        const opt = document.createElement("option");
        opt.value = m.id;
        opt.textContent = m.name || m.id;
        mSel.appendChild(opt);
      });
    } catch (err) {
      console.error("Failed to fetch config:", err);
    }
  }

  // ---------------------------------------------------------------------------
  // Conversations sidebar
  // ---------------------------------------------------------------------------

  async function loadConversations() {
    try {
      const res = await fetch("/api/conversations", { headers: authHeaders() });
      if (res.status === 401) {
        logout();
        return;
      }
      const data = await res.json();
      renderConversationList(data.conversations || []);
    } catch (err) {
      console.error("Failed to load conversations:", err);
    }
  }

  function renderConversationList(conversations) {
    const el = convList();
    el.innerHTML = "";

    if (conversations.length === 0) {
      el.innerHTML = '<div class="conv-empty">No conversations yet</div>';
      return;
    }

    conversations.forEach(function (conv) {
      const item = document.createElement("div");
      item.className = "conv-item" + (conv.id === currentConversationId ? " active" : "");
      item.dataset.id = conv.id;

      const title = conv.title || conv.server_name + " / " + conv.model;
      const date = new Date(conv.updated_at * 1000);
      const dateStr = date.toLocaleDateString() + " " + date.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });

      item.innerHTML =
        '<div class="conv-title">' + escapeHtml(title) + "</div>" +
        '<div class="conv-meta">' + escapeHtml(dateStr) + "</div>" +
        '<button class="conv-delete" title="Delete conversation">&times;</button>';

      item.addEventListener("click", function (e) {
        if (e.target.classList.contains("conv-delete")) {
          e.stopPropagation();
          deleteConversation(conv.id);
          return;
        }
        loadConversation(conv.id);
      });

      el.appendChild(item);
    });
  }

  async function loadConversation(id) {
    currentConversationId = id;

    // Highlight in sidebar
    document.querySelectorAll(".conv-item").forEach(function (el) {
      el.classList.toggle("active", Number(el.dataset.id) === id);
    });

    try {
      const res = await fetch("/api/conversations/" + id + "/messages", {
        headers: authHeaders(),
      });
      if (res.status === 401) {
        logout();
        return;
      }
      const data = await res.json();
      renderAllMessages(data.messages || []);
    } catch (err) {
      console.error("Failed to load conversation:", err);
    }
  }

  async function deleteConversation(id) {
    if (!confirm("Delete this conversation?")) return;
    try {
      await fetch("/api/conversations/" + id, {
        method: "DELETE",
        headers: authHeaders(),
      });
      if (id === currentConversationId) {
        currentConversationId = null;
        clearMessages();
      }
      await loadConversations();
    } catch (err) {
      console.error("Failed to delete conversation:", err);
    }
  }

  function newChat() {
    currentConversationId = null;
    clearMessages();
    document.querySelectorAll(".conv-item").forEach(function (el) {
      el.classList.remove("active");
    });
    messageInput().focus();
  }

  // ---------------------------------------------------------------------------
  // Message rendering
  // ---------------------------------------------------------------------------

  function clearMessages() {
    const el = messagesEl();
    el.innerHTML = "";
    showEmptyState();
  }

  function showEmptyState() {
    const el = messagesEl();
    if (!el.querySelector(".empty-state")) {
      const div = document.createElement("div");
      div.className = "empty-state";
      div.id = "empty-state";
      div.innerHTML =
        "<p>Select a conversation or start a new chat.</p>" +
        "<p>Choose a mission server and model above, then type your question below.</p>";
      el.appendChild(div);
    }
  }

  function hideEmptyState() {
    const es = emptyState();
    if (es) es.remove();
  }

  function renderAllMessages(messages) {
    const el = messagesEl();
    el.innerHTML = "";

    if (messages.length === 0) {
      showEmptyState();
      return;
    }

    messages.forEach(function (msg) {
      switch (msg.role) {
        case "user":
          appendUserMessage(msg.content);
          break;
        case "assistant":
          appendAssistantMessage(msg.content);
          break;
        case "tool_call":
          appendToolCall(parseToolContent(msg.content));
          break;
        case "tool_result":
          appendToolResult(msg.content);
          break;
      }
    });

    scrollToBottom();
  }

  function appendUserMessage(content) {
    hideEmptyState();
    const bubble = document.createElement("div");
    bubble.className = "message message-user";
    bubble.innerHTML = '<div class="message-content">' + escapeHtml(content) + "</div>";
    messagesEl().appendChild(bubble);
    scrollToBottom();
    return bubble;
  }

  function appendAssistantMessage(content) {
    hideEmptyState();
    const bubble = document.createElement("div");
    bubble.className = "message message-assistant";
    bubble.innerHTML = '<div class="message-content">' + formatAssistantContent(content) + "</div>";
    messagesEl().appendChild(bubble);
    scrollToBottom();
    return bubble;
  }

  function createStreamingAssistantBubble() {
    hideEmptyState();
    const bubble = document.createElement("div");
    bubble.className = "message message-assistant";
    bubble.innerHTML = '<div class="message-content"></div>';
    messagesEl().appendChild(bubble);
    scrollToBottom();
    return bubble;
  }

  function updateStreamingBubble(bubble, fullText) {
    const contentEl = bubble.querySelector(".message-content");
    contentEl.innerHTML = formatAssistantContent(fullText);
    scrollToBottom();
  }

  function appendToolCall(toolInfo) {
    hideEmptyState();
    const block = document.createElement("div");
    block.className = "message message-tool-call";

    const toolName = toolInfo.name || "unknown";
    const toolArgs = toolInfo.arguments || {};
    const argsJson = JSON.stringify(toolArgs, null, 2);

    block.innerHTML =
      '<div class="tool-header">' +
        '<span class="tool-icon">&#9881;</span>' +
        '<span class="tool-label">Calling <strong>' + escapeHtml(toolName) + "</strong></span>" +
        '<button class="tool-toggle" aria-expanded="false">Show args</button>' +
      "</div>" +
      '<div class="tool-body collapsed">' +
        '<pre class="tool-json">' + escapeHtml(argsJson) + "</pre>" +
      "</div>";

    const toggleBtn = block.querySelector(".tool-toggle");
    const body = block.querySelector(".tool-body");
    toggleBtn.addEventListener("click", function () {
      const expanded = body.classList.toggle("collapsed");
      toggleBtn.textContent = expanded ? "Show args" : "Hide args";
      toggleBtn.setAttribute("aria-expanded", String(!expanded));
    });

    messagesEl().appendChild(block);
    scrollToBottom();
    return block;
  }

  function appendToolResult(content) {
    hideEmptyState();
    const block = document.createElement("div");
    block.className = "message message-tool-result";

    let prettyContent;
    try {
      prettyContent = JSON.stringify(JSON.parse(content), null, 2);
    } catch (e) {
      prettyContent = content;
    }

    block.innerHTML =
      '<div class="tool-header">' +
        '<span class="tool-icon">&#9776;</span>' +
        '<span class="tool-label">Tool result</span>' +
        '<button class="tool-toggle" aria-expanded="false">Show result</button>' +
      "</div>" +
      '<div class="tool-body collapsed">' +
        '<pre class="tool-json">' + escapeHtml(prettyContent) + "</pre>" +
      "</div>";

    const toggleBtn = block.querySelector(".tool-toggle");
    const body = block.querySelector(".tool-body");
    toggleBtn.addEventListener("click", function () {
      const expanded = body.classList.toggle("collapsed");
      toggleBtn.textContent = expanded ? "Show result" : "Hide result";
      toggleBtn.setAttribute("aria-expanded", String(!expanded));
    });

    messagesEl().appendChild(block);
    scrollToBottom();
    return block;
  }

  function appendError(content) {
    hideEmptyState();
    const block = document.createElement("div");
    block.className = "message message-error";
    block.innerHTML = '<div class="message-content">' + escapeHtml(content) + "</div>";
    messagesEl().appendChild(block);
    scrollToBottom();
  }

  // ---------------------------------------------------------------------------
  // Sending messages (SSE over POST with ReadableStream)
  // ---------------------------------------------------------------------------

  async function onSubmit(e) {
    e.preventDefault();
    const text = messageInput().value.trim();
    if (!text || isStreaming) return;
    await sendMessage(text);
  }

  async function sendMessage(text) {
    const server = serverSelect().value;
    const model = modelSelect().value;

    if (!server || !model) {
      alert("Please select a mission server and model.");
      return;
    }

    // Show user message
    appendUserMessage(text);
    messageInput().value = "";
    messageInput().style.height = "auto";

    isStreaming = true;
    sendBtn().disabled = true;
    sendBtn().textContent = "...";

    abortController = new AbortController();

    const body = {
      message: text,
      server_name: server,
      model_id: model,
    };
    if (currentConversationId) {
      body.conversation_id = currentConversationId;
    }

    let streamingBubble = null;
    let assistantText = "";

    try {
      const res = await fetch("/api/chat", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          ...authHeaders(),
        },
        body: JSON.stringify(body),
        signal: abortController.signal,
      });

      if (res.status === 401) {
        logout();
        return;
      }

      if (!res.ok) {
        const errData = await res.json().catch(function () {
          return { detail: "Request failed" };
        });
        appendError(errData.detail || "Request failed with status " + res.status);
        return;
      }

      const reader = res.body.getReader();
      const decoder = new TextDecoder();
      let buffer = "";

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split("\n");
        // Keep the last incomplete line in the buffer
        buffer = lines.pop() || "";

        for (let i = 0; i < lines.length; i++) {
          const line = lines[i].trim();
          if (!line.startsWith("data: ")) continue;

          let event;
          try {
            event = JSON.parse(line.slice(6));
          } catch (e) {
            continue;
          }

          switch (event.type) {
            case "text":
              if (!streamingBubble) {
                streamingBubble = createStreamingAssistantBubble();
              }
              assistantText += event.content;
              updateStreamingBubble(streamingBubble, assistantText);
              break;

            case "tool_call":
              appendToolCall({
                name: event.tool_name,
                arguments: event.tool_args || {},
              });
              break;

            case "tool_result":
              appendToolResult(event.content || "");
              break;

            case "error":
              appendError(event.content || "Unknown error");
              break;

            case "done":
              if (event.conversation_id) {
                currentConversationId = event.conversation_id;
              }
              break;
          }
        }
      }
    } catch (err) {
      if (err.name !== "AbortError") {
        appendError("Connection error: " + err.message);
      }
    } finally {
      isStreaming = false;
      abortController = null;
      sendBtn().disabled = false;
      sendBtn().textContent = "Send";
      await loadConversations();
    }
  }

  // ---------------------------------------------------------------------------
  // Text formatting helpers
  // ---------------------------------------------------------------------------

  /**
   * Minimal markdown-like formatting for assistant messages.
   * Supports: fenced code blocks (```), inline code (`), bold (**), italic (*).
   */
  function formatAssistantContent(text) {
    if (!text) return "";

    // Escape HTML first
    let html = escapeHtml(text);

    // Fenced code blocks: ```lang\n...\n```
    html = html.replace(/```(\w*)\n([\s\S]*?)```/g, function (match, lang, code) {
      return '<pre class="code-block"><code>' + code + "</code></pre>";
    });

    // Inline code: `...`
    html = html.replace(/`([^`]+)`/g, "<code>$1</code>");

    // Bold: **...**
    html = html.replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>");

    // Italic: *...*  (but not inside bold)
    html = html.replace(/(?<!\*)\*([^*]+)\*(?!\*)/g, "<em>$1</em>");

    // Line breaks
    html = html.replace(/\n/g, "<br>");

    return html;
  }

  function escapeHtml(str) {
    if (!str) return "";
    return str
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;")
      .replace(/'/g, "&#039;");
  }

  function parseToolContent(content) {
    try {
      return JSON.parse(content);
    } catch (e) {
      return { name: "unknown", arguments: {} };
    }
  }

  function scrollToBottom() {
    const area = messageArea();
    if (area) {
      area.scrollTop = area.scrollHeight;
    }
  }

  // ---------------------------------------------------------------------------
  // Boot
  // ---------------------------------------------------------------------------

  document.addEventListener("DOMContentLoaded", init);
})();
