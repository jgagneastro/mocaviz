(function () {
  const TEAM_USERS = new Set(["collaborators", "management"]);

  function readRole() {
    const params = new URLSearchParams(window.location.search);
    const user = (params.get("user") || params.get("username") || "")
      .trim()
      .toLowerCase();
    return TEAM_USERS.has(user) ? user : "";
  }

  function applyTheme() {
    const role = readRole();
    if (!role) return;

    const targets = [document.documentElement, document.body].filter(Boolean);
    targets.forEach((target) => {
      target.classList.add("is-mocadb-team", "is-authenticated");
      target.classList.add(role === "management" ? "is-management" : "is-collaborator");
      target.dataset.mocavizUserRole = role;
    });
  }

  applyTheme();
  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", applyTheme, { once: true });
  }
})();
