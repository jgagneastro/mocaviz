"use strict";

// Named snapshots of the queue and fit controls for this browser and tool.
window.installReviewPresets = function (key, ids, {canLoad, apply, initial = {}, newestFirst = false}) {
  const panel = document.getElementById("review-presets");
  const name = panel.querySelector("[data-name]");
  const select = panel.querySelector("[data-presets]");
  const save = panel.querySelector("[data-save]");
  const load = panel.querySelector("[data-load]");
  const remove = panel.querySelector("[data-delete]");
  const status = panel.querySelector("[role=status]");
  const fields = ids.map(id => document.getElementById(id));
  let current = "";
  let presets = new Map();
  let storageAvailable = true;
  try {
    const stored = JSON.parse(localStorage.getItem(key) || "[]");
    if (Array.isArray(stored)) {
      presets = new Map(stored.filter(entry => Array.isArray(entry) && entry.length === 2 &&
        typeof entry[0] === "string" && entry[1] && typeof entry[1] === "object"));
    }
  } catch {
    storageAvailable = false;
  }

  // Seed shipped datasets once. Keep any presets the user already has and
  // respect later edits or deletions.
  const seedKey = key + ":initial-v1";
  if (Object.keys(initial).length) {
    const additions = Object.entries(initial).filter(([label]) => !presets.has(label));
    try {
      if (!storageAvailable || !localStorage.getItem(seedKey)) {
        for (const [label, filters] of additions) presets.set(label, filters);
        if (storageAvailable) {
          localStorage.setItem(key, JSON.stringify([...presets]));
          localStorage.setItem(seedKey, "1");
        }
      }
    } catch {
      for (const [label, filters] of additions) presets.set(label, filters);
    }
  }

  const updateButtons = () => {
    save.disabled = !storageAvailable;
    load.disabled = !select.value || !canLoad();
    remove.disabled = !storageAvailable || !current || select.value !== current;
  };
  const render = () => {
    // Presets are appended when saved and stored in insertion order.
    const labels = [...presets.keys()];
    if (newestFirst) labels.reverse();
    else labels.sort((left, right) => left.localeCompare(right));
    select.replaceChildren(new Option("Saved datasets", ""), ...labels.map(label => new Option(label, label)));
    select.value = newestFirst ? (labels[0] ?? "") : current;
    updateButtons();
  };
  const write = next => {
    try {
      localStorage.setItem(key, JSON.stringify([...next]));
      presets = next;
      return true;
    } catch {
      status.textContent = "Could not save to this browser.";
      return false;
    }
  };
  name.addEventListener("input", () => { status.textContent = ""; });
  panel.querySelector("form").addEventListener("submit", event => {
    event.preventDefault();
    const label = name.value.trim();
    if (!label) { name.focus(); return; }
    if (presets.has(label)) {
      status.textContent = "A dataset with that name already exists.";
      return;
    }
    const next = new Map(presets);
    next.set(label, Object.fromEntries(fields.map(field => [
      field.id, field.type === "checkbox" ? field.checked : field.value
    ])));
    if (!write(next)) return;
    current = label;
    name.value = "";
    render();
    status.textContent = "Saved " + label + ".";
  });
  select.addEventListener("change", () => { status.textContent = ""; updateButtons(); });
  load.addEventListener("click", () => {
    if (!canLoad()) return;
    const label = select.value;
    const preset = presets.get(label);
    if (!preset) return;
    for (const field of fields) {
      const value = preset[field.id];
      if (field.type === "checkbox" && typeof value === "boolean") field.checked = value;
      else if (typeof value === "string" && (field.tagName !== "SELECT" ||
          [...field.options].some(option => option.value === value))) field.value = value;
    }
    current = label;
    status.textContent = "Restored filters for " + label + ".";
    updateButtons();
    apply(label, preset);
  });
  remove.addEventListener("click", () => {
    if (select.value !== current || !current) return;
    const next = new Map(presets);
    next.delete(current);
    if (!write(next)) return;
    status.textContent = "Deleted " + current + ".";
    current = "";
    render();
  });
  panel.hidden = false;
  render();
  if (!storageAvailable) status.textContent = "Saved datasets are unavailable in this browser.";
  return updateButtons;
};
