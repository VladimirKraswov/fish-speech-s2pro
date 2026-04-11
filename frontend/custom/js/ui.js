export function qs(id){ return document.getElementById(id); }

export function escapeHtml(value){
  return String(value || "").replaceAll("&","&amp;").replaceAll("<","&lt;").replaceAll(">","&gt;");
}

export function messageBlock(entry){
  if (!entry) return "";
  return `<div class="message ${entry.kind}">${escapeHtml(entry.text)}</div>`;
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
