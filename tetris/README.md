# Tetris 俄罗斯方块

A feature-complete browser Tetris built with vanilla HTML/CSS/JS — no frameworks, no external assets.

## Project Structure

```
tetris/
├── index.html          Main page
├── css/
│   └── style.css       All styles
├── js/
│   ├── storage.js      localStorage — high score, total time, progress save/load
│   ├── game.js         Core engine — game loop, physics, rendering, effects
│   └── ui.js           UI layer — keyboard, touch, sound, combo display
└── README.md
```

## Features

| Feature | Details |
|---|---|
| Pause / Resume | Fully preserves mid-drop timing — no progress lost |
| Auto Save | Progress saved to `localStorage` after every piece lock; restored on next visit |
| High Score | Persisted across sessions |
| Total Play Time | Accumulated across all sessions, pause time excluded |
| Combo Bonus | Consecutive line clears give `(combo-1) × 50 × level` bonus + on-screen flash |
| Sound Effects | Web Audio API — move, rotate, lock, clear, hard drop, level up, game over |
| Hard Drop Flash | White canvas overlay that quickly fades for visual impact |
| Piece Spawn Animation | New pieces fade in from α=0 over ~7 frames |
| Ghost Piece | Transparent landing preview |
| Mobile Touch | Swipe left/right = move, swipe up = rotate, swipe down = hard drop |

## Controls

| Key | Action |
|---|---|
| `← →` | Move |
| `↑` / `Z` | Rotate (with wall-kick) |
| `↓` | Soft drop (+1 pt) |
| `Space` | Hard drop (+2 pt/row) |
| `P` | Pause / Resume |

**Touch:** swipe horizontally to move (continuous), swipe up to rotate, swipe down to hard drop.

## Scoring

| Lines | Base points |
|---|---|
| 1 | 100 × level |
| 2 | 300 × level |
| 3 | 500 × level |
| 4 | 800 × level |

Combo bonus: `(combo − 1) × 50 × level` for consecutive clears.
Soft drop: `+1` per row. Hard drop: `+2` per row.

## Running

Open `tetris/index.html` directly in a browser — no build step required.
