window.STRINGS = {
  en: {
    title: "2048",
    intro: "Join the numbers and get to the 2048 tile!",
    newGame: "New Game",
    howToPlayLabel: "How to play:",
    howToPlayBody: "Use your arrow keys or swipe to move the tiles. When two tiles with the same number touch, they merge into one!",
    gameOver: "Game over!",
    youWin: "You win!",
    keepGoing: "Keep going",
    tryAgain: "Try again",
    waiting: "Waiting for the game to start…",
    credits: "Credits",
  },
};

// t(key): looks up the current AlphaGo.lang (set from the host's `start`
// message) each call, since lang isn't known yet at script-load time.
window.t = function (key) {
  var lang = (window.AlphaGo && window.AlphaGo.lang) || "en";
  return window.AlphaGoI18n(window.STRINGS, lang)(key);
};

function applyStrings() {
  document.querySelectorAll("[data-i18n]").forEach(function (el) {
    el.textContent = t(el.getAttribute("data-i18n"));
  });
}

document.addEventListener("DOMContentLoaded", applyStrings);
window.addEventListener("alphago:start", applyStrings); // re-apply if lang changed
