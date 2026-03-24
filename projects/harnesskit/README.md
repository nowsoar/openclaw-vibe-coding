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
pip install .
```

Development install (with test tools):

```bash
pip install -e ".[dev]"
```

After installation, the `harnesskit` command is available in your shell:

```bash
harnesskit --help
```

---

## Quick Start

```bash
# 1. Initialize a project workspace
harnesskit init

# 2. Save a prompt
harnesskit prompt save code-reviewer \
  --content "You are a senior {{language}} engineer." \
  --description "Code review system prompt" \
  --tags "code,review"

# 3. Save a schema (function-calling tool definition)
echo '{"type":"object","properties":{"path":{"type":"string"}},"required":["path"]}' \
  | harnesskit schema save read-file --description "Read a file"

# 4. Create a context template
cat > review.yaml << 'EOF'
description: Code review context
slots:
  - name: language
    required: true
  - name: code
    required: true
template: |
  Review the following {{language}} code:
  {{code}}
EOF
harnesskit context save review-ctx --file review.yaml

# 5. Add a rule constraint
harnesskit rule add no-hallucination \
  --type hard \
  --pattern "(根据我所知|我猜测)" \
  --description "禁止推测性表述" \
  --fix-hint "只陈述确认的事实"

# 6. Run a health check
harnesskit doctor
```

---

## Workspace Structure

`harnesskit init` creates a `.harness/` directory in the current folder:

```
.harness/
├── config.yaml         # default model, API key ref, log level
├── prompts/            # versioned prompt YAML files
├── schemas/            # versioned schema JSON files
├── contexts/           # versioned context template YAML files
├── rules/              # rule constraint YAML files (no versioning)
├── skills/             # skill definitions (Phase 2)
├── harnesses/          # harness configs (Phase 3)
├── agents/             # agent configs (Phase 3)
├── logs/               # call logs
├── evals/              # evaluation suites & results
└── improvements/       # improvement journal
```

Running `harnesskit init` twice is safe — it prints a warning and exits without overwriting existing configuration.

### Default `config.yaml`

```yaml
default_model: gpt-4o
api_key: ${OPENAI_API_KEY}
log_level: INFO
```

---

## Phase 1 Commands Reference

### `harnesskit init`

Initialize a HarnessKit workspace in the current directory.

```bash
harnesskit init
```

---

### `harnesskit prompt` — Prompt Asset Management

Prompts are versioned YAML files. Each save auto-increments the patch version (`v0.0.1 → v0.0.2 → …`).

#### Save

```bash
# From a string literal
harnesskit prompt save code-reviewer \
  --content "You are a senior {{language}} engineer."

# From a file
harnesskit prompt save code-reviewer --file ./reviewer.txt

# From stdin
cat reviewer.txt | harnesskit prompt save code-reviewer

# With full metadata
harnesskit prompt save code-reviewer \
  --content "You are a senior {{language}} engineer." \
  --description "Senior code review engineer" \
  --tags "code,review,security" \
  --changelog "Initial version"
```

#### Show

```bash
harnesskit prompt show code-reviewer           # latest version
harnesskit prompt show code-reviewer@v0.0.1   # specific version
```

#### List

```bash
harnesskit prompt list
```

#### Version history

```bash
harnesskit prompt history code-reviewer
```

#### Diff two versions

```bash
harnesskit prompt diff code-reviewer@v0.0.1 code-reviewer@v0.0.2
```

#### Delete

```bash
harnesskit prompt delete code-reviewer           # all versions (asks confirmation)
harnesskit prompt delete code-reviewer@v0.0.1   # specific version
harnesskit prompt delete code-reviewer --yes     # skip confirmation
```

#### Prompt YAML format

```yaml
name: code-reviewer
version: v0.0.1
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

### `harnesskit schema` — Schema Asset Management

Schemas store JSON Schema definitions for function-calling tools. Versioned the same way as prompts.

#### Save

```bash
# From a file (full schema document with 'parameters' key)
harnesskit schema save read-file --file schema.json

# From stdin (bare parameters object or full document)
echo '{"type":"object","properties":{"path":{"type":"string"}},"required":["path"]}' \
  | harnesskit schema save read-file --description "Read a file"
```

The JSON can be either:
- A **full document** with a `parameters` key: `{"description": "...", "parameters": {...}}`
- A **bare parameters object**: `{"type": "object", "properties": {...}}`

#### Show

```bash
harnesskit schema show read-file
harnesskit schema show read-file@v0.0.1
```

#### List

```bash
harnesskit schema list
```

#### Validate

Check that the schema's `parameters` object is a valid JSON Schema:

