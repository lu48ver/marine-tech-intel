// Marine Tech Intel — tab switching + topic expand/collapse (vanilla JS, no deps)

(function () {
  "use strict";

  // ---------- Tab switching ----------
  const tabs = document.querySelectorAll(".tab");
  const panels = {
    brief: document.getElementById("panel-brief"),
    radar: document.getElementById("panel-radar"),
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

  // ---------- Client-side search ----------
  const searchInput = document.getElementById("search-input");
  const searchPanel = document.getElementById("panel-search");
  const resultsList = document.getElementById("search-results");
  const emptyMsg = document.getElementById("search-empty");
  const countEl = document.getElementById("search-count");

  let searchIndex = null; // lazy-loaded once on first keystroke

  function escapeHtml(s) {
    return s.replace(/[&<>"']/g, (c) =>
      ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c])
    );
  }

  function renderResults(items) {
    resultsList.innerHTML = items
      .map(
        (it) => `
        <li class="brief-item">
          <div class="brief-date">${escapeHtml(it.date || "")}</div>
          <div class="brief-body">
            <a class="brief-link" href="${encodeURI(it.url)}" target="_blank" rel="noopener">${escapeHtml(it.title)}</a>
            ${it.summary ? `<p class="brief-summary">${escapeHtml(it.summary)}</p>` : ""}
            <div class="brief-meta">
              <span class="src-chip">${escapeHtml(it.source)}</span>
              ${(it.topics || []).map((t) => `<span class="topic-chip">${escapeHtml(t)}</span>`).join("")}
            </div>
          </div>
        </li>`
      )
      .join("");
  }

  function runSearch(query) {
    const q = query.trim().toLowerCase();
    if (!q) {
      // Empty query: leave search mode, restore the active tab
      searchPanel.hidden = true;
      countEl.textContent = "";
      const active = document.querySelector(".tab.is-active");
      activateTab(active ? active.dataset.tab : "brief");
      return;
    }
    // Hide the normal tab panels while showing search results
    Object.values(panels).forEach((p) => p && p.classList.remove("is-active"));
    searchPanel.hidden = false;

    const terms = q.split(/\s+/);
    const matches = (searchIndex || []).filter((it) => {
      const hay = (
        it.title + " " + it.summary + " " + it.source + " " +
        (it.tags || []).join(" ") + " " + (it.topics || []).join(" ")
      ).toLowerCase();
      return terms.every((t) => hay.includes(t)); // all terms must match (AND)
    });

    renderResults(matches);
    emptyMsg.hidden = matches.length > 0;
    countEl.textContent = `${matches.length} 筆`;
  }

  if (searchInput) {
    searchInput.addEventListener("input", async () => {
      if (searchIndex === null) {
        try {
          searchIndex = await fetch("search.json").then((r) => r.json());
        } catch (e) {
          searchIndex = [];
        }
      }
      runSearch(searchInput.value);
    });
    // Esc clears the search and returns to tabs
    searchInput.addEventListener("keydown", (e) => {
      if (e.key === "Escape") {
        searchInput.value = "";
        runSearch("");
      }
    });
  }
})();
