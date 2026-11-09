(function () {
  "use strict";

  const N = 5;
  const boardEl  = document.getElementById("board");
  const statusEl = document.getElementById("status");
  const movesEl  = document.getElementById("moves");
  const bestEl   = document.getElementById("best");
  const undoBtn  = document.getElementById("undo-btn");
  const resetBtn = document.getElementById("reset-btn");
  const newBtn   = document.getElementById("new-btn");
  const chipsEl  = document.getElementById("chips");
  const waitingEl = document.querySelector(".alphago-waiting");

  const DIFFS = { easy: 3, medium: 6, hard: 10 };
  const store = Gamekit.storage("lights-out:");

  let diff = "medium";
  let board = new Uint8Array(N * N);
  let initial = new Uint8Array(N * N);
  let history = [];
  let moves = 0;
  let won = false;
  let cellEls = [];
  let waitingForStart = true, paused = false, gameOverReported = false;

  function idx(r, c) { return r * N + c; }
  function inB(r, c) { return r >= 0 && r < N && c >= 0 && c < N; }

  function press(b, r, c) {
    b[idx(r, c)] ^= 1;
    if (inB(r-1, c)) b[idx(r-1, c)] ^= 1;
    if (inB(r+1, c)) b[idx(r+1, c)] ^= 1;
    if (inB(r, c-1)) b[idx(r, c-1)] ^= 1;
    if (inB(r, c+1)) b[idx(r, c+1)] ^= 1;
  }

  function generate(seed, scrambles) {
    const rng = Gamekit.mulberry32(seed);
    const b = new Uint8Array(N * N);
    const used = new Set();
    let applied = 0, safety = 0;
    while (applied < scrambles && safety < scrambles * 8) {
      safety++;
      const r = Math.floor(rng() * N);
      const c = Math.floor(rng() * N);
      const k = r * N + c;
      if (used.has(k)) continue;
      used.add(k);
      press(b, r, c);
      applied++;
    }
    if (!b.some(x => x)) press(b, 2, 2);
    return b;
  }

  // AlphaGo: seed always comes from the host's `start` message when
  // provided, never the player's device clock (plan section 7 notes).
  // Falls back to a random seed only for the idle board shown pre-`start`.
  function newPuzzle(seedOverride) {
    const seed = seedOverride !== undefined ? seedOverride : Gamekit.randomSeed();
    initial = generate(seed, DIFFS[diff]);
    board = new Uint8Array(initial);
    history = [];
    moves = 0;
    won = false;
    gameOverReported = false;
    renderFresh();
    updateStatus();
  }

  // "new" / difficulty change end the run and wait for the host's next
  // `start` (plan section 6.6). "reset"/"undo" stay in-run — they don't
  // change the puzzle, just the player's progress on it.
  function requestNewRun() {
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

  function renderFresh() {
    boardEl.innerHTML = "";
    cellEls = [];
    for (let r = 0; r < N; r++) {
      for (let c = 0; c < N; c++) {
        const cell = document.createElement("button");
        cell.type = "button";
        cell.className = "lo-cell fade-in" + (board[idx(r, c)] ? " on" : "");
        cell.style.animationDelay = ((r * N + c) * 14) + "ms";
        cell.setAttribute("aria-label", "Row " + (r + 1) + " col " + (c + 1));
        const rr = r, cc = c;
        cell.addEventListener("click", () => onPress(rr, cc));
        boardEl.appendChild(cell);
        cellEls.push(cell);
      }
    }
  }

  function syncLights() {
    for (let i = 0; i < N * N; i++) {
      cellEls[i].classList.toggle("on", !!board[i]);
    }
  }

  function onPress(r, c) {
    if (waitingForStart || paused || won) return;
    history.push(new Uint8Array(board));
    press(board, r, c);
    moves++;
    syncLights();
    updateStatus();
  }

  // The scramble count doubles as "par" — the puzzle is generated with
  // exactly this many presses, though the true minimum solve length can be
  // shorter if presses happened to overlap/cancel (not computed exactly;
  // see CREDITS.md).
  function reportGameOver() {
    if (gameOverReported) return;
    gameOverReported = true;
    const par = DIFFS[diff];
    const score = Math.max(0, 1000 - 25 * Math.max(0, moves - par));
    AlphaGo.gameOver(score, { variant: diff, meta: { moves, par } });
  }

  function updateStatus() {
    movesEl.textContent = moves;
    const best = store.getInt("best:" + diff, null);
    bestEl.textContent = (best === null) ? "—" : best;

    const anyOn = board.some(x => x);
    if (!anyOn && !won) {
      won = true;
      statusEl.innerHTML = '<span class="ok">Solved in ' + moves + ' moves.</span>';
      if (best === null || moves < best) {
        store.set("best:" + diff, moves);
        bestEl.textContent = moves;
      }
      reportGameOver();
    } else if (!won) {
      const on = board.reduce((a, x) => a + x, 0);
      statusEl.textContent = on + ' light' + (on === 1 ? '' : 's') + ' still on.';
    }
  }

  // Difficulty chips
  Gamekit.wireDifficultyChips({
    el: chipsEl,
    difficulties: ["easy", "medium", "hard"],
    initial: diff,
    storage: store,
    storageKey: "diff",
    onChange: (d) => { diff = d; requestNewRun(); },
  });
  // Pull stored diff back (gamekit already applied it visually, but our local var needs sync)
  const storedDiff = store.get("diff", "medium");
  if (DIFFS[storedDiff]) diff = storedDiff;

  undoBtn.addEventListener("click", () => {
    if (waitingForStart || paused || history.length === 0) return;
    board = history.pop();
    moves = Math.max(0, moves - 1);
    won = false;
    syncLights();
    updateStatus();
  });

  resetBtn.addEventListener("click", () => {
    if (waitingForStart) return;
    board = new Uint8Array(initial);
    history = [];
    moves = 0;
    won = false;
    gameOverReported = false;
    syncLights();
    updateStatus();
  });

  newBtn.addEventListener("click", requestNewRun);

  window.addEventListener("alphago:start", (e) => beginRun(e.detail && e.detail.seed));
  window.addEventListener("alphago:pause", () => { paused = true; });
  window.addEventListener("alphago:resume", () => { paused = false; });

  // Idle puzzle behind the waiting overlay + manpage auto-open removed
  // (popping a modal over the waiting screen on every load was poor fit).
  newPuzzle();
  AlphaGo.ready();
})();
