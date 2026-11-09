/* ============================================================
   manpage.js — Unix-manpage-style How-to-Play overlay.

   Usage (per-game):

     <link rel="stylesheet" href="../manpage.css">
     <script defer src="../manpage.js"></script>

     <button class="btn ghost tool-btn man-trigger"
             data-man="queens"
             data-man-title="QUEENS(1)">
       <span class="q">?</span> man
     </button>

     <template id="man-queens">
       <h2>Name</h2>
       <p>queens — place monarchs on a colored board.</p>
       <h2>Rules</h2>
       <ul><li>One queen per row, column, and region.</li></ul>
       ...
     </template>

   The overlay auto-wires click-handlers on all `.man-trigger[data-man]`
   elements.

   AlphaGo note: upstream also had `Manpage.autoOpen(id)`, which popped the
   overlay once per game using localStorage. Removed — the AlphaGo game
   contract forbids real persistence (plan section 6.3), and an unprompted
   modal on load is a poor fit for an embedded game anyway. The "? man"
   on-demand button (openFromTrigger) is unaffected.
   ============================================================ */
(function (global) {
  "use strict";

  let currentBackdrop = null;
  let lastFocus = null;

  function $(sel, root) { return (root || document).querySelector(sel); }

  function close() {
    if (!currentBackdrop) return;
    const node = currentBackdrop;
    currentBackdrop = null;
    node.classList.add("closing");
    node.style.opacity = "0";
    setTimeout(() => node.remove(), 150);
    document.removeEventListener("keydown", onKey, true);
    if (lastFocus && typeof lastFocus.focus === "function") {
      try { lastFocus.focus(); } catch (e) {}
    }
  }

  function onKey(e) {
    if (!currentBackdrop) return;
    if (e.key === "Escape" || e.key === "q" || e.key === "Q") {
      e.preventDefault();
      close();
    }
  }

  function open(opts) {
    if (currentBackdrop) close();
    opts = opts || {};
    const title   = opts.title   || "HELP(1)";
    const content = opts.content;   // HTMLElement | DocumentFragment | string
    const hint    = opts.hint !== undefined
                    ? opts.hint
                    : "ESC · q · click outside to close";

    lastFocus = document.activeElement;

    const backdrop = document.createElement("div");
    backdrop.className = "man-backdrop";
    backdrop.setAttribute("role", "dialog");
    backdrop.setAttribute("aria-modal", "true");
    backdrop.setAttribute("aria-label", title);

    const win = document.createElement("div");
    win.className = "man-window";

    const bar = document.createElement("div");
    bar.className = "man-titlebar";
    bar.innerHTML =
      '<span>MAN <span class="man-id">' + escapeHtml(title) + '</span></span>' +
      (hint ? '<span class="man-hint">' + escapeHtml(hint) + "</span>" : "") +
      '<button class="man-close" type="button" aria-label="Close">×</button>';

    const body = document.createElement("div");
    body.className = "man-body";
    if (typeof content === "string") {
      body.innerHTML = content;
    } else if (content instanceof HTMLTemplateElement) {
      body.appendChild(content.content.cloneNode(true));
    } else if (content instanceof Node) {
      body.appendChild(content);
    }

    const footer = document.createElement("div");
    footer.className = "man-footer";
    footer.textContent = "GAMES · " + title.toLowerCase();

    win.appendChild(bar);
    win.appendChild(body);
    win.appendChild(footer);
    backdrop.appendChild(win);

    backdrop.addEventListener("click", (e) => {
      if (e.target === backdrop) close();
    });
    bar.querySelector(".man-close").addEventListener("click", close);

    document.body.appendChild(backdrop);
    currentBackdrop = backdrop;
    document.addEventListener("keydown", onKey, true);

    // Focus the close button for keyboard users
    setTimeout(() => {
      const btn = bar.querySelector(".man-close");
      if (btn) try { btn.focus(); } catch (e) {}
    }, 0);

    return backdrop;
  }

  function openFromTrigger(trigger) {
    const id      = trigger.getAttribute("data-man");
    const title   = trigger.getAttribute("data-man-title")
                   || ((id || "help") + "(1)").toUpperCase();
    const tplId   = trigger.getAttribute("data-man-template")
                   || ("man-" + id);
    const tpl     = document.getElementById(tplId);
    if (!tpl) {
      console.warn("[manpage] template not found:", tplId);
      return;
    }
    open({ title: title, content: tpl });
  }

  function escapeHtml(s) {
    return String(s)
      .replace(/&/g, "&amp;").replace(/</g, "&lt;")
      .replace(/>/g, "&gt;").replace(/"/g, "&quot;");
  }
  function wire() {
    document.addEventListener("click", (e) => {
      const t = e.target.closest && e.target.closest(".man-trigger[data-man]");
      if (!t) return;
      e.preventDefault();
      openFromTrigger(t);
    });
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", wire);
  } else {
    wire();
  }

  global.Manpage = {
    open: open,
    close: close,
  };
})(window);
