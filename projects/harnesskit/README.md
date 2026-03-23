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

## Prompt Asset Management

Prompts are versioned YAML files stored under `.harness/prompts/{name}/`.
Each save auto-increments the patch version (`v0.0.1 → v0.0.2 → …`).

### Save a prompt

```bash
# From a string
harnesskit prompt save code-reviewer --content "You are a senior {{language}} engineer..."

# From a file
harnesskit prompt save code-reviewer --file ./reviewer.txt

# From stdin
cat reviewer.txt | harnesskit prompt save code-reviewer

# With metadata
harnesskit prompt save code-reviewer \
  --content "You are a senior {{language}} engineer..." \
  --description "Senior code review engineer" \
  --tags "code,review,security" \
  --changelog "Initial version"
```

### Show a prompt

```bash
harnesskit prompt show code-reviewer           # latest version
harnesskit prompt show code-reviewer@v0.0.1   # specific version
```

### List all prompts

```bash
harnesskit prompt list
```

### Version history

```bash
harnesskit prompt history code-reviewer
```

### Diff two versions

```bash
harnesskit prompt diff code-reviewer@v0.0.1 code-reviewer@v0.0.2
```

### Delete a prompt

```bash
harnesskit prompt delete code-reviewer           # delete all versions
harnesskit prompt delete code-reviewer@v0.0.1   # delete specific version
harnesskit prompt delete code-reviewer --yes     # skip confirmation
```

### Prompt YAML format

```yaml
name: code-reviewer
version: v0.1.0
description: "Senior code review engineer"
created_at: "2026-03-23T10:00:00+00:00"
tags: [code, review, security]
variables:
  - name: language
    required: true
  - name: focus
    required: false
    default: "security,performance"
content: |
  You are a senior {{language}} engineer...
changelog: "Initial version"
```

---

## Development

```bash
pip install -e ".[dev]"
pytest
```

---

## Roadmap

See [ROADMAP.md](ROADMAP.md) for the full 8-phase development plan.
