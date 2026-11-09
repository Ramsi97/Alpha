const DIFFS = { easy:[9,9,10], medium:[16,16,40], hard:[20,20,80] };
const SCORE = { easy:{base:300,target:120}, medium:{base:700,target:400}, hard:{base:1500,target:900} };
let W,H,M, cells, mines, revealed, flags, over, won, firstClick;
let timerStart = 0, timerId = null, elapsed = 0;
let waitingForStart = true, paused = false, pausedAt = 0, gameOverReported = false, currentDiff = 'medium';

function idx(r,c){ return r*W+c; }
function inb(r,c){ return r>=0&&c>=0&&r<H&&c<W; }
function neigh(r,c){ const a=[]; for(let dr=-1;dr<=1;dr++) for(let dc=-1;dc<=1;dc++) if((dr||dc)&&inb(r+dr,c+dc)) a.push([r+dr,c+dc]); return a; }

function stopTimer() { if (timerId) { clearInterval(timerId); timerId = null; } }
function startTimer() {
  stopTimer();
  timerStart = Date.now();
  elapsed = 0;
  document.getElementById('time').textContent = '0s';
  timerId = setInterval(() => {
    if (paused) return;
    elapsed = Math.floor((Date.now() - timerStart) / 1000);
    document.getElementById('time').textContent = elapsed + 's';
  }, 500);
}

function reset() {
  currentDiff = document.getElementById('diff').value;
  [H,W,M] = DIFFS[currentDiff];
  cells = new Int8Array(H*W);
  mines = new Uint8Array(H*W);
  revealed = new Uint8Array(H*W);
  flags = new Uint8Array(H*W);
  over = false; won = false; firstClick = true;
  gameOverReported = false;
  stopTimer();
  elapsed = 0;
  document.getElementById('time').textContent = '0s';
  document.getElementById('status').textContent = 'Click to reveal.';
  render();
  updateHud();
}

// AlphaGo: "New game" / difficulty change abandon the current run (nothing
// reported) and go back to waiting — the host decides when the next run
// starts, matching the restart contract (plan section 6.6).
function requestNewRun() {
  stopTimer();
  reset();
  waitingForStart = true;
  showWaiting();
}

function beginRun() {
  waitingForStart = false;
  paused = false;
  reset();
  hideWaiting();
}

function showWaiting() { document.querySelector('.alphago-waiting').classList.remove('hidden'); }
function hideWaiting() { document.querySelector('.alphago-waiting').classList.add('hidden'); }

// Report only on wins, per plan section 8 — a loss still ends the run
// (gameover with score 0) so the host can close the session.
function reportGameOver() {
  if (gameOverReported) return;
  gameOverReported = true;
  let score = 0;
  if (won) {
    const s = SCORE[currentDiff];
    score = Math.round(s.base * Math.max(0.2, 1 - elapsed / s.target));
  }
  AlphaGo.gameOver(score, { variant: currentDiff, meta: { won: won, seconds: elapsed } });
}

function placeMines(safeR, safeC) {
  const safe = new Set();
  safe.add(idx(safeR,safeC));
  neigh(safeR,safeC).forEach(([r,c])=>safe.add(idx(r,c)));
  let placed = 0;
  while (placed < M) {
    const i = Math.floor(Math.random()*H*W);
    if (mines[i] || safe.has(i)) continue;
    mines[i] = 1; placed++;
  }
  for (let r=0;r<H;r++) for (let c=0;c<W;c++) {
    if (mines[idx(r,c)]) { cells[idx(r,c)] = -1; continue; }
    let n=0; neigh(r,c).forEach(([nr,nc])=>{ if (mines[idx(nr,nc)]) n++; });
    cells[idx(r,c)] = n;
  }
}

function reveal(r,c) {
  const i = idx(r,c);
  if (revealed[i] || flags[i]) return;
  revealed[i] = 1;
  if (cells[i] === -1) { over = true; return; }
  if (cells[i] === 0) neigh(r,c).forEach(([nr,nc])=>reveal(nr,nc));
}

function checkWin() {
  let safeLeft = 0;
  for (let i=0;i<H*W;i++) if (!mines[i] && !revealed[i]) safeLeft++;
  if (safeLeft === 0) { won = true; over = true; }
}

