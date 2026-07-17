import { getCurrentWindow, LogicalSize } from "@tauri-apps/api/window";
import { renderDisplay } from "./components.js";

const DEEPSEEK_API_KEY = import.meta.env.VITE_DEEPSEEK_API_KEY;
const DEEPSEEK_URL = "https://api.deepseek.com/v1/chat/completions";
const CHAT_MODEL = "deepseek-v4-flash";
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
const CHAT_SYSTEM_PROMPT = `You are ARC, an AI assistant embedded in a document extraction toolbar. You help users understand extraction results and take actions using the supplied tools. Be concise and practical.

When your response would be clearer as a dashboard, respond with exactly one JSON object, without markdown. Its shape is {"text":"brief chat summary","display":{"size":{"width":"compact|standard|wide|full","height":"short|standard|tall|full"},"rows":[{"components":[...]}]}}. The display component types are number(value,label,color), text(value,label), table(headers,rows), status(label,value,color), progress(label,value,max,color), button(label,intent,color), and divider. Each component may set width to full, half, or third. Use semantic colors success, warning, danger, neutral, info, or a hex color. The frontend handles all markup and styling. Return normal plain text when a visual display is not useful.`;

function loadStored() {
  try { return JSON.parse(localStorage.getItem(STORAGE_KEY)) || {}; } catch { return {}; }
}
const stored = loadStored();
let state = {
  serverUrl: stored.serverUrl || "http://localhost:8098",
  appName: stored.appName || "ARC",
  layout: stored.layout || "nokia",
  config: { ...DEFAULT_CONFIG, ...stored.config, colors: { ...DEFAULT_CONFIG.colors, ...stored.config?.colors }, buttonLabels: { ...DEFAULT_CONFIG.buttonLabels, ...stored.config?.buttonLabels }, defaultSize: { ...DEFAULT_CONFIG.defaultSize, ...stored.config?.defaultSize } },
  display: stored.config?.persistDisplay && stored.display ? stored.display : defaultDisplay,
  displayStack: stored.config?.persistDisplay && Array.isArray(stored.displayStack) ? stored.displayStack : [],
  screenView: "display",
  statusLog: [{ type: "success", text: "ARC ready" }],
  chatMessages: [],
  mcpTools: [],
  chatBusy: false,
};
const appWindow = getCurrentWindow();
const $ = (selector) => document.querySelector(selector);

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
    bubble.textContent = message.text;
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

async function mcpListTools() { const res = await fetch(`${state.serverUrl}/mcp/tools/list`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ demo: "document_extractor" }) }); if (!res.ok) throw new Error(`MCP tool discovery failed (${res.status}).`); return res.json(); }
async function mcpCallTool(tool, args = {}) { const res = await fetch(`${state.serverUrl}/mcp/tools/call`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ demo: "document_extractor", tool, args }) }); if (!res.ok) throw new Error(`MCP tool ${tool} failed (${res.status}): ${await res.text()}`); return res.json(); }
async function discoverMcpTools() { try { const tools = await mcpListTools(); if (!Array.isArray(tools)) throw new Error("MCP returned an invalid tool list."); state.mcpTools = tools.map((tool) => ({ type: "function", function: tool })); addStatus("success", `${tools.length} MCP tools connected`); } catch (error) { state.mcpTools = []; addStatus("warning", `MCP tools unavailable: ${error.message}`); } }

function parseAgentResponse(response) {
  const raw = response.trim().replace(/^```json\s*|\s*```$/g, "");
  try {
    const parsed = JSON.parse(raw);
    if (parsed?.display?.rows || parsed?.rows) return { text: parsed.text || "Display updated.", display: parsed.display || parsed };
  } catch { /* Plain text remains a chat response. */ }
  return { text: response, display: null };
}
function validateDisplay(display) { return display && Array.isArray(display.rows); }
async function handleChatSend(text, inputEl) {
  const message = text.trim();
  if (!message || state.chatBusy) return;
  if (!DEEPSEEK_API_KEY) { state.chatMessages.push({ role: "assistant", text: "Set VITE_DEEPSEEK_API_KEY before using ARC chat." }); rerenderChats(); return; }
  state.chatBusy = true;
  state.chatMessages.push({ role: "user", text: message }, { role: "assistant", text: "ARC is thinking...", typing: true });
  if (inputEl) inputEl.value = "";
  rerenderChats();
  try {
    const result = parseAgentResponse(await runChatLoop());
    state.chatMessages.push({ role: "assistant", text: result.text });
    if (validateDisplay(result.display)) await updateDisplay(result.display);
    addStatus("success", "Response ready");
  } catch (error) { state.chatMessages.push({ role: "assistant", text: `I could not complete that request: ${error.message}` }); addStatus("warning", `Chat error: ${error.message}`); }
  finally { state.chatMessages = state.chatMessages.filter((entry) => !entry.typing); state.chatBusy = false; rerenderChats(); }
}
async function runChatLoop() {
  const messages = [{ role: "system", content: CHAT_SYSTEM_PROMPT }, ...state.chatMessages.filter((message) => !message.typing).slice(-20).map((message) => ({ role: message.role, content: message.text }))];
  for (let round = 0; round < 6; round += 1) {
    const request = { model: CHAT_MODEL, messages }; if (state.mcpTools.length) request.tools = state.mcpTools;
    const res = await fetch(DEEPSEEK_URL, { method: "POST", headers: { "Content-Type": "application/json", Authorization: `Bearer ${DEEPSEEK_API_KEY}` }, body: JSON.stringify(request) });
    if (!res.ok) throw new Error(`DeepSeek request failed (${res.status}): ${await res.text()}`);
    const assistantMessage = (await res.json()).choices?.[0]?.message; if (!assistantMessage) throw new Error("DeepSeek returned no message.");
    const toolCalls = assistantMessage.tool_calls || []; if (!toolCalls.length) return assistantMessage.content || "I completed that request.";
    messages.push(assistantMessage);
    for (const toolCall of toolCalls) { const name = toolCall.function?.name; addStatus("info", `Running ${name}...`); let result; try { result = await mcpCallTool(name, JSON.parse(toolCall.function?.arguments || "{}")); } catch (error) { result = { error: error.message }; } messages.push({ role: "tool", tool_call_id: toolCall.id, content: JSON.stringify(result) }); }
  }
  throw new Error("The assistant exceeded the six-round tool-call limit.");
}
async function updateDisplay(display) { if (state.config.displayUpdates === "stack" && state.display) state.displayStack.push(state.display); state.display = display; saveState(); await applyDisplaySize(display.size); renderNokia(); }
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
function initKeyboardShortcuts() { document.addEventListener("keydown", (event) => { if ((event.ctrlKey || event.metaKey) && event.shiftKey && event.key.toLowerCase() === "a") { event.preventDefault(); toggleAdmin(); } }); }
initWindowControls(); initKeyboardShortcuts(); renderAll(); discoverMcpTools();