```bash
harnesskit schema validate read-file
```

#### Delete

```bash
harnesskit schema delete read-file --yes
harnesskit schema delete read-file@v0.0.1 --yes
```

---

### `harnesskit context` — Context Template Management

Context templates use [Jinja2](https://jinja.palletsprojects.com/) syntax with named **slots** (required/optional with defaults).

#### Save

```bash
# Create a YAML file first
cat > review.yaml << 'EOF'
description: Code review context
slots:
  - name: language
    required: true
  - name: code
    required: true
template: |
  Review the following {{language}} code:
  {{code}}
EOF

harnesskit context save review-ctx --file review.yaml
```

#### Render

```bash
harnesskit context render review-ctx \
  --var language=Python \
  --var "code=def foo(): pass"
```

#### Show

```bash
harnesskit context show review-ctx
harnesskit context show review-ctx@v0.0.1
```

#### List

```bash
harnesskit context list
```

#### Delete

```bash
harnesskit context delete review-ctx --yes
harnesskit context delete review-ctx@v0.0.1 --yes
```

#### Context YAML format

```yaml
description: "Code review context"
slots:
  - name: language
    required: true
  - name: style
    required: false
    default: "concise"
template: |
  Review the following {{language}} code in a {{style}} style:
  {{code}}
```

---

### `harnesskit rule` — Rule Constraint Management

Rules are **not versioned** — saving a rule with the same name overwrites it immediately.

Two types:
- **`hard`** — enforced by the linter (regex/length checks on LLM output)
- **`soft`** — injected into the system prompt as a text instruction

#### Add

```bash
# Hard rule: regex check
harnesskit rule add no-hallucination \
  --type hard \
  --check-type regex \
  --pattern "(根据我所知|我猜测)" \
  --description "禁止推测性表述" \
  --fix-hint "只陈述确认的事实"

# Hard rule: max length check
harnesskit rule add max-length \
  --type hard \
  --check-type length \
  --pattern "500" \
  --description "Output must not exceed 500 characters"

# Soft rule: prompt injection
harnesskit rule add be-concise \
  --type soft \
  --check-type regex \
  --pattern "." \
  --description "Always be concise and to the point"
```

#### List

```bash
harnesskit rule list
```

#### Show

```bash
harnesskit rule show no-hallucination
```

#### Test a rule against sample input

```bash
# Should trigger:
harnesskit rule test no-hallucination --input "根据我所知，这可能是对的"

# Should pass:
harnesskit rule test no-hallucination --input "这是经过验证的事实"
```

#### Delete

```bash
harnesskit rule delete no-hallucination --yes
```

---

### `harnesskit doctor` — Health Check

Scans `.harness/` for broken references, unused assets, and circular dependencies.

```bash
harnesskit doctor
```

Output example:

```
HarnessKit Doctor — .harness/ health check

Checking prompts... (1 found)
  ✓ code-reviewer  v0.0.1
Checking schemas... (1 found)
  ✓ read-file  v0.0.1

✓ No circular references detected.
✓ No unreferenced assets.

Summary: 0 broken reference(s), 0 unreferenced asset(s), 0 cycle(s), 2 total asset(s)
```

Returns exit code `1` if broken references or cycles are found, making it CI-friendly.

---

## Phase 2 Commands Reference

### `harnesskit skill run` — Execute a Skill via LLM

Run a skill by assembling its prompts, context, and rules, then calling the configured LLM.

#### Configuration

HarnessKit reads LLM settings from `.harness/config.yaml`:

```yaml
default_model: gpt-4o
api_key: ${OPENAI_API_KEY}   # env var reference
log_level: INFO
```

Override `base_url` for any OpenAI-compatible API (DeepSeek, Ollama, Azure, etc.):

```yaml
default_model: deepseek-chat
api_key: ${DEEPSEEK_API_KEY}
base_url: https://api.deepseek.com/v1
```

Or set `OPENAI_BASE_URL` environment variable.

#### Basic usage

```bash
# Run a skill, passing input variables with --var / -v
harnesskit skill run code-reviewer --var code="def foo(): pass" --var language=python

# Override the model for this call
harnesskit skill run code-reviewer --var code="..." --model gpt-4o-mini

# Stream output token-by-token
harnesskit skill run code-reviewer --var code="..." --stream
```

#### Dry-run (inspect without calling LLM)

Preview the assembled messages without making an API call — no API key required:

```bash
harnesskit skill run code-reviewer --var code="def foo(): pass" --dry-run
```

Output:

```
── Assembled Messages (dry-run) ──

[SYSTEM]
You are a senior code reviewer.
规则：Only output valid JSON

[USER]
Please review the following code:
def foo(): pass

Model: gpt-4o
```

#### Rule enforcement modes

```bash
# strict: hard rule violation → non-zero exit (fail fast)
harnesskit skill run code-reviewer --var code="..." --check-rules strict

# lenient (default): hard rule violation → warning only, still succeeds
harnesskit skill run code-reviewer --var code="..." --check-rules lenient
```

---

### `harnesskit logs` — LLM Call Logs

Every `skill run` execution is automatically recorded in `.harness/logs/calls.jsonl`.

#### View recent calls

```bash
harnesskit logs tail           # last 20 entries
harnesskit logs tail --n 50    # last 50 entries
```

Output:

```
            Recent LLM Calls
Timestamp            Skill          Model    Status   Tokens ↑↓  Duration
2026-03-24 10:00:01  code-reviewer  gpt-4o   success  120 / 80   1.23s
2026-03-24 10:01:05  code-reviewer  gpt-4o   error    0 / 0      0.00s
```

#### Search and filter

```bash
# Filter by skill name
harnesskit logs search --skill code-reviewer

# Filter by status
harnesskit logs search --status error

# Combine filters, limit results
harnesskit logs search --skill code-reviewer --status success --limit 10
```

#### Log record format (JSONL)

Each line in `calls.jsonl`:

```json
{
  "timestamp": "2026-03-24T10:00:01+00:00",
  "type": "llm_call",
  "skill": "code-reviewer",
  "model": "gpt-4o",
  "input_tokens": 120,
  "output_tokens": 80,
  "total_tokens": 200,
  "duration": 1.23,
  "status": "success",
  "inputs": {"code": "def foo(): pass", "language": "python"},
  "output_preview": "Issues found:\n1. Missing implementation..."
}
```

---



| Command | Description |
|---|---|
| `harnesskit init` | Initialize workspace |
| `harnesskit prompt save <name>` | Save/update a prompt |
| `harnesskit prompt show <name[@ver]>` | Display a prompt |
| `harnesskit prompt list` | List all prompts |
| `harnesskit prompt history <name>` | Version timeline |
| `harnesskit prompt diff <a> <b>` | Coloured diff |
| `harnesskit prompt delete <name[@ver]>` | Delete prompt |
| `harnesskit schema save <name>` | Save/update a schema |
| `harnesskit schema show <name[@ver]>` | Display a schema |
| `harnesskit schema list` | List all schemas |
| `harnesskit schema validate <name>` | Validate JSON Schema |
| `harnesskit schema delete <name[@ver]>` | Delete schema |
| `harnesskit context save <name>` | Save/update a context template |
| `harnesskit context render <name[@ver]>` | Render template with variables |
| `harnesskit context show <name[@ver]>` | Display a context template |
| `harnesskit context list` | List all context templates |
| `harnesskit context delete <name[@ver]>` | Delete context |
| `harnesskit rule add <name>` | Add/update a rule |
| `harnesskit rule list` | List all rules |
| `harnesskit rule show <name>` | Display a rule |
| `harnesskit rule test <name>` | Test rule against input |
| `harnesskit rule delete <name>` | Delete a rule |
| `harnesskit doctor` | Health check scan |
| `harnesskit skill run <name>` | Run a skill via LLM |
| `harnesskit skill run <name> --dry-run` | Preview assembled messages |
| `harnesskit skill run <name> --stream` | Stream LLM output |
| `harnesskit skill run <name> --check-rules strict` | Fail on hard rule violations |
| `harnesskit logs tail` | View recent LLM call logs |
| `harnesskit logs search` | Search/filter call logs |

Use `--help` on any command for full option details:

```bash
harnesskit --help
harnesskit prompt --help
harnesskit prompt save --help
```

---

## Version References

All versioned assets (prompts, schemas, contexts) support `name@version` syntax:

```bash
harnesskit prompt show my-prompt@v0.0.1   # exact version
harnesskit prompt show my-prompt          # current (latest) version
harnesskit prompt show my-prompt@prod     # tag alias (Phase 1.6+)
```

---

## Development

```bash
git clone <repo>
cd harnesskit
pip install -e ".[dev]"
pytest
```

Run integration tests only:

```bash
pytest tests/test_integration.py -v
```

---

## Roadmap

See [ROADMAP.md](ROADMAP.md) for the full 8-phase development plan.

Current status: **Phase 2.3 complete** — Skill independent execution: LLM calls (OpenAI-compatible), streaming output, hard/soft rule enforcement, and call logging.
