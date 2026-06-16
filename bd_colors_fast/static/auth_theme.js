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
  const authScriptUrl = document.currentScript?.src || "";
  const authBaseUrl = authScriptUrl ? new URL("../", authScriptUrl).toString() : new URL("./", window.location.href).toString();
  const authContext = {
    role: readUrlRole(),
    hasCredentials: false,
    private_db: readUrlPrivateDb(),
    source: "url",
  };

  function authAppUrl(path) {
    return new URL(String(path || "").replace(/^\/+/, ""), authBaseUrl).toString();
  }

  function readUrlRole() {
    const params = new URLSearchParams(window.location.search);
    const user = (params.get("user") || params.get("username") || "")
      .trim()
      .toLowerCase();
    const dbName = String(params.get("dbase") || params.get("db") || params.get("database") || "")
      .trim()
      .toLowerCase();
    return TEAM_USERS.has(user) && dbName === "mocadb_private_tables" ? user : "";
  }

  function readUrlPrivateDb() {
    const params = new URLSearchParams(window.location.search);
    const dbName = String(params.get("dbase") || params.get("db") || params.get("database") || "")
      .replace(/`/g, "")
      .trim()
      .toLowerCase();
    return dbName === "mocadb_private_tables";
  }

  function readRole() {
    return authContext.role || readUrlRole();
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
    const targets = [document.documentElement, document.body].filter(Boolean);
    targets.forEach((target) => {
      target.classList.remove("is-mocadb-team", "is-authenticated", "is-management", "is-collaborator");
      delete target.dataset.mocavizUserRole;
      delete target.dataset.mocavizAuthSource;
      if (!role) return;
      target.classList.add("is-mocadb-team", "is-authenticated");
      target.classList.add(role === "management" ? "is-management" : "is-collaborator");
      target.dataset.mocavizUserRole = role;
      target.dataset.mocavizAuthSource = authContext.source || "url";
    });
  }

  async function loadAuthContext() {
    const urlParams = new URLSearchParams(window.location.search);
    const endpoint = authAppUrl(`api/auth/context${urlParams.toString() ? `?${urlParams.toString()}` : ""}`);
    const response = await fetch(endpoint);
    const payload = await response.json();
    if (!payload?.ok) return authContext;
    const role = String(payload.role || "").trim().toLowerCase();
    authContext.role = TEAM_USERS.has(role) ? role : "";
    authContext.hasCredentials = Boolean(payload.has_credentials);
    authContext.private_db = Boolean(payload.private_db);
    authContext.source = payload.source || "server";
    applyTheme();
    window.dispatchEvent(new CustomEvent("mocaviz-auth-context", { detail: { ...authContext } }));
    return authContext;
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
  window.MocaAuthContext = {
    ready: loadAuthContext().catch(() => authContext),
    current: authContext,
  };
  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", applyPageEnhancements, { once: true });
  } else {
    addDatavizHomeLink();
  }
})();
