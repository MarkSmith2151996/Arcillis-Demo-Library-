import { getCurrentWindow, LogicalSize } from "@tauri-apps/api/window";

const DEEPSEEK_API_KEY = import.meta.env.VITE_DEEPSEEK_API_KEY;
const DEEPSEEK_URL = "https://api.deepseek.com/v1/chat/completions";
const CHAT_MODEL = "deepseek-v4-flash";
const CHAT_SYSTEM_PROMPT = `You are an AI assistant embedded in a document extraction toolbar.
You help users understand extraction results, investigate accuracy issues,
and take actions like exporting data or reprocessing invoices.
You have access to tools that let you query the extraction database,
get detailed results, export data, and control the application.
Be concise and practical. When a user asks about data, use your query
tools rather than guessing. When showing numbers, format them clearly.`;

const buttonIntents = {
  feed: "Scan the inbox for unread invoice attachments and tell me what was found.",
  run: "Run extraction on the staged inbox files and summarize the results.",
  push: "Export all clean extraction results to CSV.",
  ask: "Summarize the current invoice extraction results and flag any accuracy issues.",
};

const mockConfig = {
  name: "ARC",
  layout: "nokia",
  status: [
    { type: "success", text: "12 invoices processed" },
    { type: "warning", text: "1 needs review" },
  ],
  buttons: [
    { id: "feed", label: "FEED", icon: "upload", color: "var(--accent-blue)" },
    { id: "run", label: "RUN", icon: "bolt", color: "var(--accent-amber)" },
    { id: "push", label: "PUSH", icon: "download", color: "var(--accent-green)" },
    { id: "ask", label: "ASK", icon: "message-circle", color: "var(--accent-purple)" },
  ],
  chatHistory: [
    { role: "assistant", text: "12 invoices processed today. 1 flagged — invoice #47 is missing a vendor ID." },
    { role: "user", text: "Export the good ones" },
    { role: "assistant", text: "Done — 11 rows exported to invoices_july.xlsx" },
  ],
};

let state = {
  serverUrl: "http://localhost:8098",
  appName: "ARC",
  layout: "nokia",
  statusLog: [...mockConfig.status],
  chatMessages: [...mockConfig.chatHistory],
  mcpTools: [],
  chatBusy: false,
};

const appWindow = getCurrentWindow();

function $(sel) {
  return document.querySelector(sel);
}

function escapeHtml(value) {
  const node = document.createElement("span");
  node.textContent = value;
  return node.innerHTML;
}

async function mcpListTools(demo) {
  const res = await fetch(`${state.serverUrl}/mcp/tools/list`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ demo }),
  });
  if (!res.ok) throw new Error(`MCP tool discovery failed (${res.status}).`);
  return res.json();
}

async function mcpCallTool(demo, tool, args = {}) {
  const res = await fetch(`${state.serverUrl}/mcp/tools/call`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ demo, tool, args }),
  });
  if (!res.ok) throw new Error(`MCP tool ${tool} failed (${res.status}): ${await res.text()}`);
  return res.json();
}

async function discoverMcpTools() {
  try {
    const tools = await mcpListTools("document_extractor");
    if (!Array.isArray(tools)) throw new Error("MCP returned an invalid tool list.");
    state.mcpTools = tools.map((tool) => ({ type: "function", function: tool }));
    addStatus("success", `${tools.length} MCP tools connected`);
  } catch (error) {
    state.mcpTools = [];
    addStatus("warning", `MCP tools unavailable: ${error.message}`);
  }
}

function renderTitlebar() {
  const label = $("#titlebar-label");
  if (label) label.textContent = state.appName;
}

function renderAll() {
  renderTitlebar();
  renderNokia();
  renderStrip();
  renderChat();
  showLayoutSync(state.layout);
}

async function showLayout(name) {
  document.querySelectorAll(".layout").forEach((el) => el.classList.add("hidden"));
  const target = $(`#layout-${name}`);
  if (target) target.classList.remove("hidden");

  if (name === "nokia" || name === "chat") {
    await appWindow.setSize(new LogicalSize(280, 480));
  } else if (name === "strip") {
    await appWindow.setSize(new LogicalSize(280, 180));
  }
}

async function setWindowSize(w, h) {
  await appWindow.setSize(new LogicalSize(w, h));
}

