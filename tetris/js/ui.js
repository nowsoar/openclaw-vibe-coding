const UI = (() => {
  // ─── Sound ──────────────────────────────────────────────────────────────────

  let audioCtx = null;
  let soundEnabled = true;

  function getCtx() {
    if (!audioCtx) audioCtx = new (window.AudioContext || window.webkitAudioContext)();
    return audioCtx;
  }

  function tone(freq, dur, type = 'square', vol = 0.12, delay = 0) {
    if (!soundEnabled) return;
    try {
      const ctx  = getCtx();
      const osc  = ctx.createOscillator();
      const gain = ctx.createGain();
      osc.connect(gain); gain.connect(ctx.destination);
      osc.type = type;
      osc.frequency.setValueAtTime(freq, ctx.currentTime + delay);
      gain.gain.setValueAtTime(vol, ctx.currentTime + delay);
      gain.gain.exponentialRampToValueAtTime(0.001, ctx.currentTime + delay + dur);
      osc.start(ctx.currentTime + delay);
      osc.stop(ctx.currentTime + delay + dur + 0.05);
    } catch (e) {}
  }

  const SFX = {
    move()     { tone(220, 0.05, 'square',   0.07); },
    rotate()   { tone(330, 0.07, 'square',   0.10); },
    lock()     { tone(150, 0.12, 'sawtooth', 0.12); },
    hardDrop() { tone(80, 0.14, 'sawtooth', 0.20); tone(130, 0.10, 'sawtooth', 0.15, 0.04); },
    levelUp()  { [523,659,784,1046,1318].forEach((f,i) => tone(f, 0.14, 'square', 0.16, i*0.08)); },
    gameOver() { [523,415,330,262].forEach((f,i) => tone(f, 0.22, 'sawtooth', 0.18, i*0.14)); },
    clear(n)   { [523,659,784,1046].slice(0,n).forEach((f,i) => tone(f, 0.12, 'square', 0.15, i*0.06)); },
    combo(n)   { if (n < 2) return; const f = Math.min(440 * Math.pow(2,(n-1)*0.5), 1800); tone(f, 0.10, 'square', 0.15); },
  };

  // ─── Touch controls ─────────────────────────────────────────────────────────

  let txStart = 0, tyStart = 0, txLast = 0;
  const T_THRESH = 28;

  function onTouchStart(e) {
    const t = e.touches[0];
    txStart = txLast = t.clientX;
    tyStart = t.clientY;
  }

  function onTouchMove(e) {
    if (!Game.isRunning() || Game.isPaused()) return;
    const t = e.touches[0];
    const dx = t.clientX - txLast;
    if (Math.abs(dx) >= T_THRESH) {
      if (dx > 0) Game.moveRight(); else Game.moveLeft();
      SFX.move();
      txLast = t.clientX;
    }
  }

  function onTouchEnd(e) {
    if (!Game.isRunning() || Game.isPaused()) return;
    const t = e.changedTouches[0];
    const dx = t.clientX - txStart;
    const dy = t.clientY - tyStart;
    if (Math.abs(dy) > Math.abs(dx)) {
      if (dy < -T_THRESH) { Game.rotatePiece(); SFX.rotate(); }
      else if (dy > T_THRESH * 2) { Game.hardDrop(); SFX.hardDrop(); }
    }
  }

  // ─── Combo display ──────────────────────────────────────────────────────────

  let comboTimer = null;

  function showCombo(n, count, bonus, levelUp) {
    SFX.clear(n);
    if (count >= 2) SFX.combo(count);
    if (levelUp)    SFX.levelUp();

    const el = document.getElementById('combo-display');
    if (!el) return;
    if (count >= 2) {
      el.textContent = `COMBO ×${count}  +${bonus}`;
      el.classList.add('visible');
      clearTimeout(comboTimer);
      comboTimer = setTimeout(() => el.classList.remove('visible'), 1400);
    } else {
      el.classList.remove('visible');
    }
  }

  // ─── Stats / UI helpers ──────────────────────────────────────────────────────

  function fmtTime(ms) {
    const s = Math.floor(ms / 1000);
    const m = Math.floor(s / 60);
    const h = Math.floor(m / 60);
    if (h > 0) return `${h}h ${m % 60}m`;
    if (m > 0) return `${m}m ${s % 60}s`;
    return `${s}s`;
  }

  function refreshStats() {
    const el = document.getElementById('high-score');
    const te = document.getElementById('total-time');
    if (el) el.textContent = Storage.getHighScore().toLocaleString();
    if (te) te.textContent = fmtTime(Storage.getTotalTime());
  }

  function setScore({ score, level, lines }) {
    document.getElementById('score').textContent = score.toLocaleString();
    document.getElementById('level').textContent = level;
    document.getElementById('lines').textContent = lines;
  }

  function setOverlay(html) {
    const ov = document.getElementById('overlay');
    ov.innerHTML = html;
    ov.style.display = 'flex';
  }

  function hideOverlay() {
    document.getElementById('overlay').style.display = 'none';
  }

  function setPauseBtn(paused) {
    const pb = document.getElementById('pauseBtn');
    if (pb) pb.textContent = paused ? 'RESUME' : 'PAUSE';
  }

  // ─── Keyboard ───────────────────────────────────────────────────────────────

  function handleKey(e) {
    const running = Game.isRunning();
    const paused  = Game.isPaused();

    if (!running || paused) {
      if (e.code === 'Space') {
        e.preventDefault();
        if (running) { Game.resume(); return; }
        // If a save exists, Space resumes rather than wiping it
        if (Game.hasSaved()) { resumeSaved(); } else { newGame(); }
        return;
      }
      if (e.code === 'KeyP' && paused) { e.preventDefault(); Game.resume(); return; }
      return;
    }

    switch (e.code) {
      case 'ArrowLeft':               Game.moveLeft();    SFX.move();    break;
      case 'ArrowRight':              Game.moveRight();   SFX.move();    break;
      case 'ArrowDown':               Game.softDrop();                   break;
      case 'ArrowUp': case 'KeyZ':    Game.rotatePiece(); SFX.rotate();  break;
      case 'Space':                   Game.hardDrop();    SFX.hardDrop();break;
      case 'KeyP':                    Game.togglePause();                break;
      default: return;
    }
    e.preventDefault();
  }

  // ─── Public actions ─────────────────────────────────────────────────────────

  function newGame() {
    Storage.clearProgress();
    Game.start(false);
    hideOverlay();
    const pb = document.getElementById('pauseBtn');
    pb.disabled = false;
    setPauseBtn(false);
    refreshStats();
  }

  function resumeSaved() {
    Game.start(true);
    hideOverlay();
    const pb = document.getElementById('pauseBtn');
    pb.disabled = false;
    setPauseBtn(false);
    refreshStats();
  }

  function toggleSound() {
    soundEnabled = !soundEnabled;
    const btn = document.getElementById('soundBtn');
    if (btn) btn.textContent = soundEnabled ? 'SFX ON' : 'SFX OFF';
  }

  // ─── Init ───────────────────────────────────────────────────────────────────

  function init() {
    Game.on('scoreUpdate', setScore);

    Game.on('combo', (n, count, bonus, levelUp) => {
      showCombo(n, count, bonus, levelUp);
    });

    Game.on('lock', () => SFX.lock());

    Game.on('pauseChange', (paused) => {
      setPauseBtn(paused);
      if (paused) {
        setOverlay(
          '<h2>PAUSED</h2>' +
          '<div class="ov-divider"></div>' +
          '<div class="ov-sub">PRESS P OR RESUME</div>'
        );
      } else {
        hideOverlay();
      }
    });

    Game.on('gameEnd', ({ score, level, lines, isNewHigh, totalTime }) => {
      SFX.gameOver();
      refreshStats();
      document.getElementById('pauseBtn').disabled = true;
      setOverlay(
        `<h2>GAME OVER</h2>` +
        `<div class="ov-divider"></div>` +
        `<div class="ov-score">SCORE: ${score.toLocaleString()}</div>` +
        (isNewHigh ? `<div class="ov-new-high">✦ NEW BEST ✦</div>` : '') +
        `<div class="ov-sub">PRESS START OR SPACE</div>`
      );
    });

    // Keyboard
    document.addEventListener('keydown', handleKey);

    // Touch
    const board = document.getElementById('board');
    board.addEventListener('touchstart', onTouchStart, { passive: true });
    board.addEventListener('touchmove',  onTouchMove,  { passive: true });
    board.addEventListener('touchend',   onTouchEnd,   { passive: true });

    // Initial stats
    refreshStats();

    // Welcome overlay — offer resume if save exists
    if (Game.hasSaved()) {
      setOverlay(
        `<h2>TETRIS</h2>` +
        `<div class="ov-divider"></div>` +
        `<div class="ov-sub" style="margin-bottom:12px">SAVED GAME FOUND</div>` +
        `<div style="display:flex;gap:10px">` +
        `  <button class="btn btn-start"  style="width:auto;padding:10px 18px" onclick="UI.resumeSaved()">RESUME</button>` +
        `  <button class="btn btn-danger" style="width:auto;padding:10px 18px" onclick="UI.newGame()">NEW GAME</button>` +
        `</div>` +
        `<div class="ov-sub" style="margin-top:8px">SPACE TO RESUME</div>`
      );
    } else {
      setOverlay(
        `<h2>TETRIS</h2>` +
        `<div class="ov-divider"></div>` +
        `<div class="ov-sub">PRESS START OR SPACE</div>`
      );
    }
  }

  return { init, newGame, resumeSaved, toggleSound, togglePause: () => Game.togglePause() };
})();

window.addEventListener('DOMContentLoaded', () => {
  Game.init(
    document.getElementById('board'),
    document.getElementById('next')
  );
  UI.init();
});
