const WIDTHS = { full: "100%", half: "50%", third: "33.333%" };

function text(value) {
  return value === undefined || value === null ? "" : String(value);
}

function colorValue(color, colors) {
  if (typeof color === "string" && color.startsWith("#")) return color;
  return colors[color] || colors.neutral;
}

function componentFrame(type, component, colors) {
  const frame = document.createElement("section");
  frame.className = `display-component display-${type}`;
  frame.style.setProperty("--component-color", colorValue(component.color, colors));
  frame.style.flexBasis = WIDTHS[component.width] || WIDTHS.full;
  return frame;
}

function addLabel(frame, label) {
  if (!label) return;
  const node = document.createElement("div");
  node.className = "display-label";
  node.textContent = text(label);
  frame.append(node);
}

function renderNumber(component, colors) {
  const frame = componentFrame("number", component, colors);
  const value = document.createElement("div");
  value.className = "display-number-value";
  value.textContent = text(component.value);
  frame.append(value);
  addLabel(frame, component.label);
  return frame;
}

function renderText(component, colors) {
  const frame = componentFrame("text", component, colors);
  addLabel(frame, component.label);
  const value = document.createElement("div");
  value.className = "display-text-value";
  value.textContent = text(component.value);
  frame.append(value);
  return frame;
}

function renderTable(component, colors) {
  const frame = componentFrame("table", component, colors);
  const table = document.createElement("table");
  const headers = Array.isArray(component.headers) ? component.headers : [];
  if (headers.length) {
    const head = document.createElement("thead");
    const row = document.createElement("tr");
    headers.forEach((header) => {
      const cell = document.createElement("th");
      cell.textContent = text(header);
      row.append(cell);
    });
    head.append(row);
    table.append(head);
  }
  const body = document.createElement("tbody");
  (Array.isArray(component.rows) ? component.rows : []).forEach((values) => {
    const row = document.createElement("tr");
    (Array.isArray(values) ? values : []).forEach((value) => {
      const cell = document.createElement("td");
      cell.textContent = text(value);
      row.append(cell);
    });
    body.append(row);
  });
  table.append(body);
  frame.append(table);
  return frame;
}

function renderStatus(component, colors) {
  const frame = componentFrame("status", component, colors);
  const dot = document.createElement("span");
  dot.className = "display-status-dot";
  const content = document.createElement("div");
  content.className = "display-status-content";
  if (component.label) addLabel(content, component.label);
  const value = document.createElement("div");
  value.className = "display-status-value";
  value.textContent = text(component.value);
  content.append(value);
  frame.append(dot, content);
  return frame;
}

function renderProgress(component, colors) {
  const frame = componentFrame("progress", component, colors);
  addLabel(frame, component.label);
  const value = Number(component.value) || 0;
  const max = Number(component.max) || 100;
  const percent = Math.max(0, Math.min(100, (value / max) * 100));
  const track = document.createElement("div");
  track.className = "display-progress-track";
  const fill = document.createElement("div");
  fill.className = "display-progress-fill";
  fill.style.width = `${percent}%`;
  track.append(fill);
  const caption = document.createElement("div");
  caption.className = "display-progress-caption";
  caption.textContent = `${value}${component.max === undefined ? "%" : ` / ${max}`}`;
  frame.append(track, caption);
  return frame;
}

function renderButton(component, colors, onIntent) {
  const frame = componentFrame("button", component, colors);
  const button = document.createElement("button");
  button.className = "display-action-button";
  button.type = "button";
  button.textContent = text(component.label || "Continue");
  button.addEventListener("click", () => onIntent(component.intent || component.label || "Continue"));
  frame.append(button);
  return frame;
}

function renderDivider(component, colors) {
  const frame = componentFrame("divider", component, colors);
  frame.style.flexBasis = "100%";
  frame.append(document.createElement("hr"));
  return frame;
}

const RENDERERS = {
  number: renderNumber,
  text: renderText,
  table: renderTable,
  status: renderStatus,
  progress: renderProgress,
  button: renderButton,
  divider: renderDivider,
};

export function renderDisplay(display, options) {
  const root = document.createElement("div");
  root.className = "component-display";
  const rows = Array.isArray(display?.rows) ? display.rows : [];
  rows.forEach((row) => {
    const rowEl = document.createElement("div");
    rowEl.className = "display-row";
    (Array.isArray(row?.components) ? row.components : []).forEach((component) => {
      const renderer = RENDERERS[component?.type];
      if (renderer) rowEl.append(renderer(component, options.colors, options.onIntent));
    });
    if (rowEl.childElementCount) root.append(rowEl);
  });
  return root;
}
