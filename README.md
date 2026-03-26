# openclaw-vibe-coding

<p align="center">
  <b>A collection of projects built with AI-assisted vibe coding, powered by OpenClaw.</b><br>
  <b>用 OpenClaw AI 助手 vibe coding 构建的项目合集。</b>
</p>

<p align="center">
  <img src="https://img.shields.io/badge/built%20with-OpenClaw-blue" alt="Built with OpenClaw">
  <img src="https://img.shields.io/badge/vibe-coding-purple" alt="Vibe Coding">
  <img src="https://img.shields.io/badge/license-MIT-green" alt="MIT">
  <img src="https://img.shields.io/badge/projects-4-orange" alt="4 Projects">
</p>

---

## English

### What is this?

This repository is a living lab for **vibe coding** — the practice of building software by describing intent to an AI assistant and iterating rapidly through conversation rather than writing every line by hand.

Every project here was designed, implemented, tested, and shipped through back-and-forth dialogue with [OpenClaw](https://openclaw.ai), a personal AI assistant that can read files, run shell commands, call APIs, and push code.

The goal is not to show off finished products. It's to explore what AI-assisted development looks like in practice: what works, what breaks, how fast you can go, and how far you can reach.

---

### Projects

| Project | Description | Stack | Status |
|---------|-------------|-------|--------|
| [🔧 HarnessKit](#-harnesskit) | Local AI Harness engineering toolkit — version and manage AI Agent runtimes like code | Python, Typer, Rich, FastAPI, Textual | ✅ 8 phases complete |
| [🕹️ Tetris](#%EF%B8%8F-tetris) | Feature-complete browser Tetris — pause/resume, auto-save, touch, combo, Web Audio | Vanilla HTML/CSS/JS | ✅ Complete |
| [🔍 JSON Diff Tool](#-json-diff-tool) | Lightweight CLI to compare two JSON files with colorized output | Python (stdlib only) | ✅ Complete |
| [📝 PromptVault](#-promptvault) | Git for Prompts — CLI-first prompt version management system | Python | 🚧 In progress |

---

### 🔧 HarnessKit

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

### 🕹️ Tetris

> `tetris/`

A feature-complete Tetris built with zero frameworks and zero external assets — just HTML, CSS, and vanilla JS.

**Features:**
- ⏸️ Pause / Resume — preserves mid-drop timing exactly
- 💾 Auto Save — progress and high score persist in `localStorage`
- 🔊 Sound Effects — generated with Web Audio API (no files needed)
- ⚡ Combo Bonus — consecutive clears give bonus points + on-screen flash
- 📱 Touch Support — swipe left/right/up/down to play on mobile
- 💥 Hard Drop Flash — white canvas overlay for visual impact

Open `tetris/index.html` directly in any browser — no server needed.

→ [README](tetris/README.md)

---

### 🔍 JSON Diff Tool

> `projects/2026-03-23-json-diff-tool/`

A lightweight command-line tool to compare two JSON files and display differences in a readable format. Zero dependencies — Python standard library only.

```bash
python3 json_diff.py file_a.json file_b.json --color
```

Detects added, removed, and modified fields recursively through nested objects and arrays. Returns exit code `0` for identical files and `1` for differences — CI-friendly.

→ [README](projects/2026-03-23-json-diff-tool/README.md)

---

### 📝 PromptVault

> `projects/promptvault/`

**Git for Prompts.**

A CLI-first prompt version management system — store, version, diff, template, test, and share prompts the same way you manage code.

```bash
promptvault save my-prompt --tag v1 --desc "Initial version"
promptvault diff my-prompt@v1 my-prompt@v2
promptvault run my-prompt --var language=Python
```

Currently under active development.

→ [ROADMAP](projects/promptvault/ROADMAP.md)

---

### How it was built

Each project follows the same loop:

1. **Describe intent** — tell OpenClaw what to build in plain language
2. **AI writes code** — OpenClaw spawns a coding agent (Claude Code / Codex) that reads files, writes code, runs tests, and commits
3. **Review & steer** — review output in conversation, give feedback, iterate
4. **Ship** — agent pushes to GitHub when done

No boilerplate setup. No context switching. Just describing what you want and steering toward it.

---

### Repository Structure

```
openclaw-vibe-coding/
├── projects/
│   ├── harnesskit/              AI Harness toolkit (Python, 8 phases)
│   ├── promptvault/             Prompt version manager (in progress)
│   └── 2026-03-23-json-diff-tool/   JSON diff CLI
├── tetris/                      Browser Tetris game
└── README.md
```

---

### License

MIT

---
---

## 中文

### 这是什么？

这个仓库是 **vibe coding** 的实践场——通过向 AI 助手描述意图、在对话中快速迭代，来构建软件，而不是手写每一行代码。

这里的每个项目都是通过与 [OpenClaw](https://openclaw.ai) 的对话设计、实现、测试和交付的。OpenClaw 是一个个人 AI 助手，能读写文件、执行 shell 命令、调用 API、推送代码。

目标不是展示完美的产品，而是探索 AI 辅助开发的实际样子：什么能用，什么会出问题，能跑多快，能走多远。

---

### 项目列表

| 项目 | 描述 | 技术栈 | 状态 |
|------|------|--------|------|
| [🔧 HarnessKit](#-harnesskit-1) | 本地 AI Harness 工程工具箱——像管理代码一样管理 AI Agent 运行时 | Python, Typer, Rich, FastAPI, Textual | ✅ 8 个阶段全部完成 |
| [🕹️ Tetris](#%EF%B8%8F-tetris-1) | 功能完整的浏览器俄罗斯方块——暂停恢复、自动存档、触控、连击、Web Audio | 原生 HTML/CSS/JS | ✅ 完成 |
| [🔍 JSON Diff Tool](#-json-diff-tool-1) | 轻量级命令行 JSON 对比工具，支持彩色输出 | Python（仅标准库） | ✅ 完成 |
| [📝 PromptVault](#-promptvault-1) | Prompt 的 Git——CLI 优先的 Prompt 版本管理系统 | Python | 🚧 开发中 |

---

### 🔧 HarnessKit

> `projects/harnesskit/`

**像管理代码一样管理 AI Agent 运行时。**

```
coding agent = AI model(s) + harness
```

HarnessKit 是一个功能完整的 CLI 工具箱，用于版本化、组合和运维 AI Agent 的「操作系统层」：提示词、Schema、规则、上下文模板、Skill、Harness、Blueprint、Agent——全部本地存储，可用 Git 追踪。

**核心功能：**
- 带 `diff` 和 `history` 的版本化 prompt / schema / context / rule 资产管理
- Skill：组装提示词、调用 LLM、执行规则检查的可运行单元
- Harness + Agent：多 Skill 配置 + 会话记忆 + 交互式 REPL
- Blueprint：Shell 命令 + LLM 调用的混合工作流编排
- 评估引擎：A/B 对比、多模型 Benchmark、CI 模式（JUnit XML）
- 完整可观测性：调用日志、成本追踪、统计仪表盘、改进飞轮
- TUI（Textual）：Skill 浏览器、Prompt Diff 可视化、实时日志流
- Web Playground：FastAPI + HTMX UI，包含 Prompt 试验场、A/B 对比、Eval 仪表盘
- MCP Server 导出：将 Skill 暴露为 Claude Desktop / Cursor 的 MCP Tools
- Skills Registry：`.hsk` 可移植包——安装、发布、搜索

```bash
pip install harness-kit
harnesskit --help
```

**1 728 个测试，全部通过。** → [README](projects/harnesskit/README.md) · [ROADMAP](projects/harnesskit/ROADMAP.md)

---

### 🕹️ Tetris 俄罗斯方块

> `tetris/`

零框架、零外部依赖的功能完整俄罗斯方块——只用原生 HTML、CSS 和 JS。

**功能特性：**
- ⏸️ 暂停 / 恢复——精确保留方块下落进度
- 💾 自动存档——进度和最高分通过 `localStorage` 持久化
- 🔊 音效——用 Web Audio API 生成，无需任何音频文件
- ⚡ 连击奖励——连续消行有额外分数加成 + 屏幕特效
- 📱 触控支持——左右滑动移动，上滑旋转，下滑硬降
- 💥 硬降闪光——视觉冲击效果

直接在浏览器中打开 `tetris/index.html` 即可游玩，无需服务器。

→ [README](tetris/README.md)

---

### 🔍 JSON Diff Tool

> `projects/2026-03-23-json-diff-tool/`

轻量级命令行工具，用于对比两个 JSON 文件并以可读格式展示差异。零依赖，仅用 Python 标准库。

```bash
python3 json_diff.py file_a.json file_b.json --color
```

递归检测嵌套对象和数组中的新增、删除、修改字段。文件相同时退出码为 `0`，有差异时为 `1`，对 CI 流水线友好。

→ [README](projects/2026-03-23-json-diff-tool/README.md)

---

### 📝 PromptVault

> `projects/promptvault/`

**Prompt 的 Git。**

CLI 优先的 Prompt 版本管理系统——像管理代码一样存储、版本化、对比、模板化、测试和分享 Prompt。

```bash
promptvault save my-prompt --tag v1 --desc "初始版本"
promptvault diff my-prompt@v1 my-prompt@v2
promptvault run my-prompt --var language=Python
```

目前正在积极开发中。

→ [ROADMAP](projects/promptvault/ROADMAP.md)

---

### 构建方式

每个项目都遵循同一个循环：

1. **描述意图**——用自然语言告诉 OpenClaw 想构建什么
2. **AI 写代码**——OpenClaw 启动一个编程 Agent（Claude Code / Codex），它会读文件、写代码、跑测试、提交
3. **审查与引导**——在对话中查看输出、给反馈、迭代
4. **交付**——Agent 完成后推送到 GitHub

无需手动搭建脚手架，无需上下文切换。只需描述你想要什么，然后朝着目标不断引导。

---

### 仓库结构

```
openclaw-vibe-coding/
├── projects/
│   ├── harnesskit/              AI Harness 工具箱（Python，8 个阶段）
│   ├── promptvault/             Prompt 版本管理器（开发中）
│   └── 2026-03-23-json-diff-tool/   JSON 对比 CLI
├── tetris/                      浏览器俄罗斯方块
└── README.md
```

---

### 许可证

MIT
