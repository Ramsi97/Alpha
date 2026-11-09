(function () {
  "use strict";

  const ROWS = 6, COLS = 7;
  const P1 = 1, P2 = 2, EMPTY = 0;

  const boardEl  = document.getElementById("board");
  const colsEl   = document.getElementById("cols");
  const statusEl = document.getElementById("status");
  const undoBtn  = document.getElementById("undo-btn");
  const resetBtn = document.getElementById("reset-btn");
  const chipsEl  = document.getElementById("chips");
  const modeSel  = document.getElementById("mode");
  const waitingEl = document.querySelector(".alphago-waiting");

  const DEPTHS = { easy: 2, medium: 4, hard: 6 };
  const DIFF_SCORE_MULT = { easy: 0.7, medium: 1, hard: 1.4 };
  const store = Gamekit.storage("connect-four:");

  let diff = store.get("diff", "medium");
  if (!DEPTHS[diff]) diff = "medium";
  let mode = store.get("mode", "ai-first-p1");
  if (!["ai-first-p1", "ai-first-p2"].includes(mode)) mode = "ai-first-p1";
  modeSel.value = mode;

  let grid = newGrid();       // 6×7, grid[r][c]
  let history = [];           // stack of {col, row, player}
  let current = P1;
  let gameOver = false;
  let winLine = null;         // [{r,c},...]
  let thinking = false;
  let humanIs = P1;           // set per mode
  let waitingForStart = true, paused = false, gameOverReported = false;

  function newGrid() {
    const g = [];
    for (let r = 0; r < ROWS; r++) g.push(new Uint8Array(COLS));
    return g;
  }

  function showWaiting() { waitingEl.classList.remove("hidden"); }
  function hideWaiting() { waitingEl.classList.add("hidden"); }

  function renderShell() {
    colsEl.innerHTML = "";
    for (let c = 0; c < COLS; c++) {
      const btn = document.createElement("button");
      btn.type = "button";
      btn.className = "c4-col-btn";
      btn.textContent = "↓";
      btn.setAttribute("aria-label", "Drop in column " + (c + 1));
      btn.dataset.col = String(c);
      btn.addEventListener("click", () => onColClick(c));
      colsEl.appendChild(btn);
    }
    boardEl.innerHTML = "";
    for (let r = 0; r < ROWS; r++) {
      for (let c = 0; c < COLS; c++) {
        const cell = document.createElement("div");
        cell.className = "c4-slot";
        cell.dataset.r = String(r);
        cell.dataset.c = String(c);
        boardEl.appendChild(cell);
      }
    }
  }

  function renderBoard() {
    for (let r = 0; r < ROWS; r++) {
      for (let c = 0; c < COLS; c++) {
        const i = r * COLS + c;
        const el = boardEl.children[i];
        el.classList.remove("p1", "p2", "win");
        if (grid[r][c] === P1) el.classList.add("p1");
        else if (grid[r][c] === P2) el.classList.add("p2");
      }
    }
    if (winLine) {
      winLine.forEach(({ r, c }) => {
        boardEl.children[r * COLS + c].classList.add("win");
      });
    }
    // Disable full columns
    for (let c = 0; c < COLS; c++) {
      const btn = colsEl.children[c];
      btn.disabled = waitingForStart || paused || gameOver || thinking || grid[0][c] !== EMPTY;
    }
  }

  function dropRow(g, c) {
    for (let r = ROWS - 1; r >= 0; r--) if (g[r][c] === EMPTY) return r;
    return -1;
  }

  function makeMove(c, p) {
    const r = dropRow(grid, c);
    if (r < 0) return false;
    grid[r][c] = p;
    history.push({ r, c, p });
    return true;
  }

  function undoMove() {
    const m = history.pop();
    if (!m) return false;
    grid[m.r][m.c] = EMPTY;
    return true;
  }

  // Check if placing `p` at (r,c) creates a 4-in-a-row. Returns the winning line or null.
  function winAt(g, r, c, p) {
    const dirs = [[0,1],[1,0],[1,1],[1,-1]];
    for (const [dr, dc] of dirs) {
      const line = [{r, c}];
      for (let k = 1; k < 4; k++) {
        const nr = r + dr * k, nc = c + dc * k;
        if (nr < 0 || nr >= ROWS || nc < 0 || nc >= COLS || g[nr][nc] !== p) break;
        line.push({r: nr, c: nc});
      }
      for (let k = 1; k < 4; k++) {
        const nr = r - dr * k, nc = c - dc * k;
        if (nr < 0 || nr >= ROWS || nc < 0 || nc >= COLS || g[nr][nc] !== p) break;
        line.unshift({r: nr, c: nc});
      }
      if (line.length >= 4) return line.slice(0, 4);
    }
    return null;
  }

  function isFull(g) {
    for (let c = 0; c < COLS; c++) if (g[0][c] === EMPTY) return false;
    return true;
  }

  // Heuristic evaluation: count "threats" in every 4-window
  const COL_WEIGHT = [3, 4, 5, 7, 5, 4, 3];
  function evalWindow(w, me, them) {
    let mine = 0, yours = 0, empty = 0;
    for (const v of w) { if (v === me) mine++; else if (v === them) yours++; else empty++; }
    if (mine > 0 && yours > 0) return 0;
    if (mine === 4) return 100000;
    if (yours === 4) return -100000;
    if (mine === 3 && empty === 1) return 50;
    if (mine === 2 && empty === 2) return 5;
    if (yours === 3 && empty === 1) return -80;
    if (yours === 2 && empty === 2) return -4;
    return 0;
  }
  function evaluate(g, me) {
    const them = me === P1 ? P2 : P1;
    let score = 0;
    // Center column bias
    for (let r = 0; r < ROWS; r++) if (g[r][3] === me) score += 3;
    for (let c = 0; c < COLS; c++) for (let r = 0; r < ROWS; r++) {
      if (g[r][c] === me) score += COL_WEIGHT[c] * 0.3;
    }
    // Horizontal
    for (let r = 0; r < ROWS; r++)
      for (let c = 0; c <= COLS - 4; c++)
        score += evalWindow([g[r][c], g[r][c+1], g[r][c+2], g[r][c+3]], me, them);
    // Vertical
    for (let c = 0; c < COLS; c++)
      for (let r = 0; r <= ROWS - 4; r++)
        score += evalWindow([g[r][c], g[r+1][c], g[r+2][c], g[r+3][c]], me, them);
    // Diagonal /
    for (let r = 3; r < ROWS; r++)
      for (let c = 0; c <= COLS - 4; c++)
        score += evalWindow([g[r][c], g[r-1][c+1], g[r-2][c+2], g[r-3][c+3]], me, them);
    // Diagonal \
    for (let r = 0; r <= ROWS - 4; r++)
      for (let c = 0; c <= COLS - 4; c++)
        score += evalWindow([g[r][c], g[r+1][c+1], g[r+2][c+2], g[r+3][c+3]], me, them);
    return score;
  }

  const COL_ORDER = [3, 2, 4, 1, 5, 0, 6];

  function alphabeta(g, depth, alpha, beta, maximizing, me) {
    const them = me === P1 ? P2 : P1;

    if (depth === 0) return { score: evaluate(g, me), col: -1 };

    let bestCol = -1;
    if (maximizing) {
      let best = -Infinity;
      for (const c of COL_ORDER) {
        const r = dropRow(g, c);
        if (r < 0) continue;
        g[r][c] = me;
        const win = winAt(g, r, c, me);
        let val;
        if (win) val = 100000 + depth;
        else if (isFull(g)) val = 0;
        else val = alphabeta(g, depth - 1, alpha, beta, false, me).score;
        g[r][c] = EMPTY;
        if (val > best) { best = val; bestCol = c; }
        alpha = Math.max(alpha, val);
        if (beta <= alpha) break;
      }
      return { score: best, col: bestCol };
    } else {
      let best = Infinity;
      for (const c of COL_ORDER) {
        const r = dropRow(g, c);
        if (r < 0) continue;
        g[r][c] = them;
        const win = winAt(g, r, c, them);
        let val;
        if (win) val = -100000 - depth;
        else if (isFull(g)) val = 0;
        else val = alphabeta(g, depth - 1, alpha, beta, true, me).score;
        g[r][c] = EMPTY;
        if (val < best) { best = val; bestCol = c; }
        beta = Math.min(beta, val);
        if (beta <= alpha) break;
      }
      return { score: best, col: bestCol };
    }
  }

  function pickAIMove(me) {
    const depth = DEPTHS[diff];
    const res = alphabeta(grid, depth, -Infinity, Infinity, true, me);
    let col = res.col;
    if (col < 0 || dropRow(grid, col) < 0) {
      for (const c of COL_ORDER) if (dropRow(grid, c) >= 0) { col = c; break; }
    }
    return col;
  }

  function onColClick(c) {
    if (waitingForStart || paused || gameOver || thinking || current !== humanIs) return;
    if (!playMove(c)) return;
    advance();
  }

  // Score per plan section 7: win 500 + (42-moves)*10, draw 100, loss 0,
  // all scaled by a difficulty multiplier (not specified exactly by the
  // plan — placeholder values, see CREDITS.md).
  function reportGameOver(outcome) {
    if (gameOverReported) return;
    gameOverReported = true;
    let raw;
    if (outcome === "draw") raw = 100;
    else if (outcome === "win") raw = 500 + (42 - history.length) * 10;
    else raw = 0;
    const score = Math.round(raw * DIFF_SCORE_MULT[diff]);
    AlphaGo.gameOver(score, { variant: diff, meta: { outcome, moves: history.length } });
  }

  function playMove(c) {
    if (dropRow(grid, c) < 0) return false;
    const ok = makeMove(c, current);
    if (!ok) return false;
    const last = history[history.length - 1];
    const win = winAt(grid, last.r, last.c, last.p);
    if (win) {
      winLine = win;
      gameOver = true;
      const humanWon = last.p === humanIs;
      statusEl.innerHTML = '<span class="ok">' + (humanWon ? "You win." : "AI wins.") + '</span>';
      reportGameOver(humanWon ? "win" : "loss");
    } else if (isFull(grid)) {
      gameOver = true;
      statusEl.textContent = "Draw.";
      reportGameOver("draw");
    } else {
      current = current === P1 ? P2 : P1;
      updateTurnStatus();
    }
    renderBoard();
    return true;
  }

  function updateTurnStatus() {
    if (gameOver) return;
    statusEl.textContent = current === humanIs ? "Your turn · drop a checker." : "AI thinking…";
  }

  let aiTimer = null;
  function cancelAI() { if (aiTimer !== null) { clearTimeout(aiTimer); aiTimer = null; } thinking = false; }

  function advance() {
    if (waitingForStart || paused || gameOver) return;
    if (current !== humanIs) {
      thinking = true;
      renderBoard();
      const gen = aiTimer = setTimeout(() => {
        if (aiTimer !== gen) return;
        aiTimer = null;
        if (gameOver || paused || current === humanIs) { thinking = false; renderBoard(); return; }
        const col = pickAIMove(current);
        thinking = false;
        if (col >= 0) playMove(col);
      }, 150);
    }
  }

  function applyMode() {
    humanIs = mode === "ai-first-p2" ? P2 : P1;
    reset();
  }

  function reset() {
    cancelAI();
    grid = newGrid();
    history = [];
    current = P1;
    gameOver = false;
    winLine = null;
    gameOverReported = false;
    renderShell();
    renderBoard();
    updateTurnStatus();
    if (!waitingForStart && current !== humanIs) advance();
  }

  // AlphaGo: "new game", mode change, and difficulty change all end the run
  // and wait for the host's next `start`; "undo" stays in-run.
  function requestNewRun() {
    waitingForStart = true;
    applyMode();
    showWaiting();
    renderBoard();
  }

  function beginRun() {
    waitingForStart = false;
    paused = false;
    applyMode();
    hideWaiting();
  }

  undoBtn.addEventListener("click", () => {
    if (waitingForStart || paused || thinking) return;
    if (history.length === 0) return;
    // Undo last move; in AI mode, undo the pair so it's the player's turn again.
    undoMove();
    if (!gameOver && history.length > 0) {
      const last = history[history.length - 1];
      if (last.p === humanIs) undoMove();
    }
    gameOver = false;
    winLine = null;
    gameOverReported = false;
    // Recompute whose turn it is based on history
    current = history.length % 2 === 0 ? P1 : P2;
    renderBoard();
    updateTurnStatus();
  });

  resetBtn.addEventListener("click", requestNewRun);

  modeSel.addEventListener("change", () => {
    mode = modeSel.value;
    store.set("mode", mode);
    requestNewRun();
  });

  Gamekit.wireDifficultyChips({
    el: chipsEl,
    difficulties: ["easy", "medium", "hard"],
    initial: diff,
    storage: store,
    storageKey: "diff",
    onChange: (d) => { diff = d; requestNewRun(); },
  });
  // sync local diff after wiring
  diff = store.get("diff", diff);
  if (!DEPTHS[diff]) diff = "medium";

  window.addEventListener("alphago:start", beginRun);
  window.addEventListener("alphago:pause", () => {
    paused = true;
    cancelAI();
    renderBoard();
  });
  window.addEventListener("alphago:resume", () => {
    paused = false;
    advance();
    renderBoard();
  });

  // Idle board behind the waiting overlay + manpage auto-open removed.
  applyMode();
  AlphaGo.ready();
})();
