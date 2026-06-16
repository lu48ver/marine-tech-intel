// Marine Tech Intel — tab switching + topic expand/collapse (vanilla JS, no deps)

(function () {
  "use strict";

  // ---------- Tab switching ----------
  const tabs = document.querySelectorAll(".tab");
  const panels = {
    brief: document.getElementById("panel-brief"),
    sources: document.getElementById("panel-sources"),
    topics: document.getElementById("panel-topics"),
  };

  function activateTab(name) {
    tabs.forEach((t) => t.classList.toggle("is-active", t.dataset.tab === name));
    Object.entries(panels).forEach(([key, panel]) => {
      if (panel) panel.classList.toggle("is-active", key === name);
    });
    // Reflect the active tab in the URL hash so it survives reloads/sharing
    if (history.replaceState) history.replaceState(null, "", "#" + name);
  }

  tabs.forEach((tab) => {
    tab.addEventListener("click", () => activateTab(tab.dataset.tab));
  });

  // Restore tab from URL hash on load (e.g. #topics)
  const initial = (location.hash || "").replace("#", "");
  if (panels[initial]) activateTab(initial);

  // ---------- Topic expand / collapse ----------
  document.querySelectorAll(".topic-toggle").forEach((btn) => {
    btn.addEventListener("click", () => {
      const expanded = btn.getAttribute("aria-expanded") === "true";
      btn.setAttribute("aria-expanded", String(!expanded));
      const body = btn.nextElementSibling;
      if (body) body.hidden = expanded;
    });
  });
})();