function updateHud() {
  let flagged=0; for (let i=0;i<H*W;i++) if (flags[i]) flagged++;
  document.getElementById('mines').textContent = `${M - flagged} mines left`;
  if (over) document.getElementById('status').textContent = won ? 'You won! 🎉' : 'Boom. 💥';
}

function cellSize() {
  const vw = Math.min(document.documentElement.clientWidth * 0.94 - 16, 600);
  return Math.min(28, Math.floor(vw / Math.max(W, H)));
}

function render() {
  const el = document.getElementById('board');
  const sz = cellSize();
  el.style.gridTemplateColumns = `repeat(${W}, ${sz}px)`;
  el.style.gridTemplateRows = `repeat(${H}, ${sz}px)`;
  el.replaceChildren();
  el.style.fontSize = sz < 22 ? '0.65rem' : sz < 26 ? '0.75rem' : '0.9rem';
  for (let r=0;r<H;r++) for (let c=0;c<W;c++) {
    const i = idx(r,c);
    const d = document.createElement('div');
    d.className = 'c';
    d.setAttribute('role', 'gridcell');
    d.setAttribute('aria-label', `row ${r+1} col ${c+1}`);
    if (flags[i]) { d.classList.add('flag'); d.textContent = '⚑'; }
    else if (revealed[i]) {
      d.classList.add('open');
      if (cells[i] === -1) { d.classList.add('mine'); d.textContent = '✷'; }
      else if (cells[i] > 0) { d.textContent = cells[i]; d.classList.add('n'+cells[i]); }
    } else if (over && mines[i]) { d.classList.add('mine'); d.textContent = '✷'; }
    d.dataset.r = r; d.dataset.c = c;
    el.appendChild(d);
  }
}

function click(r,c) {
  if (waitingForStart || paused || over) return;
  const i = idx(r,c);
  if (flags[i]) return;
  if (firstClick) { placeMines(r,c); firstClick = false; startTimer(); }
  reveal(r,c);
  checkWin();
  if (over) {
    stopTimer();
    reportGameOver();
  }
  render(); updateHud();
}

function flag(r,c) {
  if (waitingForStart || paused || over) return;
  const i = idx(r,c);
  if (revealed[i]) return;
  flags[i] ^= 1;
  render(); updateHud();
}

// Delegated events on the board — single set of listeners, no leaks.
const boardEl = document.getElementById('board');
let pressTimer = null, longPressed = false;
function cellAt(target) {
  const d = target.closest('.c');
  if (!d || !d.dataset) return null;
  return { r: +d.dataset.r, c: +d.dataset.c };
}
boardEl.addEventListener('click', e => {
  if (longPressed) { longPressed = false; return; }
  const p = cellAt(e.target); if (p) click(p.r, p.c);
});
boardEl.addEventListener('contextmenu', e => {
  e.preventDefault();
  const p = cellAt(e.target); if (p) flag(p.r, p.c);
});
boardEl.addEventListener('touchstart', e => {
  const p = cellAt(e.target); if (!p) return;
  longPressed = false;
  clearTimeout(pressTimer);
  pressTimer = setTimeout(() => { longPressed = true; flag(p.r, p.c); pressTimer = null; }, 400);
}, { passive: true });
const cancelPress = () => { if (pressTimer) { clearTimeout(pressTimer); pressTimer = null; } };
boardEl.addEventListener('touchend', cancelPress);
boardEl.addEventListener('touchcancel', cancelPress);
boardEl.addEventListener('touchmove', cancelPress, { passive: true });

document.getElementById('reset').addEventListener('click', requestNewRun);
document.getElementById('diff').addEventListener('change', requestNewRun);
window.addEventListener('resize', () => { if (!over) render(); });

window.addEventListener('alphago:start', beginRun);
window.addEventListener('alphago:pause', () => {
  if (paused) return;
  paused = true;
  pausedAt = Date.now();
});
window.addEventListener('alphago:resume', () => {
  if (!paused) return;
  paused = false;
  if (timerStart) timerStart += (Date.now() - pausedAt);
});

reset(); // idle board behind the waiting overlay
AlphaGo.ready();
