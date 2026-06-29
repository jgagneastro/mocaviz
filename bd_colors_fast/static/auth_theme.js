(function () {
  const DATAVIZ_HOME_URL = "https://dataviz.mocadb.ca/js/";
  const BUG_REPORT_URL = "https://github.com/mocadb/mocadb-project/issues";
  const BD_PHOTOMETRY_DISCUSSION_URL = "https://github.com/orgs/mocadb/discussions/43";
  const BD_EVOLUTION_DISCUSSION_URL = "https://github.com/orgs/mocadb/discussions/44";
  const GAIA_CMD_DISCUSSION_URL = "https://github.com/orgs/mocadb/discussions/50";
  const BD_PHOTOMETRY_PATHS = new Set([
    "bd-colors",
    "bd_colors",
    "bd-colors-fast",
    "bd_colors_fast",
    "index.html",
  ]);
  const BD_EVOLUTION_PATHS = new Set([
    "brown-dwarf-evolution",
    "brown_dwarf_evolution",
    "bd-evolution",
    "bd_evolution",
    "bd_evolution.html",
  ]);
  const GAIA_CMD_PATHS = new Set([
    "gaia-cmd",
    "gaia_cmd",
    "stellar-gaia-cmd",
    "stellar_gaia_cmd",
    "gaia_cmd.html",
  ]);
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

  function isBdPhotometryExplorerPage() {
    const pathname = window.location.pathname.replace(/\/+$/, "");
    const pageName = pathname.split("/").pop() || "";
    if (BD_PHOTOMETRY_PATHS.has(pageName)) return true;
    return document.title.trim() === "MOCAdb Brown Dwarf Photometry Explorer";
  }

  function isBdEvolutionExplorerPage() {
    const pathname = window.location.pathname.replace(/\/+$/, "");
    const pageName = pathname.split("/").pop() || "";
    if (BD_EVOLUTION_PATHS.has(pageName)) return true;
    return document.title.trim() === "Brown Dwarf Evolution Explorer";
  }

  function isGaiaCmdExplorerPage() {
    const pathname = window.location.pathname.replace(/\/+$/, "");
    const pageName = pathname.split("/").pop() || "";
    if (GAIA_CMD_PATHS.has(pageName)) return true;
    return document.title.trim() === "MOCAdb Fast Gaia CMD";
  }

  function pageDiscussionUrl() {
    if (isBdPhotometryExplorerPage()) return BD_PHOTOMETRY_DISCUSSION_URL;
    if (isBdEvolutionExplorerPage()) return BD_EVOLUTION_DISCUSSION_URL;
    if (isGaiaCmdExplorerPage()) return GAIA_CMD_DISCUSSION_URL;
    return "";
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

  function topbarTitleGroup(topbar) {
    const existing = topbar.querySelector(".topbar-title-group");
    if (existing) return existing;

    const brand = topbar.querySelector(".brand");
    const titleGroup = document.createElement("div");
    titleGroup.className = "topbar-title-group";

    if (!brand) {
      topbar.prepend(titleGroup);
      return titleGroup;
    }

    brand.replaceWith(titleGroup);
    titleGroup.append(brand);
    return titleGroup;
  }

  function topbarLinkRow(titleGroup) {
    const existing = titleGroup.querySelector(".topbar-link-row");
    if (existing) return existing;

    const row = document.createElement("div");
    row.className = "topbar-link-row";
    titleGroup.append(row);
    return row;
  }

  function upsertTopbarLink(row, selector, options) {
    const link = row.querySelector(selector) || document.querySelector(selector) || document.createElement("a");
    link.className = options.className || "dataviz-topbar-link";
    link.dataset[options.datasetKey] = "true";
    link.href = options.href;
    link.textContent = options.text;
    if (options.external) {
      link.target = "_blank";
      link.rel = "noopener noreferrer";
    } else {
      link.removeAttribute("target");
      link.removeAttribute("rel");
    }
    row.append(link);
    return link;
  }

  function addDatavizTopbarLinks() {
    if (isDatavizHomePage()) return;

    const topbar = document.querySelector(".topbar");
    if (!topbar) return;

    const titleGroup = topbarTitleGroup(topbar);
    const row = topbarLinkRow(titleGroup);

    upsertTopbarLink(row, "[data-dataviz-home-link]", {
      className: "dataviz-topbar-link dataviz-home-link",
      datasetKey: "datavizHomeLink",
      href: datavizHomeUrl(),
      text: "Return to dataviz home",
    });
    upsertTopbarLink(row, "[data-dataviz-bug-report-link]", {
      datasetKey: "datavizBugReportLink",
      external: true,
      href: BUG_REPORT_URL,
      text: "Report a bug or feature request",
    });

    const discussionLink = row.querySelector("[data-dataviz-page-discussion-link]") || document.querySelector("[data-dataviz-page-discussion-link]");
    const discussionUrl = pageDiscussionUrl();
    if (discussionUrl) {
      upsertTopbarLink(row, "[data-dataviz-page-discussion-link]", {
        datasetKey: "datavizPageDiscussionLink",
        external: true,
        href: discussionUrl,
        text: "Open MOCAdb Discussions about this dataviz page",
      });
    } else if (discussionLink) {
      discussionLink.remove();
    }
  }

  function applyPageEnhancements() {
    applyTheme();
    addDatavizTopbarLinks();
  }

  applyTheme();
  window.MocaAuthContext = {
    ready: loadAuthContext().catch(() => authContext),
    current: authContext,
  };
  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", applyPageEnhancements, { once: true });
  } else {
    addDatavizTopbarLinks();
  }
})();
