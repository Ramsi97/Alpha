(function () {
  "use strict";

  const GRID = 20;
  const START_TICK_MS = 160;
  const MIN_TICK_MS = 70;
  const SPEEDUP_EVERY = 5; // foods
  const SPEEDUP_STEP_MS = 8;

  const canvas = document.getElementById("board");
  const ctx = canvas.getContext("2d");
  const wrapEl = document.getElementById("board-wrap");
  const waitingEl = document.querySelector(".alphago-waiting");
  const scoreEl = document.getElementById("score");
  const bestEl = document.getElementById("best");

  let cellPx = 0;
  let snake, direction, nextDirection, food, foodEaten, tickMs, best;
  let waitingForStart = true, paused = false, gameOverReported = false;

  function resizeCanvas() {
    const rect = wrapEl.getBoundingClientRect();
    const dpr = window.devicePixelRatio || 1;
    canvas.width = Math.round(rect.width * dpr);
    canvas.height = Math.round(rect.height * dpr);
    cellPx = canvas.width / GRID;
    draw();
  }

  function resetState() {
    const mid = Math.floor(GRID / 2);
    snake = [{ x: mid - 1, y: mid }, { x: mid - 2, y: mid }, { x: mid - 3, y: mid }];
    direction = { x: 1, y: 0 };
    nextDirection = direction;
    foodEaten = 0;
    tickMs = START_TICK_MS;
    gameOverReported = false;
    placeFood();
    updateHud();
    draw();
  }

  function placeFood() {
    let cell;
    do {
      cell = { x: Math.floor(Math.random() * GRID), y: Math.floor(Math.random() * GRID) };
    } while (snake.some((s) => s.x === cell.x && s.y === cell.y));
    food = cell;
  }

  function setDirection(dx, dy) {
    if (waitingForStart || paused) return;
    // Can't reverse directly into your own neck.
    if (snake.length > 1 && dx === -direction.x && dy === -direction.y) return;
    nextDirection = { x: dx, y: dy };
  }

  function showWaiting() { waitingEl.classList.remove("hidden"); }
  function hideWaiting() { waitingEl.classList.add("hidden"); }

  function updateHud() {
    scoreEl.textContent = foodEaten * 10;
    bestEl.textContent = best || 0;
  }

  function reportGameOver() {
    if (gameOverReported) return;
    gameOverReported = true;
    const score = foodEaten * 10;
    best = Math.max(best || 0, score);
    updateHud();
    AlphaGo.gameOver(score, { meta: { food: foodEaten } });
  }

  function tick() {
    if (!waitingForStart && !paused) {
      direction = nextDirection;
      const head = snake[0];
      const next = { x: head.x + direction.x, y: head.y + direction.y };

      if (next.x < 0 || next.x >= GRID || next.y < 0 || next.y >= GRID) {
        reportGameOver();
        waitingForStart = true;
        showWaiting();
      } else {
        const eating = next.x === food.x && next.y === food.y;
        const bodyToCheck = eating ? snake : snake.slice(0, -1);
        if (bodyToCheck.some((s) => s.x === next.x && s.y === next.y)) {
          reportGameOver();
          waitingForStart = true;
          showWaiting();
        } else {
          snake.unshift(next);
          if (eating) {
            foodEaten++;
            if (foodEaten % SPEEDUP_EVERY === 0) tickMs = Math.max(MIN_TICK_MS, tickMs - SPEEDUP_STEP_MS);
            placeFood();
            updateHud();
          } else {
            snake.pop();
          }
          draw();
        }
      }
    }
    setTimeout(tick, tickMs || START_TICK_MS);
  }

  function draw() {
    ctx.clearRect(0, 0, canvas.width, canvas.height);
    if (waitingForStart) return;
    // food
    ctx.fillStyle = getComputedStyle(document.documentElement).getPropertyValue("--ag-destructive") || "#e53935";
    ctx.fillRect(food.x * cellPx + 2, food.y * cellPx + 2, cellPx - 4, cellPx - 4);
    // snake
    const bodyColor = getComputedStyle(document.documentElement).getPropertyValue("--ag-button") || "#2481cc";
    snake.forEach((s, i) => {
      ctx.fillStyle = bodyColor;
      ctx.globalAlpha = i === 0 ? 1 : 0.8;
      ctx.fillRect(s.x * cellPx + 1, s.y * cellPx + 1, cellPx - 2, cellPx - 2);
    });
    ctx.globalAlpha = 1;
  }

  // Swipe controls
  let touchStartX = 0, touchStartY = 0;
  canvas.addEventListener("touchstart", (e) => {
    const t = e.touches[0];
    touchStartX = t.clientX;
    touchStartY = t.clientY;
  }, { passive: true });
  canvas.addEventListener("touchend", (e) => {
    const t = e.changedTouches[0];
    const dx = t.clientX - touchStartX;
    const dy = t.clientY - touchStartY;
    if (Math.max(Math.abs(dx), Math.abs(dy)) < 15) return; // ignore taps
    if (Math.abs(dx) > Math.abs(dy)) setDirection(dx > 0 ? 1 : -1, 0);
    else setDirection(0, dy > 0 ? 1 : -1);
  }, { passive: true });

  // Keyboard controls (desktop testing / Telegram Desktop)
  window.addEventListener("keydown", (e) => {
    const map = {
      ArrowUp: [0, -1], ArrowDown: [0, 1], ArrowLeft: [-1, 0], ArrowRight: [1, 0],
      w: [0, -1], s: [0, 1], a: [-1, 0], d: [1, 0],
    };
    const v = map[e.key];
    if (!v) return;
    e.preventDefault();
    setDirection(v[0], v[1]);
  });

  window.addEventListener("resize", resizeCanvas);

  window.addEventListener("alphago:start", () => {
    waitingForStart = false;
    paused = false;
    resetState();
    hideWaiting();
  });
  window.addEventListener("alphago:pause", () => { paused = true; });
  window.addEventListener("alphago:resume", () => { paused = false; });

  resetState(); // idle snake/score behind the waiting overlay
  resizeCanvas();
  setTimeout(tick, START_TICK_MS);
  AlphaGo.ready();
})();
