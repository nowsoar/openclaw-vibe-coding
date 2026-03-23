# HarnessKit

**Local AI Harness engineering toolkit** — manage AI Agent runtimes like code.

> `coding agent = AI model(s) + harness`

HarnessKit provides a CLI to create, version, and manage the "OS layer" of your AI Agents: prompts, schemas, context templates, rules, skills, harnesses, and blueprints — all stored locally, git-trackable, and composable.

---

## Installation

Requires Python 3.10+.

```bash
pip install harness-kit
```

Or install from source:

```bash
git clone <repo>
cd harnesskit
pip install -e .
```

---

## Quick Start

### Initialize a project

Run in any directory to set up the `.harness/` workspace:

```bash
harnesskit init
```

This creates:

```
.harness/
├── config.yaml         # default model, API key ref, log level
├── prompts/
├── schemas/
├── contexts/
├── rules/
├── skills/
├── harnesses/
├── agents/
├── logs/
├── evals/
└── improvements/
```

Running `harnesskit init` a second time in the same directory prints a warning and exits cleanly — it will **not** overwrite existing configuration.

### Default `config.yaml`

```yaml
default_model: gpt-4o
api_key: ${OPENAI_API_KEY}
log_level: INFO
```

Edit `.harness/config.yaml` to change the default model, point to a different API key environment variable, or adjust the log level.

---

## Development

```bash
pip install -e ".[dev]"
pytest
```

---

## Roadmap

See [ROADMAP.md](ROADMAP.md) for the full 8-phase development plan.
