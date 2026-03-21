const Game = (() => {
  const COLS = 10, ROWS = 20, SZ = 40;

  const COLORS = [
    null,
    '#00e5ff', // I  cyan
    '#ffd600', // O  yellow
    '#b44fff', // T  purple
    '#00e676', // S  green
    '#ff1744', // Z  red
    '#2979ff', // J  blue
    '#ff6d00', // L  orange
  ];

  const LIGHT = [
    null,
    'rgba(180,255,255,0.35)',
    'rgba(255,255,180,0.35)',
    'rgba(220,180,255,0.35)',
    'rgba(180,255,200,0.35)',
    'rgba(255,180,180,0.35)',
    'rgba(180,200,255,0.35)',
    'rgba(255,220,160,0.35)',
  ];

  const SHAPES = [null,
    [[0,0,0,0],[1,1,1,1],[0,0,0,0],[0,0,0,0]], // I
    [[2,2],[2,2]],                               // O
    [[0,3,0],[3,3,3],[0,0,0]],                   // T
    [[0,4,4],[4,4,0],[0,0,0]],                   // S
    [[5,5,0],[0,5,5],[0,0,0]],                   // Z
    [[6,0,0],[6,6,6],[0,0,0]],                   // J
    [[0,0,7],[7,7,7],[0,0,0]],                   // L
  ];

  // DOM
  let canvas, ctx, nCanvas, nctx;

  // State
  let grid, cur, nxt;
  let score, level, lines;
  let running, paused;
  let dropMs, dropAccum, lastT;
  let raf;

  // Visual effects
  let comboCount = 0;
  let flashAlpha = 0;
  let spawnAlpha = 0;

  // Session timer
  let sessionStart = 0, pauseStart = 0, pauseAccum = 0;

  // Callbacks
  let cbCombo = null, cbScore = null, cbGameEnd = null, cbPause = null, cbLock = null;

  // ─── Helpers ────────────────────────────────────────────────────────────────

  function mkGrid() {
    return Array.from({ length: ROWS }, () => Array(COLS).fill(0));
  }

  function randPiece() {
    const id = (Math.random() * 7 | 0) + 1;
    const shape = SHAPES[id].map(r => [...r]);
    return { id, shape, x: (COLS / 2 | 0) - (shape[0].length / 2 | 0), y: 0 };
  }

  function rotate(s) {
    const R = s.length, C = s[0].length;
    const r = Array.from({ length: C }, () => Array(R).fill(0));
    for (let i = 0; i < R; i++)
      for (let j = 0; j < C; j++)
        r[j][R - 1 - i] = s[i][j];
    return r;
  }

  function ok(p, sh) {
    const s = sh || p.shape;
    for (let r = 0; r < s.length; r++) {
      for (let c = 0; c < s[r].length; c++) {
        if (!s[r][c]) continue;
        const nx = p.x + c, ny = p.y + r;
        if (nx < 0 || nx >= COLS || ny >= ROWS) return false;
        if (ny >= 0 && grid[ny][nx]) return false;
      }
    }
    return true;
  }

  function shadeColor(hex, pct) {
    const n = parseInt(hex.slice(1), 16);
    const r = Math.min(255, Math.max(0, (n >> 16) + pct));
    const g = Math.min(255, Math.max(0, ((n >> 8) & 0xff) + pct));
    const b = Math.min(255, Math.max(0, (n & 0xff) + pct));
    return `rgb(${r},${g},${b})`;
  }

  // ─── Drawing ────────────────────────────────────────────────────────────────

  function blk(c, gx, gy, colorId, sz, alpha) {
    if (!sz) sz = SZ;
    const px = gx * sz, py = gy * sz;
    const col = COLORS[colorId];
    const saved = c.globalAlpha;
    if (alpha !== undefined) c.globalAlpha = Math.min(1, Math.max(0, alpha));

    const grad = c.createLinearGradient(px, py, px + sz, py + sz);
    grad.addColorStop(0, col);
    grad.addColorStop(1, shadeColor(col, -30));
    c.fillStyle = grad;
    c.fillRect(px + 1, py + 1, sz - 2, sz - 2);

    c.fillStyle = LIGHT[colorId] || 'rgba(255,255,255,0.25)';
    c.fillRect(px + 1, py + 1, sz - 2, 5);
    c.fillRect(px + 1, py + 1, 5, sz - 2);

    c.fillStyle = 'rgba(0,0,0,0.3)';
    c.fillRect(px + 1, py + sz - 6, sz - 2, 5);
    c.fillRect(px + sz - 6, py + 1, 5, sz - 2);

    c.strokeStyle = 'rgba(0,0,0,0.4)';
    c.lineWidth = 1;
    c.strokeRect(px + 0.5, py + 0.5, sz - 1, sz - 1);

    c.globalAlpha = saved;
  }

  function drawGhost() {
    const g = { ...cur, shape: cur.shape.map(r => [...r]) };
    while (ok({ ...g, y: g.y + 1 })) g.y++;
    if (g.y === cur.y) return;
    ctx.globalAlpha = 0.15;
    g.shape.forEach((row, r) =>
      row.forEach((v, c) => { if (v) blk(ctx, g.x + c, g.y + r, v, SZ); })
    );
    ctx.globalAlpha = 1;
  }

  function drawBoard() {
    // Background
    ctx.fillStyle = '#06060f';
    ctx.fillRect(0, 0, canvas.width, canvas.height);

    // Grid lines
    ctx.strokeStyle = 'rgba(255,255,255,0.03)';
    ctx.lineWidth = 1;
    for (let r = 0; r <= ROWS; r++) {
      ctx.beginPath(); ctx.moveTo(0, r * SZ); ctx.lineTo(COLS * SZ, r * SZ); ctx.stroke();
    }
    for (let c = 0; c <= COLS; c++) {
      ctx.beginPath(); ctx.moveTo(c * SZ, 0); ctx.lineTo(c * SZ, ROWS * SZ); ctx.stroke();
    }

    // Locked cells
    grid.forEach((row, r) =>
      row.forEach((v, c) => { if (v) blk(ctx, c, r, v, SZ); })
    );

    // Ghost + active piece with spawn animation
    if (cur) {
      drawGhost();
      const alpha = Math.min(1, spawnAlpha);
      cur.shape.forEach((row, r) =>
        row.forEach((v, c) => { if (v) blk(ctx, cur.x + c, cur.y + r, v, SZ, alpha); })
      );
      if (spawnAlpha < 1) spawnAlpha = Math.min(1, spawnAlpha + 0.15);
    }

    // Hard-drop flash overlay
    if (flashAlpha > 0) {
      ctx.fillStyle = `rgba(255,255,255,${flashAlpha})`;
      ctx.fillRect(0, 0, canvas.width, canvas.height);
      flashAlpha = Math.max(0, flashAlpha - 0.07);
    }
  }

  function drawNext() {
    nctx.fillStyle = '#0a0a1e';
    nctx.fillRect(0, 0, nCanvas.width, nCanvas.height);
    if (!nxt) return;
    const NS = 24;
    const s = nxt.shape;
    const ox = Math.floor((nCanvas.width  / NS - s[0].length) / 2);
    const oy = Math.floor((nCanvas.height / NS - s.length) / 2);
    s.forEach((row, r) =>
      row.forEach((v, c) => { if (v) blk(nctx, ox + c, oy + r, v, NS); })
    );
  }

  // ─── Game Logic ─────────────────────────────────────────────────────────────

  function lock() {
    let above = false;
    for (let r = 0; r < cur.shape.length; r++) {
      for (let c = 0; c < cur.shape[r].length; c++) {
        if (!cur.shape[r][c]) continue;
        const ny = cur.y + r;
        if (ny < 0) { above = true; continue; }
        grid[ny][cur.x + c] = cur.shape[r][c];
      }
    }
    if (cbLock) cbLock();
    if (above) { endGame(); return; }
    sweep();
    cur = nxt;
    spawnAlpha = 0;
    nxt = randPiece();
    if (!ok(cur)) { endGame(); return; }
    drawNext();
    if (cbScore) cbScore({ score, level, lines });
    saveProgress();
  }

  function sweep() {
    let n = 0;
    for (let r = ROWS - 1; r >= 0; r--) {
      if (grid[r].every(v => v)) {
        grid.splice(r, 1);
        grid.unshift(Array(COLS).fill(0));
        n++; r++;
      }
    }

    if (n === 0) { comboCount = 0; return; }

    comboCount++;
    const pts = [0, 100, 300, 500, 800];
    const base   = (pts[n] || 800) * level;
    const bonus  = comboCount > 1 ? (comboCount - 1) * 50 * level : 0;
    score += base + bonus;
    lines += n;

    const oldLevel = level;
    level  = Math.floor(lines / 10) + 1;
    dropMs = Math.max(60, 1000 - (level - 1) * 90);

    if (cbCombo) cbCombo(n, comboCount, bonus, level > oldLevel);
    if (cbScore) cbScore({ score, level, lines });
  }

  function saveProgress() {
    Storage.saveProgress({
      grid:  grid.map(r => [...r]),
      cur:   { ...cur, shape: cur.shape.map(r => [...r]) },
      nxt:   { ...nxt, shape: nxt.shape.map(r => [...r]) },
      score, level, lines, dropMs, comboCount,
    });
  }

  // ─── Game Loop ──────────────────────────────────────────────────────────────

  function loop(ts) {
    if (!running || paused) return;

    // lastT === 0 means "first frame after start/resume — sync clock without advancing"
    if (lastT > 0) {
      // Cap delta to 500 ms so a backgrounded tab doesn't cause a burst of drops
      dropAccum += Math.min(ts - lastT, 500);
    }
    lastT = ts;

    while (dropAccum >= dropMs) {
      dropAccum -= dropMs;
      if (ok({ ...cur, y: cur.y + 1 })) {
        cur.y++;
      } else {
        lock();
        if (!running) return;
        // Reset accumulator so the newly spawned piece gets a full interval
        dropAccum = 0;
        break;
      }
    }

    drawBoard();
    raf = requestAnimationFrame(loop);
  }

  // ─── Public API ─────────────────────────────────────────────────────────────

  function init(boardCanvas, nextCanvas) {
    canvas = boardCanvas; ctx = canvas.getContext('2d');
    nCanvas = nextCanvas; nctx = nCanvas.getContext('2d');
    ctx.fillStyle = '#06060f';
    ctx.fillRect(0, 0, canvas.width, canvas.height);
    nctx.fillStyle = '#0a0a1e';
    nctx.fillRect(0, 0, nCanvas.width, nCanvas.height);
    // Save progress when user closes or navigates away
    window.addEventListener('beforeunload', () => {
      if (running && !paused) saveProgress();
    });
  }

  function start(fromSave) {
    if (raf) cancelAnimationFrame(raf);

    if (fromSave) {
      const saved = Storage.loadProgress();
      if (saved) {
        grid       = saved.grid;
        cur        = saved.cur;
        nxt        = saved.nxt;
        score      = saved.score;
        level      = saved.level;
        lines      = saved.lines;
        dropMs     = saved.dropMs;
        comboCount = saved.comboCount || 0;
        spawnAlpha = 1;
        running = true; paused = false;
        dropAccum = 0; lastT = 0;
        sessionStart = performance.now(); pauseAccum = 0;
        if (cbScore) cbScore({ score, level, lines });
        drawNext();
        raf = requestAnimationFrame(loop);
        return true;
      }
    }

    // Fresh start
    grid = mkGrid();
    score = 0; level = 1; lines = 0; dropMs = 1000;
    dropAccum = 0; lastT = 0; comboCount = 0; flashAlpha = 0;
    cur = randPiece(); nxt = randPiece(); spawnAlpha = 0;
    running = true; paused = false;
    sessionStart = performance.now(); pauseAccum = 0;
    if (cbScore) cbScore({ score, level, lines });
    drawNext();
    raf = requestAnimationFrame(loop);
    return false;
  }

  function pause() {
    if (!running || paused) return;
    paused = true;
    pauseStart = performance.now();
    cancelAnimationFrame(raf);
    saveProgress();
    if (cbPause) cbPause(true);
  }

  function resume() {
    if (!running || !paused) return;
    paused = false;
    pauseAccum += performance.now() - pauseStart;
    lastT = 0; // reset clock without losing dropAccum
    raf = requestAnimationFrame(loop);
    if (cbPause) cbPause(false);
  }

  function togglePause() { paused ? resume() : pause(); }

  function endGame() {
    running = false;
    if (raf) cancelAnimationFrame(raf);
    const sessionMs = performance.now() - sessionStart - pauseAccum;
    const totalTime  = Storage.addTotalTime(sessionMs);
    const isNewHigh  = Storage.setHighScore(score);
    Storage.clearProgress();
    if (cbGameEnd) cbGameEnd({ score, level, lines, isNewHigh, totalTime });
  }

  // ─── Input Actions ──────────────────────────────────────────────────────────

  function moveLeft()  { if (!running || paused) return; if (ok({ ...cur, x: cur.x - 1 })) cur.x--;  drawBoard(); }
  function moveRight() { if (!running || paused) return; if (ok({ ...cur, x: cur.x + 1 })) cur.x++;  drawBoard(); }

  function softDrop() {
    if (!running || paused) return;
    if (ok({ ...cur, y: cur.y + 1 })) {
      cur.y++; score += 1;
      dropAccum = 0; // reset drop timer so soft-drop doesn't double-trigger
    } else {
      lock(); if (!running) return;
      dropAccum = 0; // give new piece a full interval after a soft-drop lock
    }
    if (cbScore) cbScore({ score, level, lines });
    drawBoard();
  }

  function rotatePiece() {
    if (!running || paused) return;
    const rot = rotate(cur.shape);
    if (ok({ ...cur, shape: rot })) {
      cur.shape = rot;
    } else {
      // Wall kicks: try horizontal offsets, then floor kick (dy = -1)
      let kicked = false;
      for (const k of [1, -1, 2, -2]) {
        if (ok({ ...cur, x: cur.x + k, shape: rot })) {
          cur.x += k; cur.shape = rot; kicked = true; break;
        }
      }
      if (!kicked && ok({ ...cur, y: cur.y - 1, shape: rot })) {
        cur.y--; cur.shape = rot;
      }
    }
    drawBoard();
  }

  function hardDrop() {
    if (!running || paused) return;
    let dropped = 0;
    while (ok({ ...cur, y: cur.y + 1 })) { cur.y++; dropped++; }
    score += dropped * 2;
    flashAlpha = 0.65;
    if (cbScore) cbScore({ score, level, lines });
    lock();
    if (!running) return;
    dropAccum = 0; // give new piece a clean interval after hard drop
    drawBoard();
  }

  return {
    init, start, togglePause, pause, resume,
    moveLeft, moveRight, softDrop, rotatePiece, hardDrop,
    isRunning: () => running,
    isPaused:  () => paused,
    hasSaved:  () => !!Storage.loadProgress(),
    on(event, cb) {
      if      (event === 'combo')       cbCombo   = cb;
      else if (event === 'scoreUpdate') cbScore   = cb;
      else if (event === 'gameEnd')     cbGameEnd = cb;
      else if (event === 'pauseChange') cbPause   = cb;
      else if (event === 'lock')        cbLock    = cb;
    },
  };
})();