function showLayoutSync(name) {
  document.querySelectorAll(".layout").forEach((el) => el.classList.add("hidden"));
  const target = $(`#layout-${name}`);
  if (target) target.classList.remove("hidden");

  if (name === "nokia" || name === "chat") {
    setWindowSize(280, 480);
  } else if (name === "strip") {
    setWindowSize(280, 180);
  }
}

function renderNokia() {
  const el = $("#layout-nokia");
  if (!el) return;
  el.innerHTML = `
    <div class="nokia-screen">
      <div class="nokia-status">
        ${state.statusLog
          .map(
            (s) =>
              `<div class="status-line"><span class="dot ${s.type}"></span>${s.text}</div>`
          )
          .join("")}
      </div>
      <div class="nokia-chat">
        ${state.chatMessages
          .map(
            (m) =>
              `<div class="chat-bubble ${m.role}${m.typing ? " typing" : ""}">${escapeHtml(m.text)}</div>`
          )
          .join("")}
      </div>
    </div>
    <div class="nokia-grid">
      ${mockConfig.buttons
        .map(
          (b) =>
            `<button class="nokia-btn" data-btn="${b.id}" style="color:${b.color}">
              <span class="icon"><i class="ti ti-${b.icon}"></i></span>
              ${b.label}
            </button>`
        )
        .join("")}
    </div>
  `;

  el.querySelectorAll(".nokia-btn").forEach((btn) => {
    btn.addEventListener("click", () => handleButtonClick(btn.dataset.btn));
  });
}

function renderStrip() {
  const el = $("#layout-strip");
  if (!el) return;
  el.innerHTML = `
    <div class="strip-header-right">
      <button class="strip-settings" id="strip-settings-btn"><i class="ti ti-settings"></i></button>
    </div>
    <div class="strip-status" id="strip-status-slots"></div>
    <input type="text" class="strip-input" id="strip-chat-input" placeholder="Type a message..." />
    <div class="strip-buttons">
      ${mockConfig.buttons
        .map(
          (b) =>
            `<button class="strip-btn" data-btn="${b.id}" style="color:${b.color}" title="${b.label}">
              <i class="ti ti-${b.icon}"></i>
            </button>`
        )
        .join("")}
    </div>
  `;

  renderStatusInto($("#strip-status-slots"));

  el.querySelectorAll(".strip-btn").forEach((btn) => {
    btn.addEventListener("click", () => handleButtonClick(btn.dataset.btn));
  });

  const input = $("#strip-chat-input");
  if (input) {
    input.addEventListener("keydown", (e) => {
      if (e.key === "Enter") handleChatSend(input.value, input);
    });
  }

  const settingsBtn = $("#strip-settings-btn");
  if (settingsBtn) {
    settingsBtn.addEventListener("click", toggleAdmin);
  }
}

function renderChat() {
  const el = $("#layout-chat");
  if (!el) return;
  el.innerHTML = `
    <div class="chat-header">
      <div class="chat-avatar"><i class="ti ti-robot"></i></div>
      <div class="chat-header-info">
        <div class="chat-header-name">${state.appName}</div>
        <div class="chat-header-status">${state.statusLog[0]?.text || ""}</div>
      </div>
    </div>
    <div class="chat-messages" id="chat-messages-container">
      ${state.chatMessages
        .map(
          (m) =>
              `<div class="chat-bubble ${m.role}${m.typing ? " typing" : ""}">${escapeHtml(m.text)}</div>`
        )
        .join("")}
    </div>
    <div class="chat-pills">
      ${mockConfig.buttons
        .map(
          (b) =>
            `<button class="chat-pill" data-btn="${b.id}" style="color:${b.color}">
              <i class="ti ti-${b.icon}"></i> ${b.label}
            </button>`
        )
        .join("")}
    </div>
    <div class="chat-input-row">
      <input type="text" class="chat-text-input" id="chat-text-input" placeholder="Ask ARC anything..." />
      <button class="chat-send-btn" id="chat-send-btn"><i class="ti ti-send"></i></button>
    </div>
  `;

  el.querySelectorAll(".chat-pill").forEach((pill) => {
    pill.addEventListener("click", () => handleButtonClick(pill.dataset.btn));
  });

  const sendBtn = $("#chat-send-btn");
  const textInput = $("#chat-text-input");
  if (sendBtn && textInput) {
    sendBtn.addEventListener("click", () => handleChatSend(textInput.value, textInput));
    textInput.addEventListener("keydown", (e) => {
      if (e.key === "Enter") handleChatSend(textInput.value, textInput);
    });
  }
}

