(function () {
  const DATAVIZ_HOME_URL = "https://dataviz.mocadb.ca/js/";
  const CONNECTION_PARAM_KEYS = [
    "host",
    "port",
    "user",
    "username",
    "pwd",
    "password",
    "dbase",
    "db",
    "database",
    "mock",
  ];
  const TEAM_USERS = new Set(["collaborators", "management"]);

  function readRole() {
    const params = new URLSearchParams(window.location.search);
    const user = (params.get("user") || params.get("username") || "")
      .trim()
      .toLowerCase();
    return TEAM_USERS.has(user) ? user : "";
  }

  function datavizHomeUrl() {
    const url = new URL(DATAVIZ_HOME_URL);
    const params = new URLSearchParams(window.location.search);
    CONNECTION_PARAM_KEYS.forEach((key) => {
      params.getAll(key).forEach((value) => {
        url.searchParams.append(key, value);
      });
    });
    return url.toString();
  }

  function isDatavizHomePage() {
    const pathname = window.location.pathname.replace(/\/+$/, "");
    return pathname === "" || pathname === "/js";
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

  function addDatavizHomeLink() {
    const existing = document.querySelector("[data-dataviz-home-link]");
    if (existing) {
      existing.href = datavizHomeUrl();
      return;
    }
    if (isDatavizHomePage()) return;

    const topbar = document.querySelector(".topbar");
    if (!topbar) return;

    const link = document.createElement("a");
    link.className = "dataviz-home-link";
    link.dataset.datavizHomeLink = "true";
    link.href = datavizHomeUrl();
    link.textContent = "Return to dataviz home";

    const brand = topbar.querySelector(".brand");
    if (!brand) {
      topbar.prepend(link);
      return;
    }

    const titleGroup = document.createElement("div");
    titleGroup.className = "topbar-title-group";
    brand.replaceWith(titleGroup);
    titleGroup.append(brand, link);
  }

  function applyPageEnhancements() {
    applyTheme();
    addDatavizHomeLink();
  }

  applyTheme();
  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", applyPageEnhancements, { once: true });
  } else {
    addDatavizHomeLink();
  }
})();
