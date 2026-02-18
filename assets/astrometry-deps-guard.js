// Guard against multi-worker Dash dependency mismatches on /astrometry.
// If the astrometry callback is missing from /_dash-dependencies, reload a few times.
(function () {
  try {
    if (!window || !window.location) return;
    var path = window.location.pathname || "";
    if (path.indexOf("/astrometry") === -1) return;

    var key = "mocaviz_astrometry_deps_attempts";
    var attempts = 0;
    try {
      attempts = parseInt(window.localStorage.getItem(key) || "0", 10) || 0;
    } catch (e) {
      attempts = 0;
    }

    if (attempts >= 5) return;

    var url = "/_dash-dependencies?_ts=" + Date.now();
    fetch(url, { cache: "no-store" })
      .then(function (r) { return r.json(); })
      .then(function (deps) {
        var hasAstrometry = false;
        if (deps && Array.isArray(deps)) {
          for (var i = 0; i < deps.length; i++) {
            var out = deps[i] && deps[i].output;
            if (out && out.indexOf("astrometry-plot-ra.figure") !== -1) {
              hasAstrometry = true;
              break;
            }
          }
        }
        if (!hasAstrometry) {
          try {
            window.localStorage.setItem(key, String(attempts + 1));
          } catch (e) {}
          // Small delay to avoid tight reload loops
          setTimeout(function () { window.location.reload(); }, 300);
        } else {
          try {
            window.localStorage.removeItem(key);
          } catch (e) {}
        }
      })
      .catch(function () {
        // If we can't fetch deps, don't loop infinitely.
      });
  } catch (e) {
    // no-op
  }
})();