function renderStatusInto(container) {
  if (!container) return;
  container.innerHTML = state.statusLog
    .map(
      (s) =>
        `<span class="strip-status" style="display:inline-flex;align-items:center;gap:6px;margin-right:12px;font-size:12px;color:var(--text-secondary);">
          <span class="dot ${s.type}"></span>${s.text}
        </span>`
    )
    .join("");
}

function addStatus(type, text) {
  state.statusLog.push({ type, text });
  if (state.statusLog.length > 5) state.statusLog.shift();
  refreshRenderedStatus();
}

function refreshRenderedStatus() {
  renderStatusInto($("#strip-status-slots"));
  const nokiaStatus = document.querySelector("#layout-nokia .nokia-status");
  if (nokiaStatus) {
    nokiaStatus.innerHTML = state.statusLog
      .map(
        (s) =>
          `<div class="status-line"><span class="dot ${s.type}"></span>${s.text}</div>`
      )
      .join("");
  }
  const chatStatus = $("#layout-chat .chat-header-status");
  if (chatStatus) {
    chatStatus.textContent = state.statusLog[state.statusLog.length - 1]?.text || "";
  }
}

function handleButtonClick(btnId) {
  const touched = new Event("button-click", { bubbles: true });
  const el = document.querySelector(`[data-btn="${btnId}"]`);
  if (el) {
    el.style.transform = "scale(0.92)";
    setTimeout(() => {
      el.style.transform = "";
    }, 150);
    el.dispatchEvent(touched);
  }

  handleChatSend(buttonIntents[btnId] || `Handle the ${btnId} toolbar action.`);
}

async function handleChatSend(text, inputEl) {
  const message = text.trim();
  if (!message || state.chatBusy) return;
  if (!DEEPSEEK_API_KEY) {
    state.chatMessages.push({ role: "assistant", text: "Set VITE_DEEPSEEK_API_KEY before using ARC chat." });
    rerenderChats();
    return;
  }

  state.chatBusy = true;
  state.chatMessages.push({ role: "user", text: message });
  if (inputEl) inputEl.value = "";
  state.chatMessages.push({ role: "assistant", text: "ARC is thinking...", typing: true });
  rerenderChats();
  scrollChatsToBottom();

  try {
    const response = await runChatLoop();
    state.chatMessages.push({ role: "assistant", text: response });
    addStatus("success", "Response ready");
  } catch (error) {
    state.chatMessages.push({ role: "assistant", text: `I could not complete that request: ${error.message}` });
    addStatus("warning", `Chat error: ${error.message}`);
  } finally {
    state.chatMessages = state.chatMessages.filter((entry) => !entry.typing);
    state.chatBusy = false;
    rerenderChats();
    scrollChatsToBottom();
  }
}

async function runChatLoop() {
  const messages = [
    { role: "system", content: CHAT_SYSTEM_PROMPT },
    ...state.chatMessages
      .filter((message) => !message.typing)
      .slice(-20)
      .map((message) => ({ role: message.role, content: message.text })),
  ];

  for (let round = 0; round < 6; round += 1) {
    const request = { model: CHAT_MODEL, messages };
    if (state.mcpTools.length) request.tools = state.mcpTools;
    const res = await fetch(DEEPSEEK_URL, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Authorization: `Bearer ${DEEPSEEK_API_KEY}`,
      },
      body: JSON.stringify(request),
    });
    if (!res.ok) throw new Error(`DeepSeek request failed (${res.status}): ${await res.text()}`);
    const payload = await res.json();
    const assistantMessage = payload.choices?.[0]?.message;
    if (!assistantMessage) throw new Error("DeepSeek returned no message.");
    const toolCalls = assistantMessage.tool_calls || [];
    if (!toolCalls.length) return assistantMessage.content || "I completed that request.";

    messages.push(assistantMessage);
    for (const toolCall of toolCalls) {
      const name = toolCall.function?.name;
      addStatus("success", `Running ${name}...`);
      let result;
      try {
        result = await mcpCallTool("document_extractor", name, JSON.parse(toolCall.function?.arguments || "{}"));
      } catch (error) {
        result = { error: error.message };
      }
      messages.push({
        role: "tool",
        tool_call_id: toolCall.id,
        content: JSON.stringify(result),
      });
    }
  }
  throw new Error("The assistant exceeded the six-round tool-call limit.");
}

