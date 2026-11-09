(function () {
  "use strict";

  const LOGICAL_W = 300, LOGICAL_H = 400;
  const ROWS = 5, COLS = 8;
  const BRICK_GAP = 4, BRICK_TOP = 30;
  const BRICK_W = (LOGICAL_W - BRICK_GAP * (COLS + 1)) / COLS;
  const BRICK_H = 16;
  const ROW_POINTS = [50, 40, 30, 20, 10]; // top row worth the most
  const PADDLE_W = 50, PADDLE_H = 10, PADDLE_Y = LOGICAL_H - 24;
  const BALL_R = 5;
  const BALL_SPEED = 180; // logical px/sec
  const MAX_VX = 160;
  const START_LIVES = 3;

  const canvas = document.getElementById("board");
  const ctx = canvas.getContext("2d");
  const wrapEl = document.getElementById("board-wrap");
  const waitingEl = document.querySelector(".alphago-waiting");
  const scoreEl = document.getElementById("score");
  const livesEl = document.getElementById("lives");

  let bricks, paddleX, ball, score, lives, waitingForStart = true, paused = false, gameOverReported = false;
  let lastT = null;

  function resizeCanvas() {
    const rect = wrapEl.getBoundingClientRect();
    const dpr = window.devicePixelRatio || 1;
    canvas.width = Math.round(rect.width * dpr);
    canvas.height = Math.round(rect.height * dpr);
    draw();
  }

  function resetState() {
    bricks = [];
    for (let r = 0; r < ROWS; r++) {
      for (let c = 0; c < COLS; c++) {
        bricks.push({
          x: BRICK_GAP + c * (BRICK_W + BRICK_GAP),
          y: BRICK_TOP + r * (BRICK_H + BRICK_GAP),
          alive: true,
          points: ROW_POINTS[r],
        });
      }
    }
    paddleX = (LOGICAL_W - PADDLE_W) / 2;
    serveBall();
    score = 0;
    lives = START_LIVES;
    gameOverReported = false;
    updateHud();
  }

  function serveBall() {
    ball = {
      x: LOGICAL_W / 2,
      y: PADDLE_Y - BALL_R - 1,
      vx: (Math.random() < 0.5 ? -1 : 1) * BALL_SPEED * 0.4,
      vy: -BALL_SPEED,
    };
  }

  function showWaiting() { waitingEl.classList.remove("hidden"); }
  function hideWaiting() { waitingEl.classList.add("hidden"); }

  function updateHud() {
    scoreEl.textContent = score;
    livesEl.textContent = lives;
  }

  function reportGameOver(outcome) {
    if (gameOverReported) return;
    gameOverReported = true;
    if (outcome === "win") score += lives * 100;
    updateHud();
    AlphaGo.gameOver(score, { meta: { outcome: outcome, lives: lives } });
  }

  function setPaddleCenter(logicalX) {
    paddleX = Math.max(0, Math.min(LOGICAL_W - PADDLE_W, logicalX - PADDLE_W / 2));
  }

  function toLogicalX(clientX) {
    const rect = wrapEl.getBoundingClientRect();
    return ((clientX - rect.left) / rect.width) * LOGICAL_W;
  }

  canvas.addEventListener("touchmove", (e) => {
    if (waitingForStart || paused) return;
    setPaddleCenter(toLogicalX(e.touches[0].clientX));
  }, { passive: true });
  canvas.addEventListener("mousemove", (e) => {
    if (waitingForStart || paused) return;
    setPaddleCenter(toLogicalX(e.clientX));
  });

  const keys = {};
  window.addEventListener("keydown", (e) => {
    if (["ArrowLeft", "ArrowRight", "a", "d"].includes(e.key)) { keys[e.key] = true; e.preventDefault(); }
  });
  window.addEventListener("keyup", (e) => { keys[e.key] = false; });

  function update(dt) {
    if (keys.ArrowLeft || keys.a) paddleX = Math.max(0, paddleX - 220 * dt);
    if (keys.ArrowRight || keys.d) paddleX = Math.min(LOGICAL_W - PADDLE_W, paddleX + 220 * dt);

    ball.x += ball.vx * dt;
    ball.y += ball.vy * dt;

    if (ball.x - BALL_R < 0) { ball.x = BALL_R; ball.vx = -ball.vx; }
    if (ball.x + BALL_R > LOGICAL_W) { ball.x = LOGICAL_W - BALL_R; ball.vx = -ball.vx; }
    if (ball.y - BALL_R < 0) { ball.y = BALL_R; ball.vy = -ball.vy; }

    if (ball.y - BALL_R > LOGICAL_H) {
      lives--;
      updateHud();
      if (lives <= 0) {
        reportGameOver("loss");
        waitingForStart = true;
        showWaiting();
        return;
      }
      serveBall();
      return;
    }

    // Paddle collision
    if (ball.vy > 0 &&
        ball.y + BALL_R >= PADDLE_Y && ball.y + BALL_R <= PADDLE_Y + PADDLE_H &&
        ball.x >= paddleX - BALL_R && ball.x <= paddleX + PADDLE_W + BALL_R) {
      ball.y = PADDLE_Y - BALL_R;
      ball.vy = -Math.abs(ball.vy);
      const offset = (ball.x - (paddleX + PADDLE_W / 2)) / (PADDLE_W / 2);
      ball.vx = Math.max(-MAX_VX, Math.min(MAX_VX, offset * MAX_VX));
    }

    // Brick collisions (resolve at most one per frame)
    for (const b of bricks) {
      if (!b.alive) continue;
      if (ball.x + BALL_R > b.x && ball.x - BALL_R < b.x + BRICK_W &&
          ball.y + BALL_R > b.y && ball.y - BALL_R < b.y + BRICK_H) {
        b.alive = false;
        score += b.points;
        ball.vy = -ball.vy;
        updateHud();
        break;
      }
    }

    if (bricks.every((b) => !b.alive)) {
      reportGameOver("win");
      waitingForStart = true;
      showWaiting();
    }
  }

  function draw() {
    const sx = canvas.width / LOGICAL_W, sy = canvas.height / LOGICAL_H;
    ctx.save();
    ctx.scale(sx, sy);
    ctx.clearRect(0, 0, LOGICAL_W, LOGICAL_H);
    if (!waitingForStart) {
      const accent = getComputedStyle(document.documentElement).getPropertyValue("--ag-button") || "#2481cc";
      const warn = getComputedStyle(document.documentElement).getPropertyValue("--ag-accent") || "#e0a800";
      bricks.forEach((b) => {
        if (!b.alive) return;
        ctx.fillStyle = warn;
        ctx.fillRect(b.x, b.y, BRICK_W, BRICK_H);
      });
      ctx.fillStyle = accent;
      ctx.fillRect(paddleX, PADDLE_Y, PADDLE_W, PADDLE_H);
      ctx.beginPath();
      ctx.arc(ball.x, ball.y, BALL_R, 0, Math.PI * 2);
      ctx.fill();
    }
    ctx.restore();
  }

  function loop(t) {
    if (lastT === null) lastT = t;
    const dt = Math.min(0.05, (t - lastT) / 1000); // clamp to avoid huge jumps after backgrounding
    lastT = t;
    if (!waitingForStart && !paused) update(dt);
    draw();
    requestAnimationFrame(loop);
  }

  window.addEventListener("resize", resizeCanvas);

  window.addEventListener("alphago:start", () => {
    waitingForStart = false;
    paused = false;
    lastT = null;
    resetState();
    hideWaiting();
  });
  window.addEventListener("alphago:pause", () => { paused = true; });
  window.addEventListener("alphago:resume", () => { paused = false; lastT = null; });

  resetState(); // idle board behind the waiting overlay
  resizeCanvas();
  requestAnimationFrame(loop);
  AlphaGo.ready();
})();
