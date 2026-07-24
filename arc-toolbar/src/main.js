import { getCurrentWindow, LogicalSize } from "@tauri-apps/api/window";
import { renderDisplay } from "./components.js";

const STORAGE_KEY = "arc-toolbar-settings";
const SIZES = { compact: 280, standard: 400, wide: 600, full: 800, short: 200, tall: 600 };
const DEFAULT_CONFIG = {
  loadingMessage: "Working...",
  colors: { success: "#22C55E", warning: "#F59E0B", danger: "#EF4444", neutral: "#9CA3AF", info: "#60A5FA" },
  buttonLabels: { feed: "FEED", run: "RUN", push: "PUSH", ask: "ASK" },
  defaultSize: { width: "compact", height: "standard" },
  persistDisplay: true,
  displayUpdates: "replace",
};
const buttonIntents = {
  feed: "Scan the inbox for unread invoice attachments and tell me what was found.",
  run: "Run extraction on the staged inbox files and summarize the results.",
  push: "Export all clean extraction results to CSV.",
  ask: "Summarize the current invoice extraction results and flag any accuracy issues.",
};
const toolbarButtons = [
  { id: "feed", icon: "upload", color: "var(--accent-blue)" },
  { id: "run", icon: "bolt", color: "var(--accent-amber)" },
  { id: "push", icon: "download", color: "var(--accent-green)" },
  { id: "ask", icon: "message-circle", color: "var(--accent-purple)" },
];
const defaultDisplay = {
  size: { width: "compact", height: "standard" },
  rows: [
    { components: [{ type: "status", width: "full", label: "Pipeline", value: "Ready", color: "success" }] },
    { components: [{ type: "text", width: "full", label: "ARC", value: "Ask ARC to scan, extract, or export invoices.", color: "info" }] },
  ],
};
function loadStored() {
  try { return JSON.parse(localStorage.getItem(STORAGE_KEY)) || {}; } catch { return {}; }
}
const stored = loadStored();
let state = {
  serverUrl: "",
  appName: stored.appName || "ARC",
  layout: stored.layout || "nokia",
  config: { ...DEFAULT_CONFIG, ...stored.config, colors: { ...DEFAULT_CONFIG.colors, ...stored.config?.colors }, buttonLabels: { ...DEFAULT_CONFIG.buttonLabels, ...stored.config?.buttonLabels }, defaultSize: { ...DEFAULT_CONFIG.defaultSize, ...stored.config?.defaultSize } },
  display: stored.config?.persistDisplay && stored.display ? stored.display : defaultDisplay,
  displayStack: stored.config?.persistDisplay && Array.isArray(stored.displayStack) ? stored.displayStack : [],
  screenView: "display",
  statusLog: [{ type: "success", text: "ARC ready" }],
  chatMessages: [],
  sessionId: crypto.randomUUID?.() || `arc-${Date.now()}`,
  chatBusy: false,
};
const appWindow = getCurrentWindow();
const $ = (selector) => document.querySelector(selector);

