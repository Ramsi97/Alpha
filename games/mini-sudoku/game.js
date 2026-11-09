(function () {
  "use strict";

  const N = 6;
  const DIGITS = [1, 2, 3, 4, 5, 6];
  const DIFFS = { easy: 22, medium: 18, hard: 14 };
  const DIFF_MULT = { easy: 1, medium: 1.5, hard: 2 };

  const boardEl  = document.getElementById("board");
  const padEl    = document.getElementById("pad");
  const statusEl = document.getElementById("status");
  const timeEl   = document.getElementById("time");
  const bestEl   = document.getElementById("best");
  const undoBtn  = document.getElementById("undo-btn");
  const resetBtn = document.getElementById("reset-btn");
  const newBtn   = document.getElementById("new-btn");
  const chipsEl  = document.getElementById("chips");
  const waitingEl = document.querySelector(".alphago-waiting");

  const store = Gamekit.storage("mini-sudoku:");

  let diff = store.get("diff", "medium");
  if (!DIFFS[diff]) diff = "medium";

  // State
  let givens = new Uint8Array(N * N);   // 0 or 1-6 (initial puzzle)
  let grid = new Uint8Array(N * N);     // current values
  let notes = [];                        // array of Sets per cell
  let history = [];
  let sel = -1;                          // selected index
  let pencil = false;
  let won = false;
  let timerStart = 0;
  let timerInterval = null;
  let elapsed = 0;
  let cellEls = [];
  let mistakes = 0;
  const hints = 0; // no hint feature in this build

  let waitingForStart = true, paused = false, pausedAt = 0, gameOverReported = false;

  function idx(r, c) { return r * N + c; }
  function rof(i) { return Math.floor(i / N); }
  function cof(i) { return i % N; }
  function box(r, c) { return Math.floor(r / 2) * 2 + Math.floor(c / 3); }

  function allowed(g, r, c, v) {
    for (let i = 0; i < N; i++) {
      if (g[idx(r, i)] === v) return false;
      if (g[idx(i, c)] === v) return false;
    }
    const br = Math.floor(r / 2) * 2;
    const bc = Math.floor(c / 3) * 3;
    for (let rr = br; rr < br + 2; rr++)
      for (let cc = bc; cc < bc + 3; cc++)
        if (g[idx(rr, cc)] === v) return false;
    return true;
  }

  // Fill random valid grid
  function fillRandom(g, rng, pos) {
    if (pos >= N * N) return true;
    const r = rof(pos), c = cof(pos);
    if (g[pos] !== 0) return fillRandom(g, rng, pos + 1);
    const digs = Gamekit.shuffle(DIGITS.slice(), rng);
    for (const v of digs) {
      if (allowed(g, r, c, v)) {
        g[pos] = v;
        if (fillRandom(g, rng, pos + 1)) return true;
        g[pos] = 0;
      }
    }
    return false;
  }

  // Count solutions up to `limit`
  function countSolutions(g, limit) {
    // Find first empty
    let pos = -1;
    for (let i = 0; i < N * N; i++) if (g[i] === 0) { pos = i; break; }
    if (pos === -1) return 1;
    const r = rof(pos), c = cof(pos);
    let count = 0;
    for (let v = 1; v <= N; v++) {
      if (allowed(g, r, c, v)) {
        g[pos] = v;
        count += countSolutions(g, limit - count);
        g[pos] = 0;
        if (count >= limit) return count;
      }
    }
    return count;
  }

  function dig(g, targetClues, rng) {
    const order = [];
    for (let i = 0; i < N * N; i++) order.push(i);
    Gamekit.shuffle(order, rng);
    let clues = N * N;
    for (const i of order) {
      if (clues <= targetClues) break;
      const saved = g[i];
      if (saved === 0) continue;
      g[i] = 0;
      // Clone grid to test uniqueness
      const test = new Uint8Array(g);
      const n = countSolutions(test, 2);
      if (n !== 1) {
        g[i] = saved;
      } else {
        clues--;
      }
    }
    return clues;
  }

  function generate(seed) {
    const rng = Gamekit.mulberry32(seed);
    const g = new Uint8Array(N * N);
    fillRandom(g, rng, 0);
    dig(g, DIFFS[diff], rng);
    return g;
  }

  // AlphaGo: seed always comes from the host's `start` message when
  // provided, never the player's device clock. Falls back to a random seed
  // only for the idle board shown before the first `start`.
  function newPuzzle(seedOverride) {
    const seed = seedOverride !== undefined ? seedOverride : Gamekit.randomSeed();
    givens = generate(seed);
    grid = new Uint8Array(givens);
    notes = [];
    for (let i = 0; i < N * N; i++) notes.push(new Set());
    history = [];
    sel = -1;
    pencil = false;
    won = false;
    mistakes = 0;
    gameOverReported = false;
    elapsed = 0;
    timerStart = Date.now();
    startTimer();
    renderShell();
    renderAll();
    updateStatus();
    updatePencilBtn();
  }

  // "new" / difficulty change end the run and wait for the host's next
  // `start`; "undo"/"reset" stay in-run.
  function requestNewRun() {
    stopTimer();
    newPuzzle();
    waitingForStart = true;
    showWaiting();
  }

  function beginRun(seed) {
    waitingForStart = false;
    paused = false;
    newPuzzle(seed);
    hideWaiting();
  }

  function showWaiting() { waitingEl.classList.remove("hidden"); }
  function hideWaiting() { waitingEl.classList.add("hidden"); }

  function stopTimer() {
    if (timerInterval) { clearInterval(timerInterval); timerInterval = null; }
  }

  function renderShell() {
    boardEl.innerHTML = "";
    cellEls = [];
    for (let r = 0; r < N; r++) {
      for (let c = 0; c < N; c++) {
        const cell = document.createElement("div");
        cell.className = "sk-cell fade-in" + (givens[idx(r, c)] ? " given" : "");
        cell.dataset.r = String(r);
        cell.dataset.c = String(c);
        cell.style.animationDelay = ((r * N + c) * 10) + "ms";
        const i = idx(r, c);
        cell.addEventListener("click", () => { if (waitingForStart || paused || won) return; sel = i; renderAll(); });
        boardEl.appendChild(cell);
        cellEls.push(cell);
      }
    }
  }

  function renderAll() {
    for (let i = 0; i < N * N; i++) {
      const el = cellEls[i];
      el.classList.remove("sel", "peer", "same-num", "conflict");
      el.innerHTML = "";
      const v = grid[i];
      if (v) {
        el.textContent = String(v);
      } else if (notes[i].size > 0) {
        const nDiv = document.createElement("div");
        nDiv.className = "notes";
        for (let n = 1; n <= N; n++) {
          const s = document.createElement("span");
          s.textContent = notes[i].has(n) ? String(n) : "";
          nDiv.appendChild(s);
        }
        el.appendChild(nDiv);
      }
    }
    if (sel >= 0) {
      const sr = rof(sel), sc = cof(sel), sv = grid[sel];
      const sbox = box(sr, sc);
      for (let i = 0; i < N * N; i++) {
        const r = rof(i), c = cof(i);
        if (i === sel) cellEls[i].classList.add("sel");
        else if (r === sr || c === sc || box(r, c) === sbox) cellEls[i].classList.add("peer");
        if (sv && grid[i] === sv && i !== sel) cellEls[i].classList.add("same-num");
      }
    }
    // Conflicts
    for (let i = 0; i < N * N; i++) {
      if (!grid[i] || givens[i]) continue;
      if (isConflict(i)) cellEls[i].classList.add("conflict");
    }
    // Pad digit "done" state (digit appears 6 times)
    const counts = new Array(N + 1).fill(0);
    for (let i = 0; i < N * N; i++) if (grid[i]) counts[grid[i]]++;
    padEl.querySelectorAll("[data-digit]").forEach(b => {
      const d = parseInt(b.dataset.digit, 10);
      b.classList.toggle("done", counts[d] >= N);
    });
  }

  function isConflict(i) {
    const v = grid[i];
    if (!v) return false;
    const r = rof(i), c = cof(i);
    for (let k = 0; k < N; k++) {
      if (k !== c && grid[idx(r, k)] === v) return true;
      if (k !== r && grid[idx(k, c)] === v) return true;
    }
    const br = Math.floor(r / 2) * 2;
    const bc = Math.floor(c / 3) * 3;
    for (let rr = br; rr < br + 2; rr++)
      for (let cc = bc; cc < bc + 3; cc++)
        if ((rr !== r || cc !== c) && grid[idx(rr, cc)] === v) return true;
    return false;
  }

  function renderPad() {
    padEl.innerHTML = "";
    for (let d = 1; d <= N; d++) {
      const b = document.createElement("button");
      b.type = "button";
      b.className = "btn";
      b.dataset.digit = String(d);
      b.textContent = String(d);
      b.addEventListener("click", () => onDigit(d));
      padEl.appendChild(b);
    }
    const del = document.createElement("button");
    del.type = "button";
    del.className = "btn";
    del.textContent = "⌫";
    del.setAttribute("aria-label", "Erase");
    del.addEventListener("click", () => onDigit(0));
    padEl.appendChild(del);
    // Pencil toggle goes in toolbar area too — add as extra row via CSS grid column span
    // Put pencil as separate row
    const penWrap = document.createElement("div");
    penWrap.style.gridColumn = "1 / -1";
    penWrap.style.display = "flex";
    penWrap.style.justifyContent = "center";
    penWrap.style.marginTop = "6px";
    const pen = document.createElement("button");
    pen.type = "button";
    pen.id = "pencil-btn";
    pen.className = "btn tool-btn";
    pen.innerHTML = '<span class="glyph">✎</span> pencil';
    pen.addEventListener("click", () => { if (waitingForStart || paused) return; pencil = !pencil; updatePencilBtn(); });
    penWrap.appendChild(pen);
    padEl.appendChild(penWrap);
  }

  function updatePencilBtn() {
    const b = document.getElementById("pencil-btn");
    if (!b) return;
    b.classList.toggle("pencil-on", pencil);
    b.setAttribute("aria-pressed", pencil ? "true" : "false");
  }

  function onDigit(d) {
    if (waitingForStart || paused || won) return;
    if (sel < 0) return;
    if (givens[sel]) return;

    history.push({ idx: sel, v: grid[sel], notes: new Set(notes[sel]) });

    if (d === 0) {
      grid[sel] = 0;
      notes[sel].clear();
    } else if (pencil) {
      if (grid[sel]) grid[sel] = 0;
      if (notes[sel].has(d)) notes[sel].delete(d);
      else notes[sel].add(d);
    } else {
      grid[sel] = d;
      notes[sel].clear();
      if (isConflict(sel)) mistakes++;
    }
    renderAll();
    checkWin();
  }

  function startTimer() {
    stopTimer();
    timeEl.textContent = Gamekit.fmtTime(0);
    timerInterval = setInterval(() => {
      if (won || paused) return;
      const s = Math.floor((Date.now() - timerStart) / 1000);
      timeEl.textContent = Gamekit.fmtTime(s);
    }, 500);
  }

  function updateStatus() {
    const best = store.getInt("best:" + diff, null);
    bestEl.textContent = best === null ? "—" : Gamekit.fmtTime(best);
  }

  function reportGameOver(seconds) {
    if (gameOverReported) return;
    gameOverReported = true;
    const mult = DIFF_MULT[diff];
    const score = mult * Math.max(100, 1000 - 2 * seconds - 50 * mistakes - 100 * hints);
    AlphaGo.gameOver(score, { variant: diff, meta: { seconds, mistakes, hints } });
  }

  function checkWin() {
    for (let i = 0; i < N * N; i++) if (!grid[i]) return;
    // Validate
    for (let i = 0; i < N * N; i++) if (isConflict(i)) {
      statusEl.innerHTML = '<span class="bad">Not quite — fix conflicts.</span>';
      return;
    }
    won = true;
    const s = Math.floor((Date.now() - timerStart) / 1000);
    elapsed = s;
    const best = store.getInt("best:" + diff, null);
    if (best === null || s < best) {
      store.set("best:" + diff, s);
      bestEl.textContent = Gamekit.fmtTime(s);
    }
    statusEl.innerHTML = '<span class="ok">Solved in ' + Gamekit.fmtTime(s) + '.</span>';
    reportGameOver(s);
  }

  // Keyboard
  document.addEventListener("keydown", (e) => {
    if (waitingForStart || paused) return;
    if (e.target.closest("input, select, textarea")) return;
    if (document.querySelector(".man-backdrop")) return;
    if (won) return;
    const k = e.key;
    if (k === "ArrowLeft" || k === "ArrowRight" || k === "ArrowUp" || k === "ArrowDown") {
      if (sel < 0) { sel = 0; }
      else {
        let r = rof(sel), c = cof(sel);
        if (k === "ArrowLeft")  c = (c + N - 1) % N;
        if (k === "ArrowRight") c = (c + 1) % N;
        if (k === "ArrowUp")    r = (r + N - 1) % N;
        if (k === "ArrowDown")  r = (r + 1) % N;
        sel = idx(r, c);
      }
      e.preventDefault();
      renderAll();
      return;
    }
    if (k >= "1" && k <= "6") { onDigit(parseInt(k, 10)); e.preventDefault(); return; }
    if (k === "Backspace" || k === "Delete" || k === "0") { onDigit(0); e.preventDefault(); return; }
    if (k === "p" || k === "P") { pencil = !pencil; updatePencilBtn(); e.preventDefault(); return; }
  });

  undoBtn.addEventListener("click", () => {
    if (waitingForStart || paused || won) return;
    const h = history.pop();
    if (!h) return;
    grid[h.idx] = h.v;
    notes[h.idx] = h.notes;
    renderAll();
  });
  resetBtn.addEventListener("click", () => {
    // No confirm() dialog: sandboxed iframes without allow-modals can't show
    // blocking dialogs, and clearing entries isn't destructive enough to
    // need one (no real persistence is at stake — plan section 6.3).
    if (waitingForStart) return;
    grid = new Uint8Array(givens);
    notes = notes.map(() => new Set());
    history = [];
    won = false;
    mistakes = 0;
    gameOverReported = false;
    sel = -1;
    timerStart = Date.now();
    startTimer();
    statusEl.textContent = "Fill each row, column, and 2×3 box with 1–6.";
    renderAll();
  });
  newBtn.addEventListener("click", requestNewRun);

  Gamekit.wireDifficultyChips({
    el: chipsEl,
    difficulties: ["easy", "medium", "hard"],
    initial: diff,
    storage: store,
    storageKey: "diff",
    onChange: (d) => { diff = d; requestNewRun(); updateStatus(); },
  });
  diff = store.get("diff", diff);
  if (!DIFFS[diff]) diff = "medium";

  window.addEventListener("alphago:start", (e) => beginRun(e.detail && e.detail.seed));
  window.addEventListener("alphago:pause", () => {
    if (paused) return;
    paused = true;
    pausedAt = Date.now();
  });
  window.addEventListener("alphago:resume", () => {
    if (!paused) return;
    paused = false;
    if (timerStart) timerStart += (Date.now() - pausedAt);
  });

  renderPad();
  newPuzzle(); // idle board behind the waiting overlay
  updateStatus();
  AlphaGo.ready();
})();
