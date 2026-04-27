// Runs on LinkedIn people search results pages.
// Adds a floating button that exports all visible profile cards to profiles.json.

function scrapeProfiles() {
  const profiles = [];

  // LinkedIn uses several different card containers depending on search type
  const cards = document.querySelectorAll([
    "li.reusable-search__result-container",
    "div.entity-result",
    "li[data-occludable-job-id]",
  ].join(", "));

  cards.forEach((card) => {
    // Name — LinkedIn wraps it in a span[aria-hidden] inside the anchor
    const nameEl =
      card.querySelector(".entity-result__title-text a span[aria-hidden]") ||
      card.querySelector(".entity-result__title-text a") ||
      card.querySelector("span.entity-result__title-line a span[aria-hidden]");
    const name = nameEl ? nameEl.textContent.trim() : "";

    // Profile URL — strip query params so the link stays clean
    const urlEl =
      card.querySelector(".entity-result__title-text a") ||
      card.querySelector("a.app-aware-link[href*='/in/']");
    const linkedin_url = urlEl ? urlEl.href.split("?")[0] : "";

    // Headline (primary subtitle)
    const headlineEl =
      card.querySelector(".entity-result__primary-subtitle") ||
      card.querySelector(".entity-result__summary");
    const headline = headlineEl ? headlineEl.textContent.trim() : "";

    // Skip ghost "LinkedIn Member" placeholders and cards with no name
    if (!name || name === "LinkedIn Member") return;

    profiles.push({ name, headline, about: "", linkedin_url });
  });

  return profiles;
}

function downloadJSON(profiles) {
  const blob = new Blob([JSON.stringify(profiles, null, 2)], {
    type: "application/json",
  });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = "profiles.json";
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  URL.revokeObjectURL(url);
}

function addButton() {
  if (document.getElementById("linkswipe-export-btn")) return;

  const btn = document.createElement("button");
  btn.id = "linkswipe-export-btn";
  btn.textContent = "⬇ Export to LinkSwipe";
  btn.style.cssText = `
    position: fixed;
    bottom: 24px;
    right: 24px;
    z-index: 99999;
    background: #0a66c2;
    color: white;
    border: none;
    border-radius: 24px;
    padding: 12px 22px;
    font-size: 14px;
    font-weight: 600;
    cursor: pointer;
    box-shadow: 0 4px 16px rgba(0,0,0,0.25);
    font-family: -apple-system, BlinkMacSystemFont, sans-serif;
  `;

  btn.addEventListener("click", () => {
    const profiles = scrapeProfiles();
    if (profiles.length === 0) {
      alert(
        "No profiles found on this page.\nMake sure you are on a LinkedIn People search results page with results visible."
      );
      return;
    }
    downloadJSON(profiles);
    btn.textContent = `✓ Exported ${profiles.length} profiles`;
    setTimeout(() => {
      btn.textContent = "⬇ Export to LinkSwipe";
    }, 3000);
  });

  document.body.appendChild(btn);
}

// LinkedIn is a SPA — re-inject the button after navigation
addButton();
const observer = new MutationObserver(() => addButton());
observer.observe(document.body, { childList: true, subtree: false });