function renderChatMarkdown(text) {
  const escaped = String(text ?? "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
  const renderInline = (line) => {
    const blockquote = line.replace(/^\s*&gt;\s?/, "");
    const heading = blockquote.match(/^\s*#{1,6}\s*(.*)$/);
    const content = (heading ? heading[1] : blockquote)
      .replace(/`/g, "")
      .replace(/\[([^\]]*)\]\([^)]*\)/g, "$1")
      .replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>");
    return heading ? `<strong>${content}</strong>` : content;
  };
  const lines = escaped.split("\n");
  const output = [];

  for (let index = 0; index < lines.length; index += 1) {
    const line = lines[index];
    if (/^\s*---+\s*$/.test(line)) continue;

    const unordered = line.match(/^\s*[-*]\s+(.*)$/);
    const ordered = line.match(/^\s*\d+\.\s+(.*)$/);
    if (unordered || ordered) {
      const tag = unordered ? "ul" : "ol";
      const items = [];
      while (index < lines.length) {
        const item = tag === "ul"
          ? lines[index].match(/^\s*[-*]\s+(.*)$/)
          : lines[index].match(/^\s*\d+\.\s+(.*)$/);
        if (!item) break;
        items.push(`<li>${renderInline(item[1])}</li>`);
        index += 1;
      }
      output.push(`<${tag}>${items.join("")}</${tag}>`);
      if (index < lines.length && !/^\s*$/.test(lines[index]) && !/^\s*---+\s*$/.test(lines[index])) output.push("<br>");
      index -= 1;
      continue;
    }

    output.push(renderInline(line));
    if (index < lines.length - 1) output.push("<br>");
  }

  return output.join("");
}

function saveState() {
  localStorage.setItem(STORAGE_KEY, JSON.stringify({ serverUrl: state.serverUrl, appName: state.appName, layout: state.layout, config: state.config, display: state.config.persistDisplay ? state.display : null, displayStack: state.config.persistDisplay ? state.displayStack : [] }));
}
function buttonMarkup(button, className) {
  return `<button class="${className}" data-btn="${button.id}" style="color:${button.color}" title="${state.config.buttonLabels[button.id]}"><i class="ti ti-${button.icon}"></i><span>${state.config.buttonLabels[button.id]}</span></button>`;
}
function renderTitlebar() { $("#titlebar-label").textContent = state.appName; }
function renderToolbarButtons(container, className) {
  container.innerHTML = toolbarButtons.map((button) => buttonMarkup(button, className)).join("");
  container.querySelectorAll("[data-btn]").forEach((button) => button.addEventListener("click", () => handleToolbarAction(button.dataset.btn)));
}
function renderNokia() {
  const el = $("#layout-nokia");
  el.innerHTML = `<div class="nokia-screen"><div class="screen-header"><span class="screen-status">${state.statusLog.at(-1)?.text || ""}</span><button class="screen-chat-toggle" id="screen-chat-toggle" title="Toggle chat"><i class="ti ti-${state.screenView === "display" ? "message-circle" : "layout-dashboard"}"></i></button></div><div class="screen-content" id="screen-content"></div></div><div class="nokia-grid" id="nokia-buttons"></div>`;
  $("#screen-chat-toggle").addEventListener("click", toggleScreenView);
  renderToolbarButtons($("#nokia-buttons"), "nokia-btn");
  renderScreenContent();
}
function renderScreenContent() {
  const content = $("#screen-content");
  if (!content) return;
  content.replaceChildren();
  if (state.screenView === "chat") {
    const chat = document.createElement("div");
    chat.className = "nokia-chat";
    appendChatMessages(chat);
    const row = document.createElement("div");
    row.className = "nokia-chat-input-row";
    row.innerHTML = `<input id="nokia-chat-input" placeholder="Ask ARC..." /><button id="nokia-chat-send"><i class="ti ti-send"></i></button>`;
    row.querySelector("button").addEventListener("click", () => handleChatSend(row.querySelector("input").value, row.querySelector("input")));
    row.querySelector("input").addEventListener("keydown", (event) => { if (event.key === "Enter") handleChatSend(event.target.value, event.target); });
    content.append(chat, row);
    chat.scrollTop = chat.scrollHeight;
    return;
  }
  const displays = state.config.displayUpdates === "stack" ? [...state.displayStack, state.display] : [state.display];
  displays.forEach((display) => content.append(renderDisplay(display, { colors: state.config.colors, onIntent: injectIntent })));
  if (state.chatBusy) content.append(createLoadingOverlay());
}
function appendChatMessages(container) {
  state.chatMessages.forEach((message) => {
    const bubble = document.createElement("div");
    bubble.className = `chat-bubble ${message.role}${message.typing ? " typing" : ""}`;
    if (message.role === "assistant" && !message.typing) bubble.innerHTML = renderChatMarkdown(message.text);
    else bubble.textContent = message.text;
    container.append(bubble);
  });
}
function createLoadingOverlay() {
  const overlay = document.createElement("div");
  overlay.className = "display-loading";
  overlay.innerHTML = `<span class="loading-spinner"></span><span></span>`;
  overlay.lastElementChild.textContent = state.config.loadingMessage;
  return overlay;
}
function renderStrip() {
  const el = $("#layout-strip");
  el.innerHTML = `<button class="strip-settings" id="strip-settings-btn"><i class="ti ti-settings"></i></button><input type="text" class="strip-input" id="strip-chat-input" placeholder="Type a message..." /><div class="strip-buttons" id="strip-buttons"></div>`;
  renderToolbarButtons($("#strip-buttons"), "strip-btn");
  $("#strip-settings-btn").addEventListener("click", toggleAdmin);
  $("#strip-chat-input").addEventListener("keydown", (event) => { if (event.key === "Enter") handleChatSend(event.target.value, event.target); });
}
function renderChat() {
  const el = $("#layout-chat");
  el.innerHTML = `<div class="chat-header"><div class="chat-avatar"><i class="ti ti-robot"></i></div><div><div class="chat-header-name">${state.appName}</div><div class="chat-header-status">${state.statusLog.at(-1)?.text || ""}</div></div></div><div class="chat-messages" id="chat-messages-container"></div><div class="chat-pills" id="chat-pills"></div><div class="chat-input-row"><input class="chat-text-input" id="chat-text-input" placeholder="Ask ARC anything..." /><button class="chat-send-btn" id="chat-send-btn"><i class="ti ti-send"></i></button></div>`;
  appendChatMessages($("#chat-messages-container"));
  renderToolbarButtons($("#chat-pills"), "chat-pill");
  $("#chat-send-btn").addEventListener("click", () => handleChatSend($("#chat-text-input").value, $("#chat-text-input")));
  $("#chat-text-input").addEventListener("keydown", (event) => { if (event.key === "Enter") handleChatSend(event.target.value, event.target); });
}
function renderAll() { renderTitlebar(); renderNokia(); renderStrip(); renderChat(); showLayoutSync(state.layout); }
function rerenderChats() { renderNokia(); renderChat(); }
function addStatus(type, text) { state.statusLog.push({ type, text }); if (state.statusLog.length > 5) state.statusLog.shift(); renderNokia(); renderChat(); }
function toggleScreenView() { state.screenView = state.screenView === "display" ? "chat" : "display"; renderNokia(); }
function injectIntent(intent) { state.screenView = "display"; handleChatSend(intent); }
function handleToolbarAction(id) { if (id === "ask" && state.layout === "nokia") { state.screenView = "chat"; renderNokia(); $("#nokia-chat-input")?.focus(); return; } handleChatSend(buttonIntents[id] || `Handle the ${id} toolbar action.`); }

async function checkServerHealth() {
  try {
    const res = await fetch(`${state.serverUrl}/mcp/tools/list`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ demo: "document_extractor" }) });
    if (!res.ok) throw new Error(`Server returned ${res.status}`);
    const tools = await res.json();
    if (!Array.isArray(tools)) throw new Error("Server returned an invalid tool list");
    addStatus("success", `Server connected (${tools.length} tools)`);
  } catch (error) {
    addStatus("warning", `Server offline: ${error.message}`);
  }
}

function validateDisplay(display) { return display && Array.isArray(display.rows); }
function updateStreamingBubble(text) {
  const typingIndex = state.chatMessages.findIndex((message) => message.typing);
  if (typingIndex !== -1) {
    state.chatMessages[typingIndex].text = text || "ARC is thinking...";
    rerenderChats();
  }
}
async function runAgentStream(message) {
  const res = await fetch(`${state.serverUrl}/agent/chat`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      message,
      session_id: state.sessionId,
      client_name: state.appName,
      spreadsheet_id: "14ud-CDITpFnNcZwqS0U5zoehthT84978l3Tty1YXT2g",
      demo: "document_extractor",
    }),
  });
  if (!res.ok) throw new Error(`Agent request failed (${res.status}): ${await res.text()}`);
  if (!res.body) throw new Error("Agent response did not include a stream.");

  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  let fullText = "";

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    const lines = buffer.split("\n");
    buffer = lines.pop();

    for (const line of lines) {
      if (!line.startsWith("data: ")) continue;
      const raw = line.slice(6).trim();
      if (!raw) continue;

      let event;
      try { event = JSON.parse(raw); } catch { continue; }

      switch (event.type) {
        case "text":
          fullText += event.content || "";
          updateStreamingBubble(fullText);
          break;
        case "tool_call":
          if (event.name === "update_display") {
            const displayData = event.args?.display || event.args;
            if (validateDisplay(displayData)) {
              try {
                await updateDisplay(displayData);
                addStatus("success", "Display updated");
              } catch (displayErr) {
                console.error("Display update failed:", displayErr);
                addStatus("warning", "Display render failed: " + (displayErr?.message || String(displayErr)));
              }
            } else {
              addStatus("warning", "Invalid display data received");
            }
          } else {
            addStatus("info", `Running ${event.name}...`);
          }
          break;
        case "tool_result":
          addStatus("success", `${event.name} complete`);
          break;
        case "error":
          throw new Error(event.content || "Agent error");
        case "done":
          break;
      }
    }
  }

  return fullText || "Done.";
}
async function handleChatSend(text, inputEl) {
  const message = text.trim();
  if (!message || state.chatBusy) return;
  state.chatBusy = true;
  state.chatMessages.push({ role: "user", text: message }, { role: "assistant", text: "ARC is thinking...", typing: true });
  if (inputEl) inputEl.value = "";
  rerenderChats();
  try {
    const fullText = await runAgentStream(message);
    state.chatMessages = state.chatMessages.filter((entry) => !entry.typing);
    state.chatMessages.push({ role: "assistant", text: fullText });
    addStatus("success", "Response ready");
  } catch (error) {
    state.chatMessages = state.chatMessages.filter((entry) => !entry.typing);
    state.chatMessages.push({ role: "assistant", text: `I could not complete that request: ${error.message}` });
    addStatus("warning", `Chat error: ${error.message}`);
  } finally {
    state.chatBusy = false;
    rerenderChats();
  }
}
async function resetSession() {
  try {
    await fetch(`${state.serverUrl}/agent/reset`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ session_id: state.sessionId }) });
  } catch { /* The local session can still reset if the server is offline. */ }
  state.sessionId = crypto.randomUUID?.() || `arc-${Date.now()}`;
  state.chatMessages = [];
  state.display = defaultDisplay;
  state.displayStack = [];
  saveState();
  rerenderChats();
  addStatus("success", "Session reset");
}
async function updateDisplay(display) {
  if (state.config.displayUpdates === "stack" && state.display) state.displayStack.push(state.display);
  state.display = display;
  state.screenView = "display";
  if (state.layout === "chat") state.layout = "nokia";
  saveState();
  await applyDisplaySize(display.size);
  renderAll();
}
async function applyDisplaySize(size = state.config.defaultSize) { const width = SIZES[size?.width] || SIZES[state.config.defaultSize.width]; const height = SIZES[size?.height] || SIZES[state.config.defaultSize.height]; await animateWindowSize(width, height); }
async function animateWindowSize(width, height) { const [current, scale] = await Promise.all([appWindow.innerSize(), appWindow.scaleFactor()]); const startWidth = current.width / scale; const startHeight = current.height / scale; const steps = 8; for (let step = 1; step <= steps; step += 1) { const progress = step / steps; await appWindow.setSize(new LogicalSize(Math.round(startWidth + (width - startWidth) * progress), Math.round(startHeight + (height - startHeight) * progress))); await new Promise((resolve) => setTimeout(resolve, 18)); } }
async function showLayout(name) { document.querySelectorAll(".layout").forEach((el) => el.classList.add("hidden")); $(`#layout-${name}`).classList.remove("hidden"); if (name === "nokia" || name === "chat") await applyDisplaySize(name === "nokia" ? state.display.size : { width: "compact", height: "standard" }); else await animateWindowSize(280, 180); }
function showLayoutSync(name) { showLayout(name).catch(console.error); }

function toggleAdmin() { const overlay = $("#admin-overlay"); if (overlay.classList.contains("hidden")) showAdmin(); else overlay.classList.add("hidden"); }
function showAdmin() {
  const overlay = $("#admin-overlay");
  overlay.innerHTML = `<div class="admin-panel"><h3>Settings</h3><div class="admin-field"><label>Layout</label><div class="admin-radio-group">${["nokia", "strip", "chat"].map((layout) => `<label><input type="radio" name="admin-layout" value="${layout}" ${state.layout === layout ? "checked" : ""} /> ${layout}</label>`).join("")}</div></div><div class="admin-field"><label>Server URL</label><input type="text" id="admin-server-url" value="${state.serverUrl}" /></div><div class="admin-field"><label>App Name</label><input type="text" id="admin-app-name" value="${state.appName}" /></div><div class="admin-field"><label>Loading message</label><input type="text" id="admin-loading-message" value="${state.config.loadingMessage}" /></div><div class="admin-field"><label>Default display size</label><div class="admin-select-row"><select id="admin-default-width">${["compact", "standard", "wide", "full"].map((value) => `<option ${state.config.defaultSize.width === value ? "selected" : ""}>${value}</option>`).join("")}</select><select id="admin-default-height">${["short", "standard", "tall", "full"].map((value) => `<option ${state.config.defaultSize.height === value ? "selected" : ""}>${value}</option>`).join("")}</select></div></div><div class="admin-field"><label>Display updates</label><select id="admin-display-updates"><option value="replace" ${state.config.displayUpdates === "replace" ? "selected" : ""}>Replace</option><option value="stack" ${state.config.displayUpdates === "stack" ? "selected" : ""}>Stack</option></select></div><div class="admin-field admin-check"><label><input type="checkbox" id="admin-persist-display" ${state.config.persistDisplay ? "checked" : ""} /> Restore display on reopen</label></div><div class="admin-field"><label>Semantic colors</label><div class="admin-colors">${Object.entries(state.config.colors).map(([name, color]) => `<label>${name}<input type="color" data-color="${name}" value="${color}" /></label>`).join("")}</div></div><div class="admin-field"><label>Toolbar labels</label><div class="admin-labels">${toolbarButtons.map((button) => `<input data-label="${button.id}" value="${state.config.buttonLabels[button.id]}" aria-label="${button.id} label" />`).join("")}</div></div><button class="admin-close" id="admin-close-btn">Close</button></div>`;
  overlay.classList.remove("hidden");
  overlay.querySelectorAll("input[name='admin-layout']").forEach((input) => input.addEventListener("change", (event) => { state.layout = event.target.value; saveState(); renderAll(); }));
  bindAdminInput("#admin-server-url", (value) => { state.serverUrl = value; }); bindAdminInput("#admin-app-name", (value) => { state.appName = value; renderTitlebar(); }); bindAdminInput("#admin-loading-message", (value) => { state.config.loadingMessage = value; });
  overlay.querySelectorAll("[data-color]").forEach((input) => input.addEventListener("input", (event) => { state.config.colors[event.target.dataset.color] = event.target.value; saveState(); renderScreenContent(); }));
  overlay.querySelectorAll("[data-label]").forEach((input) => input.addEventListener("input", (event) => { state.config.buttonLabels[event.target.dataset.label] = event.target.value; saveState(); renderAll(); showAdmin(); }));
  $("#admin-default-width").addEventListener("change", (event) => { state.config.defaultSize.width = event.target.value; saveState(); }); $("#admin-default-height").addEventListener("change", (event) => { state.config.defaultSize.height = event.target.value; saveState(); }); $("#admin-display-updates").addEventListener("change", (event) => { state.config.displayUpdates = event.target.value; saveState(); }); $("#admin-persist-display").addEventListener("change", (event) => { state.config.persistDisplay = event.target.checked; saveState(); }); $("#admin-close-btn").addEventListener("click", () => overlay.classList.add("hidden"));
}
function bindAdminInput(selector, update) { $(selector).addEventListener("input", (event) => { update(event.target.value); saveState(); }); }
function initWindowControls() { $(".titlebar").addEventListener("mousedown", (event) => { if (!event.target.closest(".titlebar-btn")) appWindow.startDragging().catch(console.error); }); $("#minimize").addEventListener("click", () => appWindow.minimize().catch(console.error)); $("#close").addEventListener("click", () => appWindow.close().catch(console.error)); }
function initKeyboardShortcuts() { document.addEventListener("keydown", (event) => { if ((event.ctrlKey || event.metaKey) && event.shiftKey && event.key.toLowerCase() === "r") { event.preventDefault(); resetSession(); return; } if ((event.ctrlKey || event.metaKey) && event.shiftKey && event.key.toLowerCase() === "a") { event.preventDefault(); toggleAdmin(); } }); }
initWindowControls(); initKeyboardShortcuts(); renderAll(); checkServerHealth();
