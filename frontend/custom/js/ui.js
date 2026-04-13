export function qs(id){ return document.getElementById(id); }

export function escapeHtml(value){
  return String(value || "").replaceAll("&","&amp;").replaceAll("<","&lt;").replaceAll(">","&gt;");
}

export function messageBlock(entry){
  if (!entry) return "";
  return `<div class="message ${entry.kind}">${escapeHtml(entry.text)}</div>`;
}

export function helpTip(text){
  const safe = escapeHtml(text);
  return `
    <span class="help-tip" tabindex="0" role="button" aria-label="${safe}" title="${safe}">
      ?
      <span class="tooltip">${safe}</span>
    </span>
  `;
}

export function labelWithHelp(label, text){
  return `<span class="label-with-help"><span>${escapeHtml(label)}</span>${helpTip(text)}</span>`;
}

export function optionRows(items, selected, label){
  return items.map((item) => {
    const active = item.name === selected ? "active" : "";
    return `
      <button class="item card ${active}" data-name="${escapeHtml(item.name)}">
        <h3>${escapeHtml(item.name)}</h3>
        <div class="meta">${label(item).map((row) => `<span>${escapeHtml(row)}</span>`).join("")}</div>
      </button>
    `;
  }).join("");
}

export function bindTabs(state){
  const tabs = document.getElementById("tabs");
  tabs.addEventListener("click", (event) => {
    const button = event.target.closest("button[data-tab]");
    if (!button) return;
    state.activeTab = button.dataset.tab;
    [...tabs.querySelectorAll("button")].forEach((node) => node.classList.toggle("active", node === button));
    [...document.querySelectorAll(".tab")].forEach((node) => node.classList.toggle("active", node.id === `tab-${state.activeTab}`));
  });
}
