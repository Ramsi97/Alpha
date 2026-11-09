(function () {
  // In production this is injected at build/deploy time to the real host origin
  // (e.g. "https://app.yourdomain.com"). "*" is only safe for local dev/testing.
  const HOST_ORIGIN = window.__ALPHAGO_HOST_ORIGIN__ || "*";

  const send = (msg) =>
    parent.postMessage({ source: "alphago-game", ...msg }, HOST_ORIGIN);

  window.addEventListener("message", (e) => {
    if (HOST_ORIGIN !== "*" && e.origin !== HOST_ORIGIN) return;
    if (e.source !== parent) return;
    const d = e.data || {};
    if (d.source !== "alphago-host") return;
    if (d.type === "theme" && d.params) applyThemeParams(d.params);
    if (d.type === "start") {
      if (d.theme) applyThemeParams(d.theme);
      if (d.lang) window.AlphaGo.lang = d.lang;
    }
    window.dispatchEvent(new CustomEvent("alphago:" + d.type, { detail: d }));
  });

  // Mirrors Telegram's themeParams onto the same --tg-theme-* custom properties
  // theme.css reads, so games get live theme updates without any code of their own.
  function applyThemeParams(params) {
    const root = document.documentElement.style;
    for (const [key, value] of Object.entries(params)) {
      const cssName = "--tg-theme-" + key.replace(/_/g, "-");
      root.setProperty(cssName, value);
    }
  }

  window.AlphaGo = {
    lang: "en",
    ready: () => send({ type: "ready" }),
    score: (value) => send({ type: "score", value }),
    gameOver: (score, opts) => send({ type: "gameover", score, ...(opts || {}) }),
    error: (message) => send({ type: "error", message }),
  };
})();
