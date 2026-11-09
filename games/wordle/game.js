(function () {
  "use strict";

  const WORD_LEN = 5;
  const MAX_GUESSES = 6;
  const GUESS_SET = new Set(window.WORDLE_GUESSES);
  const ANSWERS = window.WORDLE_ANSWERS;

  const boardEl = document.getElementById("board");
  const keyboardEl = document.getElementById("keyboard");
  const messageEl = document.getElementById("message");
  const waitingEl = document.querySelector(".alphago-waiting");

  let answer = "";
  let guesses = [];       // array of {word, statuses}
  let currentGuess = "";
  let keyStatus = {};     // letter -> 'correct' | 'present' | 'absent'
  let waitingForStart = true, paused = false, finished = false, gameOverReported = false;
  let messageTimer = null;

  function showWaiting() { waitingEl.classList.remove("hidden"); }
  function hideWaiting() { waitingEl.classList.add("hidden"); }

  function setMessage(text, ms) {
    messageEl.textContent = text;
    clearTimeout(messageTimer);
    if (ms) messageTimer = setTimeout(() => { messageEl.textContent = ""; }, ms);
  }

  // Two-pass evaluation so duplicate letters are scored correctly.
  function evaluate(guess, ans) {
    const result = new Array(WORD_LEN).fill("absent");
    const ansArr = ans.split("");
    const guessArr = guess.split("");
    for (let i = 0; i < WORD_LEN; i++) {
      if (guessArr[i] === ansArr[i]) {
        result[i] = "correct";
        ansArr[i] = null;
        guessArr[i] = null;
      }
    }
    for (let i = 0; i < WORD_LEN; i++) {
      if (guessArr[i] === null) continue;
      const idx = ansArr.indexOf(guessArr[i]);
      if (idx !== -1) {
        result[i] = "present";
        ansArr[idx] = null;
      }
    }
    return result;
  }

  const KEY_RANK = { absent: 0, present: 1, correct: 2 };
  function updateKeyStatus(word, statuses) {
    for (let i = 0; i < WORD_LEN; i++) {
      const letter = word[i], status = statuses[i];
      if (!keyStatus[letter] || KEY_RANK[status] > KEY_RANK[keyStatus[letter]]) {
        keyStatus[letter] = status;
      }
    }
  }

  function renderBoard() {
    boardEl.innerHTML = "";
    for (let r = 0; r < MAX_GUESSES; r++) {
      const rowEl = document.createElement("div");
      rowEl.className = "row";
      const submitted = guesses[r];
      const isCurrentRow = r === guesses.length && !finished;
      for (let c = 0; c < WORD_LEN; c++) {
        const tile = document.createElement("div");
        tile.className = "tile";
        if (submitted) {
          tile.textContent = submitted.word[c];
          tile.classList.add(submitted.statuses[c]);
        } else if (isCurrentRow && c < currentGuess.length) {
          tile.textContent = currentGuess[c];
          tile.classList.add("filled");
        }
        rowEl.appendChild(tile);
      }
      boardEl.appendChild(rowEl);
    }
  }

  const KEY_ROWS = [
    "q w e r t y u i o p".split(" "),
    "a s d f g h j k l".split(" "),
    ["enter", "z", "x", "c", "v", "b", "n", "m", "back"],
  ];

  function renderKeyboard() {
    keyboardEl.innerHTML = "";
    KEY_ROWS.forEach((row) => {
      const rowEl = document.createElement("div");
      rowEl.className = "krow";
      row.forEach((key) => {
        const btn = document.createElement("button");
        btn.type = "button";
        btn.className = "key" + (key.length > 1 ? " wide" : "");
        btn.textContent = key === "back" ? "⌫" : key === "enter" ? "Enter" : key;
        if (keyStatus[key]) btn.classList.add(keyStatus[key]);
        btn.addEventListener("click", () => pressKey(key));
        rowEl.appendChild(btn);
      });
      keyboardEl.appendChild(rowEl);
    });
  }

  function pressKey(key) {
    if (waitingForStart || paused || finished) return;
    if (key === "enter") return submitGuess();
    if (key === "back") {
      currentGuess = currentGuess.slice(0, -1);
      renderBoard();
      return;
    }
    if (/^[a-z]$/.test(key) && currentGuess.length < WORD_LEN) {
      currentGuess += key;
      renderBoard();
    }
  }

  function submitGuess() {
    if (currentGuess.length < WORD_LEN) {
      setMessage("Not enough letters", 1200);
      return;
    }
    if (!GUESS_SET.has(currentGuess)) {
      setMessage("Not in word list", 1200);
      return;
    }
    const statuses = evaluate(currentGuess, answer);
    updateKeyStatus(currentGuess, statuses);
    guesses.push({ word: currentGuess, statuses });
    const won = currentGuess === answer;
    currentGuess = "";
    renderBoard();
    renderKeyboard();

    if (won) {
      finish("win");
    } else if (guesses.length >= MAX_GUESSES) {
      finish("loss");
    }
  }

  // Score per plan section 7: (7 - guesses) * 150 on a win, 0 on a loss.
  // No "play again": this is a once-a-day puzzle (plan section 7 notes),
  // so there's no in-game restart UI at all.
  function finish(outcome) {
    finished = true;
    if (!gameOverReported) {
      gameOverReported = true;
      const score = outcome === "win" ? (7 - guesses.length) * 150 : 0;
      AlphaGo.gameOver(score, { meta: { guesses: guesses.length, outcome: outcome } });
    }
    setMessage(outcome === "win"
      ? "Solved in " + guesses.length + "! Come back tomorrow."
      : "The word was " + answer.toUpperCase() + ". Come back tomorrow.");
  }

  window.addEventListener("keydown", (e) => {
    const k = e.key.toLowerCase();
    if (k === "enter") { pressKey("enter"); return; }
    if (k === "backspace") { pressKey("back"); return; }
    if (/^[a-z]$/.test(k)) pressKey(k);
  });

  function beginRun(seedRaw) {
    waitingForStart = false;
    paused = false;
    finished = false;
    gameOverReported = false;
    guesses = [];
    currentGuess = "";
    keyStatus = {};

    const n = Number(seedRaw);
    let idx;
    if (Number.isFinite(n)) {
      idx = ((Math.trunc(n) % ANSWERS.length) + ANSWERS.length) % ANSWERS.length;
    } else {
      // No seed from the host (e.g. local test-host without one set) —
      // pick randomly. This is practice mode, not a real daily puzzle:
      // the host/backend is the only legitimate source of the day's word
      // (plan section 7 notes — never the player's device clock either).
      idx = Math.floor(Math.random() * ANSWERS.length);
    }
    answer = ANSWERS[idx];

    hideWaiting();
    setMessage("");
    renderBoard();
    renderKeyboard();
  }

  window.addEventListener("alphago:start", (e) => beginRun(e.detail && e.detail.seed));
  window.addEventListener("alphago:pause", () => { paused = true; });
  window.addEventListener("alphago:resume", () => { paused = false; });

  renderBoard();
  renderKeyboard();
  AlphaGo.ready();
})();