function rerenderChats() {
  const nokiaChat = $("#layout-nokia .nokia-chat");
  if (nokiaChat) {
    nokiaChat.innerHTML = state.chatMessages
      .map((m) => `<div class="chat-bubble ${m.role}${m.typing ? " typing" : ""}">${escapeHtml(m.text)}</div>`)
      .join("");
  }

  const chatMsgs = $("#chat-messages-container");
  if (chatMsgs) {
    chatMsgs.innerHTML = state.chatMessages
      .map((m) => `<div class="chat-bubble ${m.role}${m.typing ? " typing" : ""}">${escapeHtml(m.text)}</div>`)
      .join("");
  }
}

function scrollChatsToBottom() {
  const nokiaChat = $("#layout-nokia .nokia-chat");
  if (nokiaChat) nokiaChat.scrollTop = nokiaChat.scrollHeight;
  const chatMsgs = $("#chat-messages-container");
  if (chatMsgs) chatMsgs.scrollTop = chatMsgs.scrollHeight;
}

function toggleAdmin() {
  const overlay = $("#admin-overlay");
  if (!overlay) return;
  if (overlay.classList.contains("hidden")) {
    showAdmin();
  } else {
    overlay.classList.add("hidden");
  }
}

function showAdmin() {
  const overlay = $("#admin-overlay");
  if (!overlay) return;
  overlay.innerHTML = `
    <div class="admin-panel">
      <h3>Settings</h3>
      <div class="admin-field">
        <label>Layout</label>
        <div class="admin-radio-group">
          <label><input type="radio" name="admin-layout" value="nokia" ${state.layout === "nokia" ? "checked" : ""} /> Nokia</label>
          <label><input type="radio" name="admin-layout" value="strip" ${state.layout === "strip" ? "checked" : ""} /> Strip</label>
          <label><input type="radio" name="admin-layout" value="chat" ${state.layout === "chat" ? "checked" : ""} /> Chat</label>
        </div>
      </div>
      <div class="admin-field">
        <label>Server URL</label>
        <input type="text" id="admin-server-url" value="${state.serverUrl}" />
      </div>
      <div class="admin-field">
        <label>App Name</label>
        <input type="text" id="admin-app-name" value="${state.appName}" />
      </div>
      <button class="admin-close" id="admin-close-btn">Close</button>
    </div>
  `;
  overlay.classList.remove("hidden");

  document.querySelectorAll("input[name='admin-layout']").forEach((radio) => {
    radio.addEventListener("change", (e) => {
      state.layout = e.target.value;
      showLayoutSync(state.layout);
    });
  });

  const nameInput = $("#admin-app-name");
  if (nameInput) {
    nameInput.addEventListener("input", () => {
      state.appName = nameInput.value;
      renderTitlebar();
    });
  }

  const urlInput = $("#admin-server-url");
  if (urlInput) {
    urlInput.addEventListener("input", () => {
      state.serverUrl = urlInput.value;
    });
  }

  const closeBtn = $("#admin-close-btn");
  if (closeBtn) {
    closeBtn.addEventListener("click", () => overlay.classList.add("hidden"));
  }
}

function initWindowControls() {
  console.log("initWindowControls running");

  const minBtn = $("#minimize");
  const closeBtn = $("#close");
  const titlebar = $(".titlebar");

  console.log("minBtn:", !!minBtn, "closeBtn:", !!closeBtn, "titlebar:", !!titlebar);

  if (titlebar) {
    titlebar.addEventListener("mousedown", (e) => {
      if (e.target.closest(".titlebar-btn")) return;
      try {
        appWindow.startDragging();
      } catch (err) {
        console.error("startDragging failed:", err);
      }
    });
  }

  if (minBtn) {
    minBtn.addEventListener("click", () => {
      try {
        appWindow.minimize();
      } catch (err) {
        console.error("minimize failed:", err);
      }
    });
  }

  if (closeBtn) {
    closeBtn.addEventListener("click", () => {
      try {
        appWindow.close();
      } catch (err) {
        console.error("close failed:", err);
        try {
          window.close();
        } catch (fallbackErr) {
          console.error("window.close fallback also failed:", fallbackErr);
        }
      }
    });
  }

  console.log("Window controls initialized");
}

function initKeyboardShortcuts() {
  document.addEventListener("keydown", (e) => {
    if ((e.ctrlKey || e.metaKey) && e.shiftKey && e.key.toLowerCase() === "a") {
      e.preventDefault();
      toggleAdmin();
    }
  });
}

initWindowControls();
initKeyboardShortcuts();
renderAll();
discoverMcpTools();
