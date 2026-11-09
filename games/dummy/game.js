// Minimal game exercising the full host-game contract: used to prove the
// bridge, manifest validator, and test host work end to end (Phase G0).
const statusEl = document.getElementById("status");
const winBtn = document.getElementById("win");
const loseBtn = document.getElementById("lose");

let started = false;
let paused = false;
let gameOverSent = false;

function sendGameOver(score) {
  if (gameOverSent) return; // gameover must fire exactly once per run
  gameOverSent = true;
  AlphaGo.gameOver(score, { meta: { dummy: true } });
  statusEl.textContent = `game over, score ${score}`;
  winBtn.disabled = true;
  loseBtn.disabled = true;
}

window.addEventListener("alphago:start", () => {
  started = true;
  gameOverSent = false;
  statusEl.textContent = "started, pick an outcome";
  winBtn.disabled = false;
  loseBtn.disabled = false;
});

window.addEventListener("alphago:pause", () => {
  paused = true;
  statusEl.textContent = "paused";
});

window.addEventListener("alphago:resume", () => {
  paused = false;
  statusEl.textContent = started ? "started, pick an outcome" : "waiting for start";
});

winBtn.addEventListener("click", () => sendGameOver(100));
loseBtn.addEventListener("click", () => sendGameOver(0));

statusEl.textContent = "waiting for start";
AlphaGo.ready();
