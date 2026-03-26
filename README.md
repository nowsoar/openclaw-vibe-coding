# openclaw-vibe-coding

<p align="center">
  <b>A collection of projects built with AI-assisted vibe coding, powered by OpenClaw.</b>
</p>

<p align="center">
  <a href="README.md">English</a> · <a href="README_CN.md">中文</a>
</p>

<p align="center">
  <img src="https://img.shields.io/badge/built%20with-OpenClaw-blue" alt="Built with OpenClaw">
  <img src="https://img.shields.io/badge/vibe-coding-purple" alt="Vibe Coding">
  <img src="https://img.shields.io/badge/license-MIT-green" alt="MIT">
  <img src="https://img.shields.io/badge/projects-4-orange" alt="4 Projects">
</p>

---

## What is this?

This repository is a living lab for **vibe coding** — the practice of building software by describing intent to an AI assistant and iterating rapidly through conversation rather than writing every line by hand.

Every project here was designed, implemented, tested, and shipped through back-and-forth dialogue with [OpenClaw](https://openclaw.ai), a personal AI assistant that can read files, run shell commands, call APIs, and push code.

The goal is not to show off finished products. It's to explore what AI-assisted development looks like in practice: what works, what breaks, how fast you can go, and how far you can reach.

---

## Projects

| Project | Description | Stack | Status |
|---------|-------------|-------|--------|
| [🔧 HarnessKit](#-harnesskit) | Local AI Harness engineering toolkit — version and manage AI Agent runtimes like code | Python, Typer, Rich, FastAPI, Textual | ✅ 8 phases complete |
| [🕹️ Tetris](#%EF%B8%8F-tetris) | Feature-complete browser Tetris — pause/resume, auto-save, touch, combo, Web Audio | Vanilla HTML/CSS/JS | ✅ Complete |
| [🔍 JSON Diff Tool](#-json-diff-tool) | Lightweight CLI to compare two JSON files with colorized output | Python (stdlib only) | ✅ Complete |
| [📝 PromptVault](#-promptvault) | Git for Prompts — CLI-first prompt version management system | Python | 🚧 In progress |

---

## 🔧 HarnessKit

> `projects/harnesskit/`

**Manage AI Agent runtimes like code.**

```
coding agent = AI model(s) + harness
```

HarnessKit is a full-featured CLI toolkit for versioning, composing, and operating the "OS layer" of your AI Agents: prompts, schemas, rules, context templates, skills, harnesses, blueprints, and agents — all local-first and git-trackable.

**Highlights:**
- Versioned prompt / schema / context / rule assets with `diff` and `history`
- Skills: runnable units that assemble prompts, call LLMs, and enforce rules
- Harness + Agent: multi-skill configs with conversation memory and interactive REPL
- Blueprint: hybrid shell + LLM workflow pipelines
- Eval engine: A/B compare, multi-model benchmark, CI mode with JUnit XML
- Full observability: call logs, cost tracking, stats dashboard, improvement flywheel
- TUI (Textual): Skill browser, Prompt Diff visualizer, live log stream
- Web Playground: FastAPI + HTMX UI, Prompt Playground, A/B Compare, Eval Dashboard
- MCP Server export: expose Skills as tools for Claude Desktop / Cursor
- Skills Registry: portable `.hsk` packages — install, publish, search

```bash
pip install harness-kit
harnesskit --help
```

**1 728 tests, all passing.** → [README](projects/harnesskit/README.md) · [ROADMAP](projects/harnesskit/ROADMAP.md)

---

## 🕹️ Tetris

> `tetris/`

A feature-complete Tetris built with zero frameworks and zero external assets — just HTML, CSS, and vanilla JS.

**Features:**

| Feature | Details |
|---------|---------|
| ⏸️ Pause / Resume | Fully preserves mid-drop timing — no progress lost |
| 💾 Auto Save | Progress and high score persist in `localStorage` |
| 🔊 Sound Effects | Generated with Web Audio API — no audio files needed |
| ⚡ Combo Bonus | Consecutive clears give bonus points + on-screen flash |
| 📱 Touch Support | Swipe left/right to move, up to rotate, down to hard drop |
| 💥 Hard Drop Flash | White canvas overlay for visual impact |

Open `tetris/index.html` directly in any browser — no server needed.

→ [README](tetris/README.md)

---

## 🔍 JSON Diff Tool

> `projects/2026-03-23-json-diff-tool/`

A lightweight command-line tool to compare two JSON files and display differences in a readable format. Zero dependencies — Python standard library only.

```bash
python3 json_diff.py file_a.json file_b.json --color
```

Detects added, removed, and modified fields recursively through nested objects and arrays. Returns exit code `0` for identical files and `1` for differences — CI-friendly.

→ [README](projects/2026-03-23-json-diff-tool/README.md)

---

## 📝 PromptVault

> `projects/promptvault/`

**Git for Prompts.**

A CLI-first prompt version management system — store, version, diff, template, test, and share prompts the same way you manage code.

```bash
promptvault save my-prompt --tag v1 --desc "Initial version"
promptvault diff my-prompt@v1 my-prompt@v2
promptvault run my-prompt --var language=Python
```

Currently under active development. → [ROADMAP](projects/promptvault/ROADMAP.md)

---

## How it was built

Each project follows the same loop:

1. **Describe intent** — tell OpenClaw what to build in plain language
2. **AI writes code** — OpenClaw spawns a coding agent (Claude Code / Codex) that reads files, writes code, runs tests, and commits
3. **Review & steer** — review output in conversation, give feedback, iterate
4. **Ship** — agent pushes to GitHub when done

No boilerplate setup. No context switching. Just describing what you want and steering toward it.

---

## Repository Structure

```
openclaw-vibe-coding/
├── projects/
│   ├── harnesskit/                      AI Harness toolkit (Python, 8 phases)
│   ├── promptvault/                     Prompt version manager (in progress)
│   └── 2026-03-23-json-diff-tool/       JSON diff CLI
├── tetris/                              Browser Tetris game
└── README.md
```

---

## License

MIT
