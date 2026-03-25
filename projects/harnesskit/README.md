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

## Skill End-to-End Tutorial

A **Skill** bundles a prompt, rules, context, and I/O schema into a versioned, runnable unit. Here is the full workflow.

### Step 1 — Create the raw assets

```bash
harnesskit init

# System prompt
harnesskit prompt save code-reviewer-system \
  --content "You are a senior {{language}} engineer. Review the code and return a JSON list of issues." \
  --description "Code reviewer system prompt" \
  --tags "code,review"

# User prompt
harnesskit prompt save code-reviewer-user \
  --content "Review this code:\n{{code}}" \
  --description "Code reviewer user prompt"

# Hard rule — blocks speculative output
harnesskit rule add no-speculation \
  --type hard \
  --pattern "I think|probably|我猜测|可能是" \
  --description "Do not speculate — only report confirmed issues" \
  --fix-hint "Remove speculative language; only state confirmed findings"

# Soft rule — injected into system prompt
harnesskit rule add output-json \
  --type soft \
  --pattern "." \
  --description "Always return output as valid JSON"

# Context template
cat > review_ctx.yaml << 'EOF'
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
harnesskit context save review-ctx --file review_ctx.yaml
```

### Step 2 — Define the Skill YAML

```yaml
# code-reviewer.yaml
name: code-reviewer
description: "Reviews code and outputs a list of issues"
trigger: "When code needs review"

inputs:
  - name: code
    type: string
    required: true
  - name: language
    type: string
    default: "auto"

outputs:
  - name: issues
    type: array

assets:
  prompts:
    system: code-reviewer-system
    user: code-reviewer-user
  rules:
    - no-speculation
    - output-json
  context: review-ctx

examples:
  - input:
      code: "def foo(): pass"
      language: python
    expected_contains: ["缺少实现"]

changelog: "Initial version"
```

```bash
harnesskit skill save code-reviewer --file code-reviewer.yaml
```

### Step 3 — Validate and inspect

```bash
# Check all referenced assets resolve correctly
harnesskit skill validate code-reviewer

# Preview assembled prompts without calling the LLM
harnesskit skill run code-reviewer \
  --var "code=def foo(): pass" \
  --var language=python \
  --dry-run

# Show all asset dependencies
harnesskit skill deps code-reviewer
```

### Step 4 — Run the Skill

```bash
# Set your API key
export OPENAI_API_KEY=sk-...

# Run with default (lenient) rule checking
harnesskit skill run code-reviewer \
  --var "code=def divide(a, b): return a/b" \
  --var language=python

# Run with strict rule checking (hard rule violation = non-zero exit)
harnesskit skill run code-reviewer \
  --var "code=def divide(a, b): return a/b" \
  --check-rules strict

# Stream output token by token
harnesskit skill run code-reviewer \
  --var "code=def divide(a, b): return a/b" \
  --stream
```

### Step 5 — Version management

```bash
# Iterate: save a new version (patch auto-increments)
harnesskit skill save code-reviewer --file code-reviewer-v2.yaml
harnesskit skill diff code-reviewer@v0.0.1 code-reviewer@v0.0.2

# Tag a version for deployment
harnesskit skill tag code-reviewer --name production

# Run the production-tagged version
harnesskit skill run code-reviewer@production --var "code=x=1"

# Clone to experiment without touching the original
harnesskit skill clone code-reviewer code-reviewer-experimental
```

### Step 6 — Observe

```bash
# View recent calls
harnesskit logs tail

# Search by skill name
harnesskit logs search --skill code-reviewer

# Check violation statistics
harnesskit rule stats
```

---

## Skill Design Best Practices

### 1. One skill = one responsibility
A skill should do exactly one thing. If you find yourself adding many branches to the prompt, split it into multiple skills.

### 2. Keep system prompts focused
The system prompt sets the agent's role and output format. User prompts and context templates provide the variable content. Keep them separate so each can be versioned independently.

### 3. Always define inputs and outputs
Even if you don't validate them at runtime yet, explicit `inputs` and `outputs` act as documentation and make the skill self-describing. Use `required: true` on fields that must be present.

### 4. Use hard rules for non-negotiable constraints
Hard rules run **after** the LLM responds and will block or warn on violations. Use them for:
- Output format requirements (e.g. must be JSON)
- Content safety (e.g. no speculative language)
- Length limits

Use `--check-rules strict` in CI and `--check-rules lenient` during development.

### 5. Use soft rules to guide behaviour
Soft rules are injected into the system prompt as plain text instructions. Use them for stylistic guidance that you want the model to follow but which doesn't need post-hoc enforcement.

### 6. Pin asset versions for production
Use tag aliases (`@production`, `@stable`) rather than floating references so a tag promotion is an explicit, auditable act:

```bash
# Promote v0.0.3 to production
harnesskit skill tag code-reviewer --name production --version v0.0.3
```

### 7. Add examples
The `examples` field in a skill YAML is documentation for now — it will feed the evaluation engine in Phase 5. Fill it in from the start so you build a regression dataset as you iterate.

### 8. Run `doctor` before committing
`harnesskit doctor` scans for broken references and unreferenced assets. Run it as a pre-commit check:

```bash
harnesskit doctor && git add .harness/ && git commit -m "Update skill definitions"
```

---

## Phase 2 Commands Reference

### `harnesskit skill` — Skill Version Management (Phase 2.5)

#### Tag a skill version

Create a named alias pointing to a specific (or current) version:

```bash
# Tag the current version as 'production'
harnesskit skill tag code-reviewer --name production

# Tag a specific version
harnesskit skill tag code-reviewer --name stable --version v0.0.1
```

Then load by tag alias:

```bash
harnesskit skill show code-reviewer@production
harnesskit skill run code-reviewer@production --var code="def foo(): pass"
```

#### Clone a skill

Copy a skill under a new name, resetting its version to `v0.0.1`:

```bash
harnesskit skill clone code-reviewer code-reviewer-experimental
```

The cloned skill:
- Gets a new name and `v0.0.1` version
- Preserves all inputs, outputs, assets, and examples
- Sets `changelog` to `"Cloned from 'code-reviewer'"`

#### List dependencies

Show all asset references declared by a skill:

```bash
harnesskit skill deps code-reviewer
harnesskit skill deps code-reviewer@v0.0.1
```

Output:

```
Dependencies of code-reviewer:

Prompts:
  • code-reviewer-system@v0.1.0
  • code-reviewer-user@v0.0.1

Rules:
  • no-hallucination
  • output-json

Context:
  • code-review-ctx@v0.0.1

Total: 4 dependency(ies)
```

---

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

Each line in `calls.jsonl`. When hard rules are triggered, a `violations` field is included:

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
  "status": "rule_violation",
  "inputs": {"code": "def foo(): pass"},
  "output_preview": "我猜测这里有一个 bug...",
  "violations": [
    {
      "rule": "no-speculation",
      "type": "hard",
      "matches": ["我猜测"],
      "fix_hint": "Remove speculative language"
    }
  ],
  "violation_count": 1
}
```

---

### `harnesskit rule stats` — Violation Statistics

View how many times each rule has been violated across all recorded LLM calls:

```bash
harnesskit rule stats
```

Output:

```
      Rule Violation Statistics
Rule              Type  Violations  Description
no-speculation    hard           3  No speculative content
no-hallucination  hard           1  No fabricated information
be-concise        soft           0  Keep responses brief

Total violations recorded in call logs: 4
```

This command reads `.harness/logs/calls.jsonl` to aggregate counts. It shows all rules (including those with zero violations) and highlights any rules that were deleted after violations were recorded.

---



---

## Phase 3 Commands Reference

### `harnesskit harness` — Harness Configuration Management

A **Harness** bundles multiple Skills with a shared model configuration, memory policy, and global constraints — forming a complete, versioned runtime for an Agent.

#### Create / Update

```bash
# Minimal creation
harnesskit harness create my-code-review --description "Code review harness"

# With skills and model config
harnesskit harness create my-code-review \
  --description "Code review harness" \
  --skills "code-reviewer@v0.1.0,explain-error@v0.0.2" \
  --model gpt-4o \
  --temperature 0.3 \
  --max-tokens 2000 \
  --memory-scope session \
  --max-turns 10 \
  --context-budget 4000

# From a YAML file
harnesskit harness create my-code-review --file harness.yaml
```

Harness YAML format:

```yaml
name: my-code-review
description: "Complete code review harness"

skills:
  - code-reviewer@v0.1.0
  - explain-error@v0.0.2

model:
  provider: openai
  name: gpt-4o
  temperature: 0.3
  max_tokens: 2000

memory:
  scope: session      # session | harness | global
  max_turns: 10

constraints:
  rules: [no-hallucination]
  max_cost_per_call: 0.01
  timeout: 30

context_budget: 4000
changelog: "Initial version"
```

#### Show

```bash
harnesskit harness show my-code-review           # latest version
harnesskit harness show my-code-review@v0.0.1   # specific version
```

#### List

```bash
harnesskit harness list
```

Output:

```
                   Harnesses
Name             Version  Skills  Model   Memory Scope  Description
my-code-review   v0.0.1       2  gpt-4o  session       Complete code review harness
```

#### Diff two versions

```bash
harnesskit harness diff my-code-review@v0.0.1 my-code-review@v0.0.2
```

#### Validate skill references

Checks that every skill referenced in the harness exists:

```bash
harnesskit harness validate my-code-review
```

Returns exit code `1` if any skill reference is broken — CI-friendly.

#### Clone

Copy a harness to a new name, resetting its version to `v0.0.1`:

```bash
harnesskit harness clone my-code-review my-code-review-staging
```

#### Delete

```bash
harnesskit harness delete my-code-review --yes        # all versions
harnesskit harness delete my-code-review@v0.0.1 --yes # specific version
```

#### Run a Harness

Execute a skill within a harness, using the harness model config, context budget, and constraint rules:

```bash
# Run a harness with a single skill
harnesskit harness run my-code-review --var code="def foo(): pass"

# Select a specific skill when harness has multiple skills
harnesskit harness run my-code-review --skill code-reviewer --var code="..."

# Preview assembled prompt without calling the LLM
harnesskit harness run my-code-review --dry-run

# Stream output token-by-token
harnesskit harness run my-code-review --stream --var code="..."

# Override model (takes priority over harness model config)
harnesskit harness run my-code-review --model gpt-4-turbo --var code="..."

# Strict rule checking — fail on hard rule violation
harnesskit harness run my-code-review --check-rules strict --var code="..."
```

**How `harness run` works:**

1. Loads harness config (model, context_budget, constraints.rules)
2. Resolves which skill to run (auto if 1 skill, or `--skill` flag for multiple)
3. Validates required skill inputs
4. Renders skill assets (prompts, context, rules)
5. Checks estimated token count against `context_budget` — warns if exceeded
6. Merges harness model config with global `.harness/config.yaml` (CLI `--model` takes priority)
7. Applies skill rules **plus** harness constraint rules to the output
8. Logs the call to `.harness/logs/calls.jsonl`

**Context budget management:**

The harness `context_budget` (in tokens) limits prompt size. HarnessKit estimates token count (~4 chars/token) before the LLM call and prints a warning if exceeded:

```
⚠ Estimated prompt tokens (~5200) exceed context_budget (4000).
  Consider reducing input size or increasing context_budget.
```

The call still proceeds — it's a warning, not a hard stop. Adjust `context_budget` in the harness YAML to tune this threshold.

**Multi-skill harness:**

When a harness has multiple skills, you must specify which one to run:

```bash
# Shows available skills if --skill is omitted
harnesskit harness run my-harness
# ⚠ Harness has 2 skills. Use --skill <name> to select one:
#   • code-reviewer@v0.1.0
#   • explain-error@v0.0.2

# Select explicitly
harnesskit harness run my-harness --skill code-reviewer --var code="..."
```

---

### `harnesskit memory` — Conversation Memory

When a harness has `memory.scope: harness` or `memory.scope: global`, each `harness run` automatically persists conversation turns to disk — enabling history-aware multi-turn interactions.

**Scopes:**

| Scope | Persistence | Path |
|---|---|---|
| `session` | In-process only (default) | — |
| `harness` | Per-harness JSON file | `.harness/memory/{name}.json` |
| `global` | Shared across all harnesses | `.harness/memory/global.json` |

**Configure memory in your harness YAML:**

```yaml
memory:
  scope: harness   # session | harness | global
  max_turns: 10    # auto-compress when exceeded
```

**Commands:**

```bash
# Show conversation history for a harness
harnesskit memory show my-code-review

# Show with global scope
harnesskit memory show my-code-review --scope global

# Limit to last 5 turns
harnesskit memory show my-code-review -n 5

# List all memory files
harnesskit memory list

# Search conversation history
harnesskit memory search my-code-review "python error"

# Clear memory (with confirmation prompt)
harnesskit memory clear my-code-review

# Clear without prompt
harnesskit memory clear my-code-review --yes
```

**Context compression:**

When the number of conversation turns exceeds `max_turns`, HarnessKit automatically compresses older turns into a summary, keeping recent context within budget:

```
[历史摘要 8 轮]
USER: what is dependency injection?
ASSISTANT: Dependency injection is a design pattern...
...
```

The summary is stored in `metadata.summary` and can be viewed with `memory show`.

**Disable memory for a single run:**

```bash
harnesskit harness run my-code-review --no-memory --var code="..."
```

---

### `harnesskit agent` — Interactive AI Agent (Phase 3.4)

An **Agent** binds a Harness to a persistent identity, enabling multi-turn interactive conversations in a REPL interface. Agents are stored as simple YAML files (no versioning — latest definition always wins).

#### Create an Agent

```bash
# Minimal: link to an existing harness
harnesskit agent create code-assistant --harness my-code-review

# Full options
harnesskit agent create code-assistant \
  --harness my-code-review \
  --identity-name "代码助手" \
  --description "帮助你审查和改进代码" \
  --memory-scope harness \   # session | harness | global
  --persist \                # persist memory across sessions
  --max-iterations 20        # max conversation turns per session
```

Agent YAML format (`.harness/agents/{name}.yaml`):

```yaml
name: code-assistant
harness: my-code-review@v0.1.0
identity:
  name: "代码助手"
  description: "帮助你审查和改进代码"
memory:
  scope: harness   # session | harness | global
  persist: true
max_iterations: 10
```

#### Run — Interactive REPL

```bash
harnesskit agent run code-assistant
```

This starts a REPL conversation:

```
╔══ Agent: 代码助手 ══
帮助你审查和改进代码
Harness: my-code-review | Model: gpt-4o | Memory: harness
Commands: /reset  /save  /quit
╚══════════════════════════════

You: 帮我看看这段 Python 代码有什么问题...

代码助手:
[AI response...]
  50↑ 120↓ tokens | 2.35s

You: /save
✓ Conversation saved to .harness/memory/conversations/code-assistant-20260324T103045.json

You: /quit
Goodbye!
```

**REPL commands:**

| Command | Description |
|---|---|
| `/reset` | Clear memory for this session |
| `/save` | Save conversation to `.harness/memory/conversations/` |
| `/save <path>` | Save conversation to a specific file |
| `/quit` or `/q` | Exit the REPL |

**Options:**

```bash
# Stream output token-by-token
harnesskit agent run code-assistant --stream

# Override model
harnesskit agent run code-assistant --model gpt-4-turbo

# Disable memory for this session
harnesskit agent run code-assistant --no-memory
```

#### Other commands

```bash
harnesskit agent list            # table of all agents
harnesskit agent show <name>     # show agent definition
harnesskit agent delete <name>   # delete agent (--yes to skip prompt)
```

**Memory persistence in agents:**

When `memory.scope` is `harness` or `global` **and** `memory.persist: true`, each assistant turn is automatically written to disk after the response. This means you can interrupt the session and resume later — memory carries over. With `scope: session` (default), memory is cleared when the REPL exits.

---

### Phase 3 End-to-End Tutorial

Complete walkthrough from an empty workspace to a running interactive agent:

```bash
# 1. Initialize workspace
harnesskit init

# 2. Create a system prompt
harnesskit prompt save code-reviewer-sys \
  --content "You are a senior {{language}} engineer. Review the code carefully." \
  --description "Code reviewer system prompt" \
  --tags "code,review"

# 3. Create a user prompt
harnesskit prompt save code-reviewer-user \
  --content "Please review the following code:\n{{code}}" \
  --description "Code reviewer user prompt"

# 4. Create a rule
harnesskit rule add no-speculation \
  --type hard \
  --pattern "(I think|I guess|probably|maybe it's)" \
  --description "No speculative language in reviews" \
  --fix-hint "State only confirmed issues"

# 5. Save a skill (from YAML file)
cat > code-reviewer.yaml << 'EOF'
name: code-reviewer
description: "Reviews code and reports issues"
trigger: "When code needs to be reviewed"
inputs:
  - name: code
    type: string
    required: true
  - name: language
    type: string
    default: python
outputs:
  - name: issues
    type: string
assets:
  prompts:
    system: code-reviewer-sys
    user: code-reviewer-user
  rules:
    - no-speculation
changelog: "Initial version"
EOF
harnesskit skill save --file code-reviewer.yaml

# 6. Create a harness combining the skill with model config
harnesskit harness create code-review-harness \
  --description "Full code review harness" \
  --skills "code-reviewer" \
  --model gpt-4o \
  --temperature 0.2 \
  --memory-scope harness \
  --max-turns 20 \
  --context-budget 8000

# 7. Validate all references are intact
harnesskit harness validate code-review-harness

# 8. Create an interactive agent
harnesskit agent create code-assistant \
  --harness code-review-harness \
  --identity-name "Code Assistant" \
  --description "Reviews and improves your code"

# 9. Start an interactive conversation
harnesskit agent run code-assistant
```

**Best practices for Phase 3:**

- **Keep skills focused**: Each skill should do one thing. Compose complexity in the harness, not in a single monolithic skill.
- **Version your harnesses**: Every `harness create` auto-increments the version. Use `harness diff` to review changes before deploying.
- **Use `harness validate` in CI**: Returns exit code `1` on broken references — catches regressions early.
- **Tune `context_budget`**: Start at 4000 tokens and increase if you see budget warnings. `harness run --dry-run` shows token estimates without making an LLM call.
- **Use `memory.scope: harness`** for persistent agents. Use `session` for stateless one-shot tasks.
- **Run the full doctor**: `harnesskit doctor` scans for broken references, missing assets, and stale pointers across your entire workspace.

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
| `harnesskit rule stats` | Violation count statistics |
| `harnesskit rule delete <name>` | Delete a rule |
| `harnesskit doctor` | Health check scan |
| `harnesskit skill save <name> --file <yaml>` | Save/update a skill |
| `harnesskit skill show <name[@ver]>` | Display skill definition |
| `harnesskit skill list` | List all skills |
| `harnesskit skill diff <a> <b>` | Diff two skill versions |
| `harnesskit skill validate <name>` | Check all asset refs are valid |
| `harnesskit skill tag <name> --name <tag>` | Create a version alias |
| `harnesskit skill clone <name> <new-name>` | Clone skill to new name (v0.0.1) |
| `harnesskit skill deps <name[@ver]>` | List all asset dependencies |
| `harnesskit skill run <name>` | Run a skill via LLM |
| `harnesskit skill run <name> --dry-run` | Preview assembled messages |
| `harnesskit skill run <name> --stream` | Stream LLM output |
| `harnesskit skill run <name> --check-rules strict` | Fail on hard rule violations |
| `harnesskit skill run <name> --check-rules lenient` | Warn on violations, continue |
| `harnesskit logs tail` | View recent LLM call logs |
| `harnesskit logs search` | Search/filter call logs |
| `harnesskit cost report` | Cost report grouped by skill/model/day |
| `harnesskit cost breakdown` | Per-call cost breakdown (most expensive first) |
| `harnesskit cost set-price` | Override model pricing in config |
| `harnesskit stats show <name>` | Statistics dashboard for a skill/harness |
| `harnesskit stats show <name> --since 7d` | Stats for the last 7 days |
| `harnesskit harness create <name>` | Create/update a harness |
| `harnesskit harness show <name[@ver]>` | Display harness definition |
| `harnesskit harness list` | List all harnesses |
| `harnesskit harness diff <a> <b>` | Diff two harness versions |
| `harnesskit harness validate <name>` | Validate all skill references |
| `harnesskit harness clone <name> <new>` | Clone harness to new name (v0.0.1) |
| `harnesskit harness delete <name[@ver]>` | Delete a harness |
| `harnesskit harness run <name>` | Run a harness skill via LLM |
| `harnesskit harness run <name> --skill <s>` | Select skill in multi-skill harness |
| `harnesskit harness run <name> --dry-run` | Preview assembled messages |
| `harnesskit harness run <name> --stream` | Stream LLM output |
| `harnesskit harness run <name> --check-rules strict` | Fail on hard rule violations |
| `harnesskit harness run <name> --no-memory` | Disable memory persistence for this run |
| `harnesskit memory show <name>` | Show conversation history for a harness |
| `harnesskit memory list` | List all persisted memory files |
| `harnesskit memory search <name> <keyword>` | Search conversation history |
| `harnesskit memory clear <name> --yes` | Clear memory for a harness |
| `harnesskit agent create <name> --harness <h>` | Create an interactive agent |
| `harnesskit agent run <name>` | Start interactive REPL conversation |
| `harnesskit agent run <name> --stream` | Stream agent output |
| `harnesskit agent run <name> --no-memory` | Run without persisting memory |
| `harnesskit agent list` | List all agents |
| `harnesskit agent show <name>` | Show agent definition |
| `harnesskit agent delete <name> --yes` | Delete an agent |
| `harnesskit blueprint create <name> --file <yaml>` | Create/update a blueprint |
| `harnesskit blueprint show <name[@ver]>` | Display blueprint definition |
| `harnesskit blueprint list` | List all blueprints |
| `harnesskit blueprint diff <a> <b>` | Diff two blueprint versions |
| `harnesskit blueprint validate <name>` | Validate structure, refs, assets, goto targets, and cycles |
| `harnesskit blueprint run <name>` | Execute blueprint steps (deterministic nodes) |
| `harnesskit blueprint run <name> --dry-run` | Render commands without executing |
| `harnesskit blueprint run <name> --step <id>` | Start from a specific step (skip earlier) |
| `harnesskit blueprint run <name> --verbose` | Show full stdout/stderr for every step |
| `harnesskit blueprint delete <name[@ver]>` | Delete a blueprint |
| `harnesskit health check` | Run full health check (staleness, success rate, unused assets) |
| `harnesskit health check --stale-days 7` | Custom staleness threshold |
| `harnesskit health check --success-threshold 0.9` | Custom success-rate threshold |
| `harnesskit health fix` | Preview auto-fixable issues |
| `harnesskit health fix --yes` | Apply all auto-fixes (delete unused assets) |
| `harnesskit health fix --dry-run` | Show what would be fixed without making changes |

Use `--help` on any command for full option details:

```bash
harnesskit --help
harnesskit prompt --help
harnesskit prompt save --help
```

---

## Phase 4 — Blueprint Workflows (Phase 4.1)

A **Blueprint** defines a hybrid workflow composed of *deterministic* nodes (shell commands) and *agentic* nodes (Harness / Skill calls). Steps pass data to each other via `{{steps.xxx.output}}` interpolation.

### Blueprint YAML Format

```yaml
name: code-review-pipeline
version: v0.1.0
description: "完整的代码审查流水线"

inputs:
  - name: file_path
    required: true

steps:
  - id: lint
    type: deterministic
    name: "代码格式检查"
    run: "flake8 {{inputs.file_path}}"
    on_fail: stop     # stop | continue | goto:<step_id>
    timeout: 10       # seconds

  - id: review
    type: agentic
    name: "AI 代码审查"
    harness: my-code-review@v0.1.0
    inputs:
      code: "{{steps.lint.output}}"
    max_retries: 2
    timeout: 60

  - id: summary
    type: agentic
    name: "生成摘要"
    skill: summarize@v0.1.0
    inputs:
      text: "{{steps.review.output}}"

outputs:
  lint_result: "{{steps.lint.output}}"
  review_result: "{{steps.review.output}}"
  summary: "{{steps.summary.output}}"
```

### Variable Interpolation (Phase 4.5)

| Syntax | Meaning |
|--------|---------|
| `{{inputs.file_path}}` | Blueprint-level input value |
| `{{steps.lint.output}}` | stdout / result of the `lint` step |
| `{{steps.lint.stderr}}` | stderr of a step |
| `{{steps.lint.exit_code}}` | Exit code of a deterministic step |
| `{{steps.lint.status}}` | Step status string (`success`, `failed`, …) |
| `{{env.MY_VAR}}` | OS environment variable |

#### Pipe Filters

Variables can be transformed with `|` filters before being inserted:

| Filter | Example | Result |
|--------|---------|--------|
| `truncate:N` | `{{steps.run.output \| truncate:100}}` | Keep first N chars, append `...` if longer |
| `json` | `{{steps.run.output \| json}}` | JSON-encode the value (adds quotes, escapes specials) |
| `upper` | `{{inputs.lang \| upper}}` | Convert to upper-case |
| `lower` | `{{inputs.lang \| lower}}` | Convert to lower-case |
| `strip` | `{{steps.run.output \| strip}}` | Strip leading/trailing whitespace |

Filters can be **chained**:

```yaml
# Strip whitespace, truncate, then JSON-encode
run: "echo '{{steps.prev.output | strip | truncate:80 | json}}'"

# In outputs block
outputs:
  summary: "{{steps.review.output | strip | truncate:200}}"
```

### `harnesskit blueprint` Commands

```bash
# Create / update a blueprint from a YAML file
harnesskit blueprint create my-pipeline --file pipeline.yaml

# Show blueprint definition
harnesskit blueprint show my-pipeline
harnesskit blueprint show my-pipeline@v0.0.1

# List all blueprints
harnesskit blueprint list

# Diff two versions
harnesskit blueprint diff my-pipeline@v0.0.1 my-pipeline@v0.0.2

# Validate structure and variable references
harnesskit blueprint validate my-pipeline

# Validate structure only (skip asset existence checks)
harnesskit blueprint validate my-pipeline --no-check-assets

# Delete (all versions or a specific one)
harnesskit blueprint delete my-pipeline --yes
harnesskit blueprint delete my-pipeline@v0.0.1 --yes
```

### Storage Layout

```
.harness/blueprints/{name}/
    v0.0.1.yaml
    v0.0.2.yaml
    _current          ← plain-text file containing current version
```

### Blueprint Validation (Phase 4.2)

`harnesskit blueprint validate` runs **five checks** and produces a rich, categorised report:

| Check | What it verifies |
|---|---|
| **Structure** | Required fields, valid step types, unique IDs, `on_fail` values, etc. |
| **Variable References** | All `{{steps.xxx.*}}` and `{{inputs.xxx}}` point to declared step/input IDs |
| **Asset References** | Referenced harnesses and skills actually exist in `.harness/` |
| **Goto Targets** | `on_fail: goto:<id>` values reference a declared step ID |
| **Variable Cycles** | No circular dependencies between step outputs |

Example output:

```
Blueprint 'my-pipeline@v0.0.1' — Validation Report
────────────────────────────────────────────────────

[Structure] ✓ No errors
[Variable References] ✓ No errors
[Asset References] 1 error(s)
  • Step 'review': harness 'my-harness@v0.1.0' not found.
    Fix: run 'harnesskit harness list' to see available harnesses.
[Goto Targets] ✓ No errors
[Variable Cycles] ✓ No errors
────────────────────────────────────────────────────
✗ Found 1 error(s). Blueprint is NOT valid.
```

---

### Blueprint Executor — Deterministic & Agentic Steps (Phase 4.3 + 4.4 + 4.6)

`harnesskit blueprint run` executes a blueprint's steps in order, providing real-time progress output.  Both `type: deterministic` (shell) and `type: agentic` (LLM) steps are fully supported.

**Key features:**

| Feature | Description |
|---|---|
| **Shell command execution** | `type: deterministic` steps run via `subprocess` with stdout/stderr capture |
| **Agentic step execution** | `type: agentic` steps call a **Skill** or **Harness** via LLM |
| **Harness model config** | When a step references a `harness:`, its `model:` settings override global defaults |
| **Retry with back-off** | `max_retries: N` retries on transient errors (rate-limit, 429, 503…) with exponential back-off |
| **Timeout control** | Each step respects its `timeout` value (default 60 s for deterministic, 120 s for agentic) |
| **Variable interpolation** | `{{inputs.x}}`, `{{steps.id.output}}`, `{{env.VAR}}` resolved at runtime; pipe filters (`truncate:N`, `json`, `upper`, `lower`, `strip`) transform values inline |
| **`on_fail: stop`** | Abort pipeline, mark remaining steps as skipped |
| **`on_fail: continue`** | Continue to next step despite failure |
| **`on_fail: goto:<id>`** | Jump to a specific step for error recovery |
| **`--dry-run`** | Render all commands / show agentic refs without executing |
| **`--step <id>`** | Resume from a specific step (skip earlier ones) |
| **`--verbose`** | Print stdout/stderr for every step |
| **Output resolution** | Blueprint `outputs` block resolved against step results |
| **Call logging** | Agentic steps log to `.harness/logs/calls.jsonl` |
| **Execution report** | Each run saves a JSON report to `.harness/logs/blueprints/{name}-{timestamp}.json` |
| **Real-time progress** | Rich spinner shows the current running step; results are printed as each step completes |

**Example:**

```bash
# Create a pipeline
cat > pipeline.yaml << 'EOF'
name: lint-pipeline
description: "Lint then summarise results"
inputs:
  - name: file_path
    required: true

steps:
  - id: lint
    type: deterministic
    name: "Run flake8"
    run: "flake8 {{inputs.file_path}} || true"
    on_fail: continue
    timeout: 30

  - id: count
    type: deterministic
    name: "Count issues"
    run: "echo {{steps.lint.output}} | wc -l"

outputs:
  issues: "{{steps.lint.output}}"
  count:  "{{steps.count.output}}"
EOF

harnesskit blueprint create lint-pipeline --file pipeline.yaml

# Dry-run preview (no commands executed)
harnesskit blueprint run lint-pipeline --dry-run --var file_path=mycode.py

# Execute for real
harnesskit blueprint run lint-pipeline --var file_path=mycode.py

# Verbose output (shows stdout/stderr per step)
harnesskit blueprint run lint-pipeline --var file_path=mycode.py --verbose

# Resume from a specific step
harnesskit blueprint run lint-pipeline --var file_path=mycode.py --step count
```

Example terminal output:

```
Blueprint lint-pipeline@v0.0.1
─────────────────────────────
  ✓ lint  Run flake8  0.31s
  ✓ count Count issues  0.05s
─────────────────────────────
Outputs:
  issues: mycode.py:12:1: E302 ...
  count: 3

✓ Blueprint 'lint-pipeline' completed successfully (0.36s)
Report saved: .harness/logs/blueprints/lint-pipeline-20260324T103045123456.json
```

**Agentic step example** — mix shell commands with LLM calls:

```yaml
steps:
  - id: lint
    type: deterministic
    run: "flake8 {{inputs.file_path}}"
    on_fail: continue

  - id: review
    type: agentic
    name: "AI code review"
    skill: code-reviewer@v0.1.0          # or use harness: my-harness@v0.1.0
    inputs:
      code: "{{steps.lint.output}}"
    max_retries: 2
    timeout: 60

  - id: summary
    type: agentic
    skill: summarize@v0.1.0
    inputs:
      text: "{{steps.review.output}}"
```

```bash
harnesskit blueprint run my-pipeline --var file_path=app.py
```

### Execution Reports (Phase 4.6)

Every `harnesskit blueprint run` call automatically saves a JSON report to:

```
.harness/logs/blueprints/{name}-{timestamp}.json
```

The report contains per-step duration, status, output preview, and a summary:

```json
{
  "timestamp": "2026-03-24T10:30:45.123456+00:00",
  "blueprint": "lint-pipeline",
  "version": "v0.0.1",
  "status": "success",
  "duration": 0.36,
  "summary": {
    "total": 2,
    "success": 2,
    "failed": 0,
    "skipped": 0,
    "dry_run": 0
  },
  "steps": [
    {"id": "lint", "status": "success", "duration": 0.31, "exit_code": 0, "output_preview": "..."},
    {"id": "count", "status": "success", "duration": 0.05, "exit_code": 0, "output_preview": "3"}
  ],
  "outputs": {"issues": "...", "count": "3"}
}
```

Reports are written even when a blueprint fails or is stopped, making them useful for debugging and post-run analysis.

---

## Phase 5 — Eval Engine

The **Eval Engine** lets you define repeatable test suites for your Skills and Harnesses — with structured assertions — so you can measure and compare quality over time.

### Test Suite YAML Format

```yaml
name: code-review-suite
description: "代码审查测试集"

cases:
  - id: detect-bug
    name: "发现除零错误"
    inputs:
      code: "def divide(a, b): return a/b"
      language: python
    assertions:
      - type: contains
        path: "$.issues[*].type"
        value: "ZeroDivisionError"
      - type: regex
        path: "$.summary"
        pattern: "异常处理|error handling"

  - id: empty-function
    name: "空函数检查"
    inputs:
      code: "def foo(): pass"
      language: python
    assertions:
      - type: contains
        path: "$.issues[*].message"
        value: "缺少实现"
```

**Supported assertion types:**

| Type | Required fields | Description |
|---|---|---|
| `contains` | `path`, `value` | JSONPath result contains `value` |
| `regex` | `path`, `pattern` | JSONPath result matches regex `pattern` |
| `json_schema` | `path`, `schema` | JSONPath result validates against JSON Schema |
| `custom` | `function` | Call a custom Python function (e.g. `mymodule.check`) |

Storage: `.harness/evals/suites/{name}.yaml` (no versioning — direct overwrite).

### Eval Commands

```bash
# Add or update a test suite from a YAML file
harnesskit eval suite-add --file suite.yaml

# List all saved test suites
harnesskit eval list

# Inspect a test suite (cases + assertions)
harnesskit eval show code-review-suite

# Delete a test suite
harnesskit eval delete code-review-suite --yes
```

### Assertion Engine (Phase 5.2)

The assertion engine evaluates structured assertions against any Python value (dict, list, string) using **JSONPath** (`jsonpath-ng`) for navigation.

#### Assertion types

| Type | Required fields | Description |
|---|---|---|
| `contains` | `path`, `value` | JSONPath result equals or contains `value` (substring / list element) |
| `regex` | `path`, `pattern` | JSONPath result matches regex `pattern` (any match in the result list) |
| `json_schema` | `path`, `schema` | First JSONPath match validates against a JSON Schema dict |
| `custom` | `function` | Importable Python function returns truthy (e.g. `mymodule.check`) |

`path` uses standard JSONPath syntax (e.g. `$`, `$.key`, `$.items[*].type`).
`path` is optional — if omitted, the root data value is used directly.

#### Using the assertion engine in Python

```python
from harness_kit.assertions import run_assertions, assertions_passed, assertion_summary

# Typically you'd get this from an LLM call result
llm_output = {
    "issues": [
        {"type": "ZeroDivisionError", "severity": "high", "message": "除零风险"}
    ],
    "summary": "发现 error handling 问题",
}

assertions = [
    {"type": "contains", "path": "$.issues[*].type",     "value": "ZeroDivisionError"},
    {"type": "contains", "path": "$.issues[*].severity", "value": "high"},
    {"type": "regex",    "path": "$.summary",            "pattern": r"异常处理|error handling"},
    {
        "type": "json_schema",
        "path": "$.issues[0]",
        "schema": {
            "type": "object",
            "required": ["type", "severity", "message"],
        },
    },
]

results = run_assertions(assertions, llm_output)

if assertions_passed(results):
    print("All assertions passed!")
else:
    for r in results:
        if not r.passed:
            print(r.message)  # "FAIL — '$.issues[*].type' does not contain ..."

summary = assertion_summary(results)
print(summary)  # {"total": 4, "passed": 4, "failed": 0}
```

#### AssertionResult fields

| Field | Type | Description |
|---|---|---|
| `passed` | `bool` | `True` if the assertion was satisfied |
| `assertion_type` | `str` | Type string (`contains`, `regex`, …) |
| `path` | `str \| None` | The JSONPath that was evaluated |
| `expected` | `Any` | The expected value / pattern / schema |
| `actual` | `Any` | The values returned by the JSONPath evaluation |
| `message` | `str` | Human-readable `OK — …` or `FAIL — …` explanation |

---

## Phase 5.3 — Single Eval Run

`harnesskit eval run` executes a test suite against a skill, evaluates every assertion, and generates a full evaluation report.

### Running an eval

```bash
# Run the test suite "code-review-suite" against skill "code-reviewer"
harnesskit eval run code-reviewer --suite code-review-suite

# Pin to a specific version
harnesskit eval run code-reviewer@v0.2.0 --suite code-review-suite

# Override the LLM model
harnesskit eval run code-reviewer --suite code-review-suite --model gpt-4o-mini

# CI mode: exit with code 1 when any test case fails
harnesskit eval run code-reviewer --suite code-review-suite --ci
```

### Output example

```
Eval: code-reviewer@v0.1.0  suite=code-review-suite  cases=2

 ID           Name              Status       Duration  Tokens  Assertions
 detect-bug   发现除零错误       ✓ passed     1.23s     350     2/2
 empty-func   空函数检查         ✗ failed     0.98s     290     0/1

✗ empty-func — 空函数检查
  FAIL [contains] FAIL — '$.issues[*].message' does not contain '缺少实现'. Actual: ...

Summary: total=2  passed=1  failed=1
Report saved: .harness/evals/results/2026-03-24T10-00-00-000.json
```

### Result report format

Each run persists a JSON report to `.harness/evals/results/{timestamp}.json`:

```json
{
  "timestamp": "2026-03-24T10:00:00+00:00",
  "target": "code-reviewer@v0.1.0",
  "suite": "code-review-suite",
  "summary": {
    "total": 2,
    "passed": 1,
    "failed": 1
  },
  "cases": [
    {
      "id": "detect-bug",
      "name": "发现除零错误",
      "status": "passed",
      "duration": 1.23,
      "input_tokens": 200,
      "output_tokens": 150,
      "output_preview": "{\"issues\": [{\"type\": \"ZeroDivisionError\" ...}",
      "assertions": [
        {
          "type": "contains",
          "path": "$.issues[*].type",
          "passed": true,
          "message": "OK — '$.issues[*].type' contains 'ZeroDivisionError'"
        }
      ],
      "assertion_summary": {"total": 2, "passed": 2, "failed": 0}
    }
  ]
}
```

### LLM output parsing

The eval runner automatically tries to parse each LLM response as JSON so that JSONPath assertions can navigate it:

1. Direct JSON object or array → parsed with `json.loads`
2. Markdown fenced code block (` ```json ... ``` `) → extracted and parsed
3. Anything else → left as a raw string (string assertions still work)

### `run_eval` Python API

You can use the eval runner from your own code without going through the CLI:

```python
from harness_kit.eval import run_eval

def my_invoke(inputs: dict) -> tuple[str, int, int, float]:
    # Call your LLM here and return (output_text, input_tokens, output_tokens, duration)
    return '{"issues": [{"type": "ok"}], "summary": "looks fine"}', 100, 50, 1.2

report = run_eval(
    target="my-skill@v0.1.0",
    suite_name="code-review-suite",
    invoke_fn=my_invoke,
)
print(report["summary"])  # {"total": 1, "passed": 1, "failed": 0}
```

---

## Phase 5.4 — A/B Comparison

`harnesskit eval compare` runs the **same test suite** against two skill targets and produces a side-by-side metrics comparison so you can decide which version to promote.

### Usage

```bash
# Compare two versions of the same skill
harnesskit eval compare \
  --a code-reviewer@v0.1.0 \
  --b code-reviewer@v0.2.0 \
  --suite code-review-suite

# Override the LLM model for both runs
harnesskit eval compare --a my-skill@v1 --b my-skill@v2 \
  --suite my-suite --model gpt-4o-mini

# CI mode: exit 1 if either target has failures
harnesskit eval compare --a my-skill@v1 --b my-skill@v2 \
  --suite my-suite --ci
```

### Output

The command prints two rich tables:

**Metrics Comparison** — pass rate, avg tokens, total tokens, avg duration for each target, with colour-coded deltas (green = improvement):

```
           Metrics Comparison
┌─────────────┬──────────────────┬──────────────────┬──────────────┐
│ Metric      │ A: skill@v0.1.0  │ B: skill@v0.2.0  │ Change (B vs A) │
├─────────────┼──────────────────┼──────────────────┼──────────────┤
│ Pass rate   │ 2/3 (66.7%)      │ 3/3 (100.0%)     │ ▲0.333       │
│ Avg tokens  │ 120.0            │ 110.0            │ ▲-10.0       │
│ Total tokens│ 360              │ 330              │ ▼-30         │
│ Avg duration│ 1.200s           │ 0.900s           │ ▲-0.3        │
└─────────────┴──────────────────┴──────────────────┴──────────────┘
```

**Changed Cases** — only the test cases where the pass/fail status differs between A and B.

A final **Recommendation** line names the better target (higher pass rate wins; tokens used as tie-breaker).

### `compare_evals` Python API

```python
from harness_kit.eval import run_eval, compare_evals

report_a = run_eval("my-skill@v0.1.0", "my-suite", invoke_fn_a)
report_b = run_eval("my-skill@v0.2.0", "my-suite", invoke_fn_b)

cmp = compare_evals(report_a, report_b)
print(cmp["verdict"])          # "a" or "b"
print(cmp["metrics_a"])        # pass_rate, total_tokens, avg_duration, …
print(cmp["changed_cases"])    # list of cases where status differed
```

---

## Phase 5.5 — Multi-model Benchmark

`harnesskit eval benchmark` runs the **same skill** against multiple LLM models on the same test suite in one command, then produces a side-by-side comparison so you can choose the best model for your use case.

### Usage

```bash
# Benchmark a skill across three models
harnesskit eval benchmark code-reviewer \
  --suite code-review-suite \
  --models "gpt-4o,claude-3-5-sonnet,deepseek-v3"

# Pin to a specific skill version
harnesskit eval benchmark code-reviewer@v0.2.0 \
  --suite code-review-suite \
  --models "gpt-4o,gpt-4o-mini"

# CI mode: exit 1 if any model has failures
harnesskit eval benchmark code-reviewer \
  --suite code-review-suite \
  --models "gpt-4o,gpt-4o-mini" \
  --ci
```

### Output

**Benchmark table** — one row per model showing pass rate, token usage, and duration. The recommended model is marked with ★:

```
          Benchmark — code-reviewer@v0.2.0 × code-review-suite
┌──────────────────────┬───────────┬────────┬────────┬────────────┬─────────────┬──────────────┐
│ Model                │ Pass Rate │ Passed │ Failed │ Avg Tokens │ Total Tokens│ Avg Duration │
├──────────────────────┼───────────┼────────┼────────┼────────────┼─────────────┼──────────────┤
│ gpt-4o ★             │ 100.0%    │      5 │      0 │      180.0 │         900 │       1.200s │
│ gpt-4o-mini          │  80.0%    │      4 │      1 │       95.0 │         475 │       0.800s │
│ deepseek-v3          │  80.0%    │      4 │      1 │      210.0 │        1050 │       2.100s │
└──────────────────────┴───────────┴────────┴────────┴────────────┴─────────────┴──────────────┘
```

**Per-case results** — grid showing ✓/✗ for each case × model combination.

A **Best Model** recommendation line names the winner (highest pass rate; tie-break: fewest tokens, then fastest).

### Selection logic

| Criterion | Direction |
|---|---|
| Pass rate | Higher is better |
| Avg tokens | Lower is better (tie-break) |
| Avg duration | Lower is better (tie-break) |

### `benchmark_evals` Python API

```python
from harness_kit.eval import run_eval, benchmark_evals

reports = []
for model in ["gpt-4o", "gpt-4o-mini", "deepseek-v3"]:
    report = run_eval(
        target=f"my-skill@v0.1.0 [{model}]",
        suite_name="my-suite",
        invoke_fn=make_invoke_fn(model),   # your factory
        extra_fields={"model": model, "skill": "my-skill@v0.1.0"},
    )
    reports.append(report)

bench = benchmark_evals(reports)
print(bench["best_model"])   # e.g. "gpt-4o"
for entry in bench["entries"]:
    print(entry["model"], entry["metrics"]["pass_rate"])
```

---

## Phase 5.6 — Eval System Integration

Phase 5.6 completes the evaluation engine with three features: **Harness eval-suite binding**, **CI mode with JUnit XML reports**, and **historical pass-rate trend analysis**.

### Harness Eval-Suite Binding

Bind a test suite to a harness at creation time so the relationship is stored in the harness YAML:

```bash
# Create a harness and bind a test suite to it
harnesskit harness create my-harness \
  --description "Production code reviewer" \
  --skills code-reviewer \
  --eval-suite code-review-suite

# The eval_suite field is stored in the harness YAML
harnesskit harness show my-harness
```

The `eval_suite` field is persisted in `.harness/harnesses/my-harness/vX.Y.Z.yaml`:

```yaml
name: my-harness
version: v0.1.0
description: Production code reviewer
skills:
  - code-reviewer
eval_suite: code-review-suite
...
```

### CI Mode with JUnit XML

Use `--ci` to fail the process with exit code 1 when any test case fails (ideal for CI pipelines):

```bash
# Exit code 0 = all passed, exit code 1 = any failures
harnesskit eval run my-skill --suite my-suite --ci

# Also generate a JUnit XML report (consumed by Jenkins, GitHub Actions, etc.)
harnesskit eval run my-skill --suite my-suite --ci --junit-xml results/junit.xml
```

The JUnit XML follows the standard `<testsuites>/<testsuite>/<testcase>` format with `<failure>` and `<error>` elements for failed/errored cases.

**GitHub Actions example:**

```yaml
- name: Run eval
  run: harnesskit eval run my-skill --suite my-suite --ci --junit-xml results/junit.xml
- name: Publish test results
  uses: dorny/test-reporter@v1
  if: always()
  with:
    name: Eval Results
    path: results/junit.xml
    reporter: java-junit
```

### Historical Trend Analysis

`harnesskit eval trend` reads all saved eval results from `.harness/evals/results/` and displays a pass-rate trend table with an ASCII sparkline chart:

```bash
# Show all eval history
harnesskit eval trend

# Filter by target name (substring match)
harnesskit eval trend my-skill

# Filter by suite
harnesskit eval trend --suite code-review-suite

# Limit to last N runs
harnesskit eval trend --limit 10
```

Example output:

```
              Eval History Trend
 # │ Timestamp           │ Target               │ Suite            │ Pass Rate │ Passed │ Total │ Trend
───┼─────────────────────┼──────────────────────┼──────────────────┼───────────┼────────┼───────┼──────
 1 │ 2026-01-01 12:00:00 │ my-skill@v0.1.0      │ code-review-…    │      60.0%│      3 │     5 │
 2 │ 2026-01-03 14:30:00 │ my-skill@v0.2.0      │ code-review-…    │      80.0%│      4 │     5 │ ↑
 3 │ 2026-01-05 09:15:00 │ my-skill@v0.2.1      │ code-review-…    │     100.0%│      5 │     5 │ ↑

Pass-Rate Chart (each bar = one run)

  ▅▇█
  ───
  0%100%

Latest: 100.0%  Avg: 80.0%  (3 runs shown)
```

### Python API

```python
from harness_kit.eval import generate_junit_xml, eval_trend

# Generate JUnit XML from a run_eval report
report = run_eval(target="my-skill@v0.1.0", suite_name="my-suite", invoke_fn=invoke_fn)
generate_junit_xml(report, Path("results/junit.xml"))

# Get trend data programmatically
entries = eval_trend(target_filter="my-skill", suite_filter="my-suite", limit=20)
for entry in entries:
    print(f"{entry['timestamp']}: {entry['pass_rate']:.0%}")
```

---

## Phase 6.1 — 调用日志系统 (Call Log System)

Phase 6.1 adds a full-featured call log system for observability: every LLM call is recorded as a JSON Lines entry, and you can tail, search, and export those logs from the CLI.

### Log Record Format

Every `skill run` or `harness run` appends a record to `.harness/logs/calls.jsonl`:

```json
{
  "timestamp": "2026-03-25T10:00:00+00:00",
  "type": "llm_call",
  "skill": "code-reviewer",
  "model": "gpt-4o",
  "input_tokens": 500,
  "output_tokens": 200,
  "total_tokens": 700,
  "cost": 0.015,
  "duration": 2.5,
  "status": "success"
}
```

### `harnesskit logs tail`

Show the most recent LLM call log entries:

```bash
# Last 20 entries (default)
harnesskit logs tail

# Last 50 entries
harnesskit logs tail --n 50

# Only entries from the last 24 hours
harnesskit logs tail --since 1d

# Last 2 hours
harnesskit logs tail --since 2h
```

### `harnesskit logs search`

Search and filter call logs:

```bash
# Filter by skill name
harnesskit logs search --skill code-reviewer

# Filter by status
harnesskit logs search --status error

# Filter by time window
harnesskit logs search --since 1d

# Combine filters
harnesskit logs search --skill code-reviewer --since 7d --limit 100
```

Supported `--since` units: `d` (days), `h` (hours), `m` (minutes), `s` (seconds).

### `harnesskit logs export`

Export logs as CSV or JSON Lines for further analysis:

```bash
# Export all logs as CSV to stdout
harnesskit logs export --format csv

# Export last 7 days as CSV to a file
harnesskit logs export --format csv --since 7d --output logs.csv

# Export as JSON Lines
harnesskit logs export --format jsonl --since 1d

# Filter by skill and export
harnesskit logs export --format csv --skill code-reviewer --since 30d
```

CSV columns: `timestamp`, `type`, `skill`, `model`, `input_tokens`, `output_tokens`, `total_tokens`, `cost`, `duration`, `status`, `error`, `violation_count`.

### Python API

```python
from harness_kit import call_logger as cl
from pathlib import Path

# Log a call programmatically
cl.log_call(
    skill="my-skill",
    model="gpt-4o",
    input_tokens=200,
    output_tokens=80,
    duration=1.5,
    cost=0.012,
    status="success",
)

# Tail the last 10 entries from the last day
records = cl.tail_logs(n=10, since="1d")

# Search by skill and time window
results = cl.search_logs(skill="my-skill", since="7d", limit=50)

# Export as CSV string
csv_data = cl.export_logs(fmt="csv", since="7d")

# Export as JSON Lines string
jsonl_data = cl.export_logs(fmt="jsonl", since="1d", skill="my-skill")
```

---

## Phase 6.2 — 成本追踪 (Cost Tracking)

Phase 6.2 adds per-call cost estimation, aggregated cost reports, per-model pricing configuration, and cost alert thresholds.

Every `skill run` and `harness run` call now automatically calculates and logs the USD cost using built-in pricing tables for all major models.

### Built-in model pricing

Prices are pre-configured for the most common models (USD per 1K tokens):

| Model | Input | Output |
|---|---|---|
| gpt-4o | $0.0025 | $0.0100 |
| gpt-4o-mini | $0.00015 | $0.0006 |
| claude-3-5-sonnet | $0.003 | $0.015 |
| claude-3-opus | $0.015 | $0.075 |
| deepseek-v3 | $0.00027 | $0.0011 |

### `harnesskit cost report`

```bash
harnesskit cost report                      # 30-day report, grouped by skill
harnesskit cost report --since 7d           # last 7 days
harnesskit cost report --group-by model     # grouped by model
harnesskit cost report --group-by day       # daily breakdown
```

Output includes: total spend, call count, token count, avg per call, most expensive call.

### `harnesskit cost breakdown`

```bash
harnesskit cost breakdown                   # top 20 most expensive calls (7d)
harnesskit cost breakdown --since 30d       # last 30 days
harnesskit cost breakdown --skill my-skill  # filter by skill
harnesskit cost breakdown --limit 10        # show top 10
```

### `harnesskit cost set-price`

Override the price for any model:

```bash
harnesskit cost set-price my-model --input 0.001 --output 0.002
harnesskit cost list-prices                 # show all prices
```

Prices are saved to `.harness/config.yaml` under `model_pricing`.

### Cost alerts via config

Add alert thresholds to `.harness/config.yaml`:

```yaml
cost_alert:
  per_call: 0.05    # warn if a single call exceeds $0.05
  per_day: 1.00     # warn if daily total exceeds $1.00
```

### Log record — cost field

Every call log record includes the computed cost:

```json
{"timestamp": "...", "skill": "code-reviewer", "model": "gpt-4o",
 "input_tokens": 500, "output_tokens": 200, "cost": 0.003250, "duration": 1.8}
```

---

## Phase 6.3 — 统计仪表盘 (Statistics Dashboard)

Phase 6.3 adds a rich statistics dashboard that aggregates call-log data for any skill or harness and renders it as tables and ASCII bar charts directly in the terminal.

### `harnesskit stats show`

```bash
harnesskit stats show my-skill              # all-time stats
harnesskit stats show my-skill --since 7d   # last 7 days
harnesskit stats show my-skill --since 24h  # last 24 hours
harnesskit stats show my-skill --bar-width 40  # wider bar charts
```

**Example output:**

```
── Stats: my-skill (last 7d) ──

Overview
┏━━━━━━━━━━━━━━━━━━━━━━┳━━━━━━━━━━━┓
┃ Metric               ┃     Value ┃
┡━━━━━━━━━━━━━━━━━━━━━━╇━━━━━━━━━━━┩
│ Total calls          │        47 │
│ Successful           │        44 │
│ Errors               │         3 │
│ Success rate         │     93.6% │
│ Avg duration         │     2.14s │
│ Min duration         │     0.82s │
│ Max duration         │     8.37s │
│ Avg tokens / call    │       621 │
│   ↳ input            │       499 │
│   ↳ output           │       122 │
│ Total tokens         │    29,187 │
│ Total cost           │  $0.0726  │
│ Avg cost / call      │ $0.001544 │
└──────────────────────┴───────────┘

Token Consumption Distribution (total tokens per call)

  0–100      ████░░░░░░░░░░░░░░░░░░░░░░░░░░     3
  101–250    ████████░░░░░░░░░░░░░░░░░░░░░░     8
  251–500    ██████████████░░░░░░░░░░░░░░░░    14
  501–1K     ██████████████████████░░░░░░░░    22

Duration Distribution

  0–1s       ████░░░░░░░░░░░░░░░░░░░░░░░░░░     4
  1–3s       █████████████████████░░░░░░░░░    21
  3–5s       ████████████░░░░░░░░░░░░░░░░░░    12
  5–10s      ██████░░░░░░░░░░░░░░░░░░░░░░░░     6

Model Usage
┏━━━━━━━━━━━━━━━┳━━━━━━━┳━━━━━━━┓
┃ Model         ┃ Calls ┃ Share ┃
┡━━━━━━━━━━━━━━━╇━━━━━━━╇━━━━━━━┩
│ gpt-4o        │    32 │ 68.1% │
│ gpt-4o-mini   │    15 │ 31.9% │
└───────────────┴───────┴───────┘

No errors recorded — all calls succeeded
```

### What's tracked

| Metric | Description |
|---|---|
| Call count | Total, successful, and error call counts |
| Success rate | Percentage of successful calls (green ≥90%, yellow ≥70%, red <70%) |
| Duration stats | Average, min, and max call duration in seconds |
| Token distribution | Histogram of total tokens per call across 8 size buckets |
| Duration distribution | Histogram of call duration across 6 time buckets |
| Model usage | Which models were used and how often |
| Error types | Frequency of each distinct error message |
| Cost summary | Total and average USD cost per call |

---

## Phase 6.4 — 改进飞轮核心 (Improvement Flywheel)

Phase 6.4 implements the **Improvement Flywheel**: a structured log that turns every Harness failure into a documented, trackable improvement step. Every fix is recorded with its context (issue, root cause, versions before/after, eval delta), making your iteration history auditable and actionable.

### Storage

Each skill's improvement journal lives at `.harness/improvements/{skill}.jsonl`. Each line is a JSON record:

```json
{
  "timestamp": "2026-03-25T10:00:00+00:00",
  "type": "improvement",
  "skill": "code-reviewer",
  "issue": "LLM hallucinated a function name",
  "root_cause": "Missing no-hallucination rule",
  "fix": "Added no-hallucination hard rule to skill",
  "before_version": "v0.1.0",
  "after_version": "v0.1.1",
  "eval_improvement": "+12%"
}
```

### `harnesskit improve log`

Record an improvement interactively via CLI flags:

```bash
harnesskit improve log code-reviewer \
  --issue "LLM hallucinated a function name" \
  --root-cause "Missing no-hallucination rule" \
  --fix "Added no-hallucination hard rule to skill" \
  --before v0.1.0 \
  --after v0.1.1 \
  --eval "+12%"
```

Output:

```
✓ Improvement logged for skill code-reviewer
  Timestamp    2026-03-25 10:00:00+00:00
  Skill        code-reviewer
  Issue        LLM hallucinated a function name
  Root Cause   Missing no-hallucination rule
  Fix          Added no-hallucination hard rule to skill
  Versions     v0.1.0 → v0.1.1
  Eval Δ       +12%
```

### `harnesskit improve history <skill>`

View full improvement history for a skill (most-recent first):

```bash
harnesskit improve history code-reviewer          # all time
harnesskit improve history code-reviewer --since 7d
harnesskit improve history code-reviewer --limit 5
```

Output:

```
Improvement History: code-reviewer
Found 3 record(s)

 1. 2026-03-25 10:00:00  v0.1.0 → v0.1.1  +12%
    Issue:      LLM hallucinated a function name
    Root cause: Missing no-hallucination rule
    Fix:        Added no-hallucination hard rule to skill

 2. 2026-03-22 09:30:00  v0.0.2 → v0.1.0  +8%
    Issue:      Output was not valid JSON
    Root cause: Prompt did not enforce JSON output
    Fix:        Added output-json soft rule
```

### `harnesskit improve report`

Aggregate all improvements for a reporting period:

```bash
harnesskit improve report                   # default: week
harnesskit improve report --period day
harnesskit improve report --period month
harnesskit improve report --period 14d
```

Output:

```
Improvement Report — period: week  (since 2026-03-18 10:00:00 UTC)

  Total improvements   3
  Skills improved      2
  Eval gains recorded  2

Improvements by Skill
┏━━━━━━━━━━━━━━━━┳━━━━━━━┳━━━━━━━━━━━━━━━━━━━━━━┓
┃ Skill          ┃ Count ┃ Bar                  ┃
┡━━━━━━━━━━━━━━━━╇━━━━━━━╇━━━━━━━━━━━━━━━━━━━━━━┩
│ code-reviewer  │     2 │ ████████████████████ │
│ summarizer     │     1 │ ██████████           │
└────────────────┴───────┴──────────────────────┘

Eval Improvements Recorded
  ▲ +12%
  ▲ +8%

Recent Improvements
  2026-03-25 10:00:00  code-reviewer  v0.1.0 → v0.1.1  +12%
    Fix: Added no-hallucination hard rule to skill
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
pytest tests/test_integration.py -v         # Phase 1 integration
pytest tests/test_phase2_integration.py -v  # Phase 2 integration
pytest tests/test_phase3_integration.py -v  # Phase 3 end-to-end
```

---

## Phase 6.5 — Harness 健康检查 (Harness Health Check)

Phase 6.5 adds a comprehensive **health check system** that proactively surfaces problems in your Harness workspace before they cause failures.

### What is checked

| Category | Severity | Description |
|---|---|---|
| **Staleness** | warning / critical | Skills not updated in N days (default 14). Critical when ≥ 2× threshold. |
| **Success Rate** | warning / critical | Skills whose call-log success rate is below threshold (default 80%). Critical when < 75% of threshold. Skipped if fewer than 5 calls. |
| **Unused Assets** | warning | Prompts, schemas, contexts, and rules not referenced by any skill or harness. These are **auto-fixable**. |
| **Schema Outdated** | warning | Schemas not updated in N days (default 14). |

### `harnesskit health check`

```bash
harnesskit health check                           # default thresholds (14 days, 80% success)
harnesskit health check --stale-days 7            # flag skills older than 7 days
harnesskit health check --success-threshold 0.9   # require 90% success rate
```

**Example output:**

```
HarnessKit Health Check

Stale Assets (1 issue(s))
┌──────────┬────────────┬────────────────┬──────────────────────────────────────────┐
│ Severity │ Asset Type │ Name           │ Message                                  │
├──────────┼────────────┼────────────────┼──────────────────────────────────────────┤
│ WARNING  │ skill      │ old-classifier │ Skill 'old-classifier' has not been      │
│          │            │                │ updated in 18 days (threshold: 14 days)  │
└──────────┴────────────┴────────────────┴──────────────────────────────────────────┘

Unused Assets (2 issue(s))
┌──────────┬────────────┬──────────────┬─────────────────────────────────────────────────┐
│ Severity │ Asset Type │ Name         │ Message                                         │
├──────────┼────────────┼──────────────┼─────────────────────────────────────────────────┤
│ WARNING  │ prompt     │ draft-prompt │ Prompt 'draft-prompt' is not referenced by any  │
│          │            │              │ skill or harness (auto-fixable)                 │
└──────────┴────────────┴──────────────┴─────────────────────────────────────────────────┘

Summary: 0 critical, 3 warning — 2 auto-fixable
Scanned: 3 skill(s), 2 schema(s), 4 primitive asset(s)

Run harnesskit health fix to auto-fix 2 issue(s).
```

Exit code is **1** when any critical issues are found, **0** otherwise.

### `harnesskit health fix`

```bash
harnesskit health fix               # preview fixable issues, then prompt for confirmation
harnesskit health fix --yes         # skip confirmation prompt
harnesskit health fix --dry-run     # show what would be done without making changes
```

Auto-fixable issues: currently **unused assets** (prompts, schemas, contexts, rules not referenced by any skill or harness). The fix deletes the asset directory / file.

**Example:**

```bash
$ harnesskit health fix --yes
Auto-fixable issues (2 found)
┌───┬──────────┬────────────┬──────────────┬─────────────────────────────────────┐
│ # │ Severity │ Asset Type │ Name         │ Fix Action                          │
├───┼──────────┼────────────┼──────────────┼─────────────────────────────────────┤
│ 1 │ WARNING  │ prompt     │ draft-prompt │ harnesskit prompt delete draft-prompt │
│ 2 │ WARNING  │ rule       │ unused-rule  │ harnesskit rule delete unused-rule  │
└───┴──────────┴────────────┴──────────────┴─────────────────────────────────────┘

Fix Report
  ✓ Deleted: .harness/prompts/draft-prompt
  ✓ Deleted: .harness/rules/unused-rule.yaml

Fixed: 2  Failed: 0
```

---

## Phase 6.6 — Phase 6 集成与优化 (Observability Integration & Optimization)

Phase 6.6 completes the Phase 6 observability layer with a comprehensive end-to-end integration test suite and performance optimizations for all log-reading paths.

### Performance Improvements

All log-reading functions (`tail_logs`, `search_logs`, `export_logs`, `violation_stats` in `call_logger.py`, plus the matching readers in `stats.py`, `improvement.py`, and `health.py`) have been upgraded from loading the entire file into memory to **streaming line-by-line** with `collections.deque`:

| Before | After |
|---|---|
| `file.read_text().splitlines()` — whole file in RAM | `with file.open() as f: for line in f` — one line at a time |
| `records[-n:]` — allocates full list then slices | `deque(maxlen=n)` — O(1) rolling window |

This means `harnesskit logs tail`, `logs search`, `stats show`, and `health check` stay fast even when `.harness/logs/calls.jsonl` grows to millions of lines.

### Integration Test Suite

`tests/test_phase6_integration.py` adds **28 pytest tests** that verify the complete observability pipeline end-to-end:

| Test Group | Coverage |
|---|---|
| `TestLogPipeline` (6) | write → tail → search → export CSV/JSONL → violation stats |
| `TestCostPipeline` (4) | cost estimation, report by skill / by model, CLI smoke |
| `TestStatsPipeline` (4) | success rate, duration buckets, token buckets, CLI smoke |
| `TestImprovementPipeline` (4) | log improvement, history, report, CLI smoke |
| `TestHealthPipeline` (5) | clean workspace, stale skill, unused asset, CLI, dry-run fix |
| `TestEndToEndFlow` (2) | full Python API chain + full CLI chain |
| `TestPerformance` (3) | 1000-record tail/search/export — each must complete < 1 s |

---

## Phase 7.1 — TUI 框架搭建 (TUI Framework)

Phase 7.1 introduces an interactive terminal user interface (TUI) powered by [Textual](https://github.com/Textualize/textual).

### Launch the TUI

```bash
harnesskit tui
```

### Layout

The TUI is divided into four regions:

```
┌─────────────────────────────────────────────────────┐
│  HarnessKit  —  Local AI Harness Engineering Toolkit │  ← Header
├────────────────┬────────────────────────────────────┤
│  HarnessKit    │                                     │
│  ──────────    │   ⚙ Skills                          │
│  ⚙  Skills    │                                     │  ← Main
│  🔧 Harnesses  │   可复用的 AI 能力单元。每个 Skill…  │
│  📋 Blueprints │                                     │
│  🧪 Eval       │                                     │
│  📜 Logs       │                                     │
│  💰 Cost       │                                     │
│  🔄 Improve    │                                     │
│  🏥 Health     │                                     │
│  ⚙️ Settings   │                                     │
├────────────────┴────────────────────────────────────┤
│  j 向下   k 向上   Enter 选择   ? 帮助   q 退出       │  ← Footer
└─────────────────────────────────────────────────────┘
```

### Keyboard Shortcuts

| Key | Action |
|-----|--------|
| `j` / `↓` | Move cursor down |
| `k` / `↑` | Move cursor up |
| `Enter` | Select / activate current item |
| `?` | Toggle help overlay |
| `q` | Quit |

### Navigation Sections

| Section | Description |
|---------|-------------|
| Skills | Browse skill assets and their descriptions |
| Harnesses | View harness configurations |
| Blueprints | Explore workflow definitions |
| Eval | Evaluation engine overview |
| Logs | Call log information |
| Cost | Cost tracking overview |
| Improve | Improvement flywheel |
| Health | Health check status |
| Settings | Configuration reference |

### Dependencies

`textual>=0.40.0` is added as a runtime dependency. It is installed automatically with `pip install harness-kit`.

### Tests

Phase 7.1 ships with **21 pytest tests** in `tests/test_tui.py`:

| Test Category | Count | Coverage |
|---|---|---|
| Module import & structure | 5 | package import, callable, NAV_ITEMS |
| App configuration | 6 | title, subtitle, bindings (q/j/k/↑↓/?) |
| Textual pilot (async) | 9 | compose, initial state, j/k navigation, clamping, ? help overlay, arrow keys |
| CLI integration | 1 | `tui` command registered in main app |

---

## Phase 7.2 — Skill 浏览器 (Skill Browser)

Phase 7.2 adds an interactive Skill browser inside the TUI — a dedicated
`SkillBrowserScreen` that lets you explore, search, and take action on every
Skill registered in your `.harness/` directory.

### Open the Skill Browser

```
harnesskit tui          # launch TUI
# Navigate to ⚙  Skills and press Enter
```

### Layout

```
┌─────────────────────────────────────────────────────────────────────────┐
│ HarnessKit                                    Skill 浏览器               │
├──────────────────┬──────────────────────────────────────────────────────┤
│ ⚙  Skills        │  code-reviewer   v0.1.0                              │
│ ──────────────── │                                                       │
│ 搜索 Skill…      │  描述：审查代码，输出问题列表                        │
│                  │  触发条件：当需要审查代码时                          │
│  code-reviewer   │                                                       │
│  summarizer      │  输入参数：                                          │
│  explainer       │    * code  (string)                                  │
│                  │      lang  (string)  (默认: auto)                    │
│                  │                                                       │
│                  │  快捷操作：                                          │
│                  │    r  运行  → harnesskit skill run code-reviewer      │
│                  │    d  对比  → harnesskit skill diff code-reviewer@…   │
│                  │    e  编辑  → harnesskit skill save --file <…>        │
├──────────────────┴──────────────────────────────────────────────────────┤
│ Esc 返回  j 向下  k 向上  r 运行  d Diff  e 编辑                        │
└─────────────────────────────────────────────────────────────────────────┘
```

### Keyboard Shortcuts

| Key | Action |
|-----|--------|
| `j` / `↓` | Move selection down |
| `k` / `↑` | Move selection up |
| `r` | Show `harnesskit skill run <name>` command |
| `d` | Show `harnesskit skill diff` command |
| `e` | Show `harnesskit skill save --file` command |
| `Esc` | Return to main navigation |

### Search & Filter

Type in the search box at the top of the left pane to filter skills
by name or description in real time.

### Tests

Phase 7.2 ships with **27 pytest tests** in `tests/test_tui_skill_browser.py`:

| Test Category | Count | Coverage |
|---|---|---|
| Module import & structure | 2 | package import, tui export |
| Formatter unit tests | 5 | detail text, inputs, outputs, assets, command hints |
| Binding configuration | 4 | escape, j/k, r/d/e |
| Instantiation | 2 | basic, base_path injection |
| Textual pilot (async) | 13 | compose, empty state, skill listing, detail, j/k nav, clamping, search filter, r/d/e notices, dismiss notice |
| Main app integration | 1 | Enter on Skills nav → SkillBrowserScreen pushed |

---

## Phase 7.3 — Prompt Diff 可视化 (Prompt Diff Visualization)

Phase 7.3 adds an interactive side-by-side **Prompt Diff** screen inside the TUI — select any
two prompt versions and instantly see what changed, with line-level colour coding and
character-level inline diff highlighting.

### Launch

```bash
harnesskit tui          # launch TUI
# → Navigate to "📝  Prompts" with j/k
# → Press Enter → PromptDiffScreen opens
# → Esc to return
```

### PromptDiffScreen layout

```
╔═ HarnessKit ══════════════════════════════════════════════════════╗
║ 📝 Prompt                │ ─── my-prompt@v0.0.1 ─── │ ─── my-prompt@v0.0.2 ─── ║
║ ─────────────────────    │                            │                            ║
║ my-prompt  v0.0.2        │ [dim]common line[/dim]     │ [dim]common line[/dim]     ║
║                          │ [red]- old text[/red]      │ [green]+ new text[/green]  ║
║ 旧版本 (左)               │ [dim]context[/dim]         │ [dim]context[/dim]         ║
║  v0.0.1 ✓               │                            │                            ║
║                          │                            │                            ║
║ 新版本 (右)               │                            │                            ║
║  v0.0.2 ✓               │                            │                            ║
╚══════════════════════════════════════════════════════════════════════╝
```

**Left sidebar** — prompt list + old/new version selectors.  Selecting a prompt or version
immediately refreshes the diff.

**Right area** — two side-by-side panes:
| Pane | Content |
|------|---------|
| Left (old) | Version A — removed lines in **red** (`-`) |
| Right (new) | Version B — added lines in **green** (`+`) |
| Both | Unchanged context lines in dim colour |

**Inline diff** — for lines that changed between versions, character-level differences are
additionally highlighted with `bold red` (old side) / `bold green` (new side).

### Keyboard shortcuts (PromptDiffScreen)

| Key | Action |
|-----|--------|
| `j` / `↓` | Scroll both diff panes down simultaneously |
| `k` / `↑` | Scroll both diff panes up simultaneously |
| `Esc` | Return to main TUI navigation |

Selecting a different prompt or version in the left sidebar updates the diff in real time —
no extra key press needed.

### Test coverage

Phase 7.3 ships with **33 pytest tests** in `tests/test_tui_prompt_diff.py`:

| Test Category | Count | Coverage |
|---|---|---|
| Pure helper functions | 13 | `_escape_markup`, `_inline_diff`, `build_diff_panes` (empty, deleted, added, unchanged, inline, labels) |
| Module import & structure | 6 | package import, tui export, widget import |
| Instantiation & bindings | 4 | basic, base_path injection, escape, j/k bindings |
| Textual pilot (async) | 8 | compose, empty state, prompt loading, single/two version defaults, pane population, label display, escape nav, j/k scroll |
| Main app integration | 2 | Enter on Prompts nav → PromptDiffScreen pushed |

---

## Phase 7.4 — Eval 结果可视化 (Eval Result Visualization)

Phase 7.4 adds an interactive **Eval Result Browser** inside the TUI — visualise test suite outcomes at a glance, with colour-coded pass/fail per case and full assertion detail on demand.

```bash
harnesskit tui          # launch TUI
# → navigate to 🧪  Eval → press Enter
```

### Layout

```
┌─ 🧪 Test Suites ─────┬─ Cases ─ my-suite  (1/2 passed) ──────────────────────────────────────┐
│                       │ ✓  Case 0                                                               │
│ my-suite  (2 cases)   │ ✗  Case 1                                                               │
│ other-suite (3 cases) │                                                                         │
│                       ├─ 断言详情 ─────────────────────────────────────────────────────────────┤
│                       │ Case 0  id: case-0                                                      │
│                       │ 状态：✓ passed                                                          │
│                       │ 耗时：0.100s   Tokens: in 10 / out 5                                   │
│                       │ 断言（1/1 通过）：                                                      │
│                       │   ✓  contains  $.result                                                 │
│                       │      OK                                                                 │
└───────────────────────┴─────────────────────────────────────────────────────────────────────────┘
```

**Left pane** — all test suites (from `.harness/evals/suites/`)
**Top-right pane** — all cases for the selected suite, coloured:
- `[green]✓[/green]` — case passed in the most-recent eval run
- `[red]✗[/red]` — case failed or errored
- `[dim]•[/dim]` — no run data yet

**Bottom-right pane** — assertion detail for the selected case: status, duration, tokens, output preview, and each assertion with its message.

### Keyboard shortcuts

| Key | Action |
|-----|--------|
| `j / ↓` | Move selection down |
| `k / ↑` | Move selection up |
| `Tab` | Switch focus between Suites and Cases panes |
| `Esc` | Return to main TUI navigation |

### Tests

Phase 7.4 ships with **30 pytest tests** in `tests/test_tui_eval_browser.py`:

| Test Category | Count | Coverage |
|---|---|---|
| Pure helper functions | 9 | `_status_markup` (passed/failed/error/unknown), `_format_case_list` (no results, with results), `_format_assertion_detail` (no result, with result, with error) |
| Module import & structure | 2 | package import, tui re-export |
| Instantiation & bindings | 5 | basic, base_path injection, escape/j/k/tab bindings |
| Textual pilot (async) | 12 | compose, empty state, suite listing, case list, green/red colouring, assertion messages, j/k nav, tab pane switch, j in cases pane, escape nav, result summary |
| Main app integration | 2 | Enter on Eval nav → EvalBrowserScreen pushed |

---

## Phase 7.5 — 实时日志流 (Real-time Log Stream)

Phase 7.5 adds a live **Log Browser** screen inside the TUI — a `tail -f`-style real-time view of all LLM call logs with filtering, search highlight, and pause/resume support.

```bash
harnesskit tui          # launch TUI
# → navigate to 📜  Logs → press Enter
```

### Features

| Feature | Description |
|---|---|
| Real-time tail | Panel auto-refreshes every 2 s, showing the most recent 200 calls |
| Skill filter | Partial, case-insensitive match against the Skill name |
| Time window filter | Human-readable durations: `1d`, `2h`, `30m`, `60s` |
| Search highlight | Keyword search tints matching rows with a dark-blue background |
| Pause / Resume | Freeze the view with `Space`, resume with `Space` again |
| Manual refresh | Force an immediate reload with `r` regardless of pause state |
| Colour coding | `✓` success rows in green, `✗` error rows in red |

### Log panel columns

```
时间                  Skill                Model             状态   耗时    Tokens   费用
2026-03-25 10:00:00  code-reviewer        gpt-4o            ✓     2.50s    300tok  $0.0150
2026-03-25 10:01:00  translate-skill      claude-3-5-sonnet ✗     0.80s     50tok  $0.0030
```

### Keyboard shortcuts

| Key | Action |
|---|---|
| `Space` | Pause / resume live refresh |
| `r` | Force immediate refresh |
| `j / ↓` | Scroll log panel down |
| `k / ↑` | Scroll log panel up |
| `Esc` | Return to main TUI navigation |

> **Filter inputs** (Skill, Since, Search) are accessible via mouse click or Tab navigation.  `Space` and `r` use priority bindings so they work from any focus state.

### Tests

Phase 7.5 ships with **35 pytest tests** in `tests/test_tui_logs_browser.py`:

| Test Category | Count | Coverage |
|---|---|---|
| Pure helper functions | 16 | `_escape_markup`, `_format_timestamp`, `_format_status` (success/error/unknown), `_format_record` (basic, no cost, search highlight, case-insensitive), `_format_log_panel` (empty, records, paused indicator, search highlight) |
| Module import & structure | 2 | package import, tui re-export |
| Instantiation & bindings | 6 | basic, base_path injection, escape/space/j/k/r bindings, initial pause state |
| Textual pilot (async) | 9 | compose, empty state, record display, record count, pause toggle, pause indicator, r refresh, escape nav, success green / error red / multiple records |
| Main app integration | 2 | Enter on Logs nav → LogsBrowserScreen pushed |

---

## Phase 7.6 — TUI 优化与完善 (TUI Polish & Completion)

Phase 7.6 polishes the TUI with four user-experience improvements:

1. **Enhanced help page** — The `?` overlay is now scrollable (`ScrollableContainer`) and documents every shortcut across all screens, including the new theme-toggle key.
2. **Theme toggle** — Press `t` to switch between `textual-dark` and `textual-light` themes without restarting.
3. **Responsive layout** — The sidebar narrows automatically when the terminal is resized: 16 cols at <80 wide, 22 cols at 80–99 wide, 24 cols at ≥100 wide.
4. **Error handling** — All `push_screen` calls are wrapped in `try/except`; failures surface as Textual toast notifications (`self.notify`) instead of crashing the app.

### Quick reference

| Key | Action |
|-----|--------|
| `t` | Toggle Dark ↔ Light theme |
| `?` | Open / close scrollable help page |
| `j` / `k` | Navigate up / down in current list |
| `Enter` | Open screen for selected section |
| `Esc` | Return to previous screen |
| `q` | Quit |

### Theme toggle

```
harnesskit tui      # launches in default dark theme
# press 't' to switch to light theme, press again to go back
```

### Responsive layout

The sidebar automatically adapts its width to the terminal size:

| Terminal width | Sidebar width |
|---------------|---------------|
| < 80 cols     | 16 cols       |
| 80–99 cols    | 22 cols       |
| ≥ 100 cols    | 24 cols       |

### Error handling

If a screen fails to load (e.g., missing data files), the app shows a toast notification at the top of the screen instead of crashing:

```
[ERROR] 加载屏幕时发生未知错误
```

### Phase 7.6 test coverage

Phase 7.6 ships with **23 pytest tests** in `tests/test_tui_phase76.py`:

| Category | Tests | Description |
|----------|-------|-------------|
| Binding checks | 3 | `t` key present; original bindings preserved; theme action callable |
| Help page | 3 | CSS overflow, scrollable container, theme key mentioned |
| Error handling | 2 | `action_select_item` and `on_list_view_selected` both have `try/except` |
| Source inspection | 2 | Theme action uses `self.theme`; resize handler adjusts sidebar |
| Pilot — theme toggle | 4 | Dark↔light toggle, restore after 2 presses, only dark/light values |
| Pilot — help overlay | 3 | Shows on `?`, closes on any key, contains scrollable container |
| Pilot — help content | 1 | 't' key and 主题 appear in label text |
| Pilot — responsive | 2 | Narrow (≤20) and wide (24) sidebar after resize |
| Pilot — misc | 3 | No crash on nav, theme does not affect index, help + theme combo |

---

## Phase 8.1 — Web 服务框架 (Web Service Framework)

Phase 8.1 brings a full **FastAPI + uvicorn** HTTP layer to HarnessKit, letting you
interact with your local `.harness/` workspace over a REST API — from a browser,
Postman, or any HTTP client.

### Quick start

```bash
# Install (fastapi + uvicorn are now core dependencies)
pip install harness-kit

# Start the server (default: http://127.0.0.1:7749)
harnesskit serve

# Custom host/port
harnesskit serve --host 0.0.0.0 --port 8080

# Development mode with auto-reload
harnesskit serve --reload
```

### API endpoints

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/api/skills` | List all skills (name, version, description, …) |
| `GET` | `/api/skills/{name}` | Get full skill definition |
| `POST` | `/api/skills/{name}/run` | Run a skill with given inputs |

### Request / Response examples

**List skills**
```bash
curl http://127.0.0.1:7749/api/skills
# [{"name":"code-reviewer","version":"v0.1.0","description":"…"}, …]
```

**Get skill**
```bash
curl http://127.0.0.1:7749/api/skills/code-reviewer
# {"name":"code-reviewer","version":"v0.1.0","inputs":[…], …}
```

**Run skill**
```bash
curl -X POST http://127.0.0.1:7749/api/skills/code-reviewer/run \
  -H "Content-Type: application/json" \
  -d '{"inputs": {"code": "def foo(): pass", "language": "python"}, "model": "gpt-4o"}'
# {"output":"…","model":"gpt-4o","input_tokens":120,"output_tokens":80,"duration":1.3,"skill":"code-reviewer","version":"v0.1.0"}
```

### CORS

All origins are allowed (`*`) so any front-end running on localhost (or elsewhere)
can call the API without a proxy.

### Interactive docs

FastAPI's auto-generated Swagger UI is available at
[http://127.0.0.1:7749/docs](http://127.0.0.1:7749/docs) and the OpenAPI JSON
schema at `/openapi.json`.

### Phase 8.1 test coverage

Phase 8.1 ships with **22 pytest tests** in `tests/test_web.py`:

| Category | Tests | Coverage |
|----------|-------|----------|
| App creation | 3 | `create_app()` returns FastAPI, default base, title |
| `GET /api/skills` | 4 | empty workspace, skill present, JSON content-type, fields |
| `GET /api/skills/{name}` | 4 | 200 with body, 404 with detail, unknown skill name |
| `POST /api/skills/{name}/run` | 5 | 404 missing skill, 422 missing input, 503 no API key, 200 with LLM mock, model override |
| CORS | 2 | preflight OPTIONS, allow-origin on GET |
| OpenAPI docs | 2 | schema paths present, /docs 200 |
| CLI `serve` | 2 | command registered, `--host`/`--port` flags |

---

## Phase 8.2 — 前端框架搭建 (Frontend Framework)

Phase 8.2 adds a full **HTMX + Alpine.js + TailwindCSS** web frontend to HarnessKit, served
directly by FastAPI's static file layer. No build step, no Node.js — everything runs from CDN.

### Starting the Web UI

```bash
harnesskit serve
# Open http://localhost:7749 in your browser
```

### Frontend architecture

| Component | Role |
|-----------|------|
| **HTMX** | Declarative HTTP requests; navigation swaps partial HTML into `#content` |
| **Alpine.js** | Lightweight reactive data (skills list, loading state, search filter) |
| **TailwindCSS CDN** | Utility-first styling, zero config |
| **FastAPI `StaticFiles`** | Serves `harness_kit/web/static/` at `/static/` |

### Page structure

```
http://localhost:7749/
├── Header (HarnessKit title + global loading indicator + API Docs link)
├── Sidebar navigation
│   ├── Skills      → hx-get="/partials/skills"
│   ├── Harness     → hx-get="/partials/harness"
│   ├── Eval        → hx-get="/partials/eval"
│   ├── Logs        → hx-get="/partials/logs"
│   └── Settings    → hx-get="/partials/settings"
└── Main content area (#content) — HTMX swaps partials here
```

### Navigation flow

1. Browser loads `/` → FastAPI serves `index.html`
2. HTMX fires `hx-get="/partials/skills"` on page load → skills partial injected into `#content`
3. Each navigation click fires `hx-get="/partials/{section}"` → new partial replaces `#content`
4. The **Skills** partial uses Alpine.js `fetch('/api/skills')` to load live data from the API

### New API endpoints (Phase 8.2)

| Endpoint | Description |
|----------|-------------|
| `GET /` | Serve `index.html` frontend shell |
| `GET /partials/{section}` | Return HTMX partial HTML for `skills \| harness \| eval \| logs \| settings` |
| `GET /static/*` | Static assets (CSS, JS, images) |

### File layout

```
harness_kit/web/
├── __init__.py            # create_app() — FastAPI app factory
└── static/
    ├── index.html         # Main SPA shell
    └── partials/
        ├── skills.html    # Skills browser (Alpine.js + /api/skills)
        ├── harness.html   # Harness list
        ├── eval.html      # Eval dashboard
        ├── logs.html      # Call log viewer
        └── settings.html  # Config / quick links
```

### Phase 8.2 test coverage

Phase 8.2 ships with **44 new pytest tests** in `tests/test_web_frontend.py`:

| Category | Tests | Coverage |
|----------|-------|----------|
| Root page (`GET /`) | 16 | 200 status, HTML content-type, TailwindCSS/HTMX/Alpine.js CDN tags, nav items, `hx-get`, `#content` target |
| Partial: skills | 5 | 200, HTML, heading, Alpine.js fetch, `/api/skills` reference |
| Partial: harness | 2 | 200, heading |
| Partial: eval | 2 | 200, heading |
| Partial: logs | 2 | 200, heading |
| Partial: settings | 2 | 200, heading |
| 404 partials | 2 | unknown section → 404, detail message |
| Static file serving | 2 | root index.html, all 5 partials |
| Phase 8.1 compat | 3 | `/api/skills`, `/openapi.json`, `/docs` still work |
| Filesystem checks | 8 | static dir + index.html + partials dir + 5 partial files |

---

## Phase 8.3 — Prompt Playground

Phase 8.3 transforms the Skills page into a fully interactive **Prompt Playground** —
a split-panel interface where you can select any Skill, fill its inputs, choose a model,
run it against the LLM, and immediately see the output alongside token stats.

### Using the Playground

```bash
# Start the web server
harnesskit serve

# Then open http://localhost:7749 in your browser
# → Click the "Skills" nav item (loaded by default)
# → Select any skill from the left panel
# → Fill the input form (generated dynamically from the skill's `inputs` definition)
# → Optionally override the model (e.g. "gpt-4o", "claude-3-5-sonnet")
# → Click ▶ Run
# → Output appears below with model, token counts, and duration
```

### Playground UI layout

```
┌─────────────────────────────────────────────────────────┐
│  Skills Playground                       3 skill(s)      │
│  [Filter skills…]                                        │
├──────────────────┬──────────────────────────────────────┤
│  translate v0.1  │  translate                v0.0.1      │
│  ping v0.0.1     │  Translate text to another language   │
│                  │                                        │
│                  │  Inputs                               │
│                  │  text * — string                      │
│                  │  ┌──────────────────────────────┐    │
│                  │  │ Enter text…                  │    │
│                  │  └──────────────────────────────┘    │
│                  │  target_lang (optional)               │
│                  │  ┌──────────────────────────────┐    │
│                  │  │ English                      │    │
│                  │  └──────────────────────────────┘    │
│                  │  Model                                │
│                  │  [gpt-4o or leave blank for default]  │
│                  │  [ ▶ Run ]                            │
│                  │                                        │
│                  │  Output            gpt-4o  60 tok  1s │
│                  │  ┌──────────────────────────────┐    │
│                  │  │ Hello World in English…      │    │
│                  │  └──────────────────────────────┘    │
└──────────────────┴──────────────────────────────────────┘
```

### Key features

| Feature | Detail |
|---------|--------|
| Dynamic input form | Auto-generated from `skill.inputs` — required/optional labels, type hints, pre-filled defaults |
| Model selector | Free-text input; leave blank to use `.harness/config.yaml` default |
| Live run | Calls `POST /api/skills/{name}/run`; shows spinner while waiting |
| Output panel | Rendered `<pre>` block; token counts (in/out) and duration shown |
| Error display | Missing required inputs → 422 detail; LLM failure → 502 message |
| Skill selector | Left sidebar with search/filter; active skill highlighted |

### Phase 8.3 test coverage

Phase 8.3 ships with **47 pytest tests** in `tests/test_web_playground.py`:

| Class | Tests | What is verified |
|-------|-------|-----------------|
| `TestPlaygroundHTMLStructure` | 19 | form, model selector, run button, output area, Alpine functions, API references, template loop, token stats, `<pre>` element, static file |
| `TestSkillDetailAPI` | 8 | `inputs` field present, required flag, default value, empty inputs list, 404, description, version |
| `TestRunSkillPlayground` | 14 | 404 missing skill, 422 missing required input, 503 no API key, 200 success, output/model/tokens/duration/skill-name fields, model override, optional default filled, no-inputs skill, 502 LLM failure |
| `TestBackwardsCompat` | 6 | Phase 8.1/8.2 API and partials still work |

---

## Phase 8.4 — A/B 对比界面 (A/B Compare)

Phase 8.4 adds a dedicated **A/B Compare** section to the Web Playground, letting you run two
versions of the same skill side-by-side with a single click and immediately see the differences
between their outputs.

```bash
harnesskit serve
# Open http://localhost:7749 → click "Compare" in the left sidebar
```

### Features

- **Skill & version selector** — choose any skill, then pick version A and version B from a dropdown populated by `GET /api/skills/{name}/versions`
- **Shared input form** — one set of inputs drives both runs (dynamically generated from the skill's input definitions, with required/optional/default indicators)
- **Parallel execution** — the `POST /api/compare` endpoint runs both versions concurrently using a `ThreadPoolExecutor` and returns a `CompareResponse{result_a, result_b}` in a single HTTP call
- **Side-by-side output panels** — A (blue) and B (purple) results displayed next to each other with per-run token counts and duration
- **Word-level diff highlighting** — words unique to each side are highlighted green, making differences immediately obvious
- **Model override** — an optional model field lets you override the configured default for both runs

### New API endpoints (Phase 8.4)

| Endpoint | Description |
|----------|-------------|
| `GET /api/skills/{name}/versions` | Returns all available versions for a skill, sorted oldest → newest |
| `POST /api/compare` | Run two skill versions in parallel; body: `{skill, version_a, version_b, inputs, model?}`; returns `{result_a, result_b}` |

### Phase 8.4 test coverage

Phase 8.4 ships with **42 pytest tests** in `tests/test_web_ab_compare.py`:

| Class | Tests | What is verified |
|-------|-------|-----------------|
| `TestListSkillVersions` | 5 | 200 with version list, sort order, single-version skill, 404 missing, JSON content-type |
| `TestCompareEndpoint` | 9 | 200 success, response shape (all 7 fields), correct versions in results, 404 skill/version, 422 missing input, 503 no API key, model override, same-version both sides |
| `TestComparePartialHTMLStructure` | 18 | heading, skill/version-A/version-B selects, input form, model input, run button, output panels A+B, error element, diff legend, API refs, Alpine component, `runCompare`/`diffHtml` functions, file existence |
| `TestBackwardCompat` | 10 | all Phase 8.1/8.2/8.3 routes still work; Compare nav item in index; OpenAPI paths updated |

---

## Phase 8.5 — Eval Dashboard

Phase 8.5 brings a live **Eval Dashboard** to the Web Playground, giving you full visibility into
your test suite health, historical pass-rate trends, and one-click suite runs — all from the browser.

### Using the Eval Dashboard

```bash
harnesskit serve          # start web server (default: http://localhost:7749)
# Click "Eval" in the navigation bar
```

### Dashboard layout

```
┌─────────────────────────────────────────────────────────────────┐
│  Eval Dashboard                                     ↻ Refresh  │
├──────────────┬──────────────┬──────────────────────────────────┤
│  3           │  24          │  2                               │
│  Test Suites │  Passed      │  Failed                          │
├──────────────┴──────────────┴──────────────────────────────────┤
│ Test Suites        [Filter…]  │  Recent Runs                   │
│ ──────────────────────────── │  Time  Target  Suite  Pass Rate │
│ ▸ code-review-suite          │  Mar 25 my-skill basic 2/2 100% │
│   2 cases · 3 assertions     │  Mar 24 my-skill basic 1/2  50% │
│   [Run]                      │                                 │
│ ▸ second-suite               │                                 │
│   1 case · 1 assertion       │                                 │
├──────────────────────────────┴─────────────────────────────────┤
│ Pass-Rate Trend                                 last 8 runs    │
│ ────────────────────────────────────────────────────────────── │
│ 100% ·····●────────────●···                                    │
│  50%                        ●──●                               │
│   0%                                                           │
│      ● green=100%  ● yellow=≥70%  ● red=<70%                  │
└────────────────────────────────────────────────────────────────┘
```

### New API endpoints (Phase 8.5)

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/api/eval/suites` | List all test suites with case/assertion counts |
| `GET` | `/api/eval/suites/{name}` | Get full suite definition |
| `POST` | `/api/eval/suites/{name}/run` | Run suite against a skill (body: `{"target": "skill-name"}`) |
| `GET` | `/api/eval/results` | List recent eval results (query: `limit=20`) |
| `GET` | `/api/eval/trend` | Pass-rate trend points (query: `target`, `suite`, `limit`) |

### Phase 8.5 test coverage

Phase 8.5 ships with **49 pytest tests** in `tests/test_web_eval_dashboard.py`:

| Class | Tests | What's covered |
|-------|-------|----------------|
| `TestListEvalSuites` | 4 | list returns all suites, summary fields (case_count, assertion_count), empty list, JSON content-type |
| `TestGetEvalSuite` | 3 | suite detail, 404 on missing suite, second suite data |
| `TestRunEvalSuite` | 5 | 404 missing suite/skill, 503 no API key, 200 success report shape, result file persisted |
| `TestListEvalResults` | 6 | list, expected fields, summary fields, empty list, limit param, newest-first ordering |
| `TestGetEvalTrend` | 7 | list, trend fields, pass_rate 0–1 range, empty list, target/suite filters, limit param |
| `TestEvalPartialExists` | 2 | file exists, served via `/partials/eval` |
| `TestEvalPartialStructure` | 15 | Alpine component, stats IDs, suite-list ID, search input, results-table ID, trend-chart ID, run-btn/target/error IDs, SVG sparkline, x-init load, API call refs, run method, empty-state, trend legend |
| `TestBackwardsCompatibility` | 7 | Phase 8.1–8.4 API routes and partials still work |

---

## Phase 8.6 — Blueprint Visualization

Phase 8.6 adds a **Blueprint Visualization** panel to the Web Playground, letting you explore
workflow definitions as interactive flow graphs, inspect each step's type and action, and simulate
execution via a step-by-step dry run — all without touching the CLI.

### Using Blueprint Visualization

```bash
harnesskit serve          # start web server (default: http://localhost:7749)
# Click "Blueprints" in the navigation bar
```

### Panel layout

```
┌─────────────────────────────────────────────────────────────────┐
│  Blueprints                                       Phase 8.6    │
├────────────────┬────────────────────────────────────────────────┤
│ Blueprints  2  │  code-review-pipeline  v0.0.1                 │
│ [Search…]      │  Lint then review                             │
│ ─────────────  │  Inputs: file_path *                          │
│ ▸ code-review  │                                               │
│   v0.0.1       ├────────────────────────────────────────────────┤
│   2 steps      │  Flow Graph                                   │
│ ─────────────  │  ▶Start → ⚙ lint → 🤖 review → ⏹End        │
│ ▸ full-pipe    │   (Mermaid.js flowchart LR)                   │
│   v0.0.1       ├────────────────────────────────────────────────┤
│   3 steps      │  Steps                      [▶ Dry Run]      │
│                │  ⬜ lint   deterministic  shell: flake8 …    │
│                │  ⬜ review agentic        skill: code-review… │
│                ├────────────────────────────────────────────────┤
│                │  Outputs                                      │
│                │  lint_result    {{steps.lint.output}}         │
│                │  review_result  {{steps.review.output}}       │
└────────────────┴────────────────────────────────────────────────┘
```

### New API endpoints (Phase 8.6)

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/api/blueprints` | List all blueprints (name, version, description, step_count) |
| `GET` | `/api/blueprints/{name}` | Get full blueprint definition |
| `GET` | `/api/blueprints/{name}/graph` | Get Mermaid flowchart definition |
| `POST` | `/api/blueprints/{name}/dry-run` | Simulate execution — returns step plan with pending status |

### Dry run animation

Clicking **Dry Run** sends a `POST /api/blueprints/{name}/dry-run` request. The panel then
animates through each step (pending → running → done) at 400 ms per step using Alpine.js
reactivity, showing a live walkthrough without calling any LLM.

### Mermaid.js graph

The `GET /api/blueprints/{name}/graph` endpoint returns a `mermaid` field containing a
`flowchart LR` diagram. Edge styles encode `on_fail` modes:

| `on_fail` value | Edge style |
|-----------------|------------|
| `stop` (default) | solid `-->` |
| `continue` | dashed `-.->|on fail: continue|` |
| `goto:<id>` | dual edges: fail goes to target, success continues forward |

### Phase 8.6 test coverage

Phase 8.6 ships with **48 pytest tests** in `tests/test_web_blueprint_viz.py`:

| Class | Tests | What's covered |
|-------|-------|----------------|
| `TestListBlueprints` | 4 | list returns all, metadata fields (name/version/description/step_count), empty list, multiple blueprints |
| `TestGetBlueprint` | 5 | full definition, steps fields, outputs, inputs, 404 on missing |
| `TestGetBlueprintGraph` | 7 | mermaid field, flowchart keyword, step IDs, __START__/__END__, continue on_fail, 404, goto edge |
| `TestDryRunBlueprint` | 7 | step plan, pending status, action field, metadata, 404, type preserved, harness action |
| `TestBlueprintsPartialHTMLStructure` | 16 | all UI element IDs, Mermaid CDN, Alpine component, API refs, dry-run/graph calls, phase badge |
| `TestIndexBlueprintNav` | 3 | "blueprints" in nav, label, Phase 8.6 badge |
| `TestBackwardsCompatibility` | 6 | all Phase 8.1–8.5 routes and partials still work |

---

## Phase 8.7 — MCP Server Export + AGENTS.md Export

Phase 8.7 adds two export commands that make HarnessKit skills available to external AI clients:

- **`harnesskit export agents-md`** — auto-generate an `AGENTS.md` skill directory (≤60 lines)
- **`harnesskit export mcp`** — start an MCP Server exposing all Skills as MCP Tools for Claude Desktop, Cursor, or any MCP-compatible client

### AGENTS.md Generation

```bash
# Print to stdout
harnesskit export agents-md

# Write to file
harnesskit export agents-md --output AGENTS.md
```

The output follows the ETH Zurich research finding that AGENTS.md files exceeding 60 lines
reduce agent performance — the generator enforces a strict 60-line cap and truncates gracefully
if needed.

Example output:

```markdown
# AGENTS.md — HarnessKit Skill Directory

> Auto-generated by `harnesskit export agents-md`. Do not edit manually.

## Skills

- **code-reviewer** (`v0.1.0`): Reviews code for bugs and style issues
  Trigger: _when reviewing a PR_ | Docs: `.harness/skills/code-reviewer/v0.1.0.yaml`
- **summarizer** (`v0.2.0`): Summarizes long text | Docs: `.harness/skills/summarizer/v0.2.0.yaml`

## Harnesses

- **full-review** (`v0.1.0`): Complete review workflow
  Skills: code-reviewer@v0.1.0, summarizer@v0.2.0
```

Regenerate whenever you update skills:

```bash
harnesskit export agents-md --output AGENTS.md
```

### MCP Server

```bash
# Install MCP dependency
pip install 'harness-kit[mcp]'

# Start the MCP stdio server
harnesskit export mcp
```

All registered Skills are exposed as MCP Tools.  Each tool's input schema is derived from
the skill's `inputs` definition.  When called, the skill runs through the configured LLM
(same pipeline as `harnesskit skill run`).

**Claude Desktop configuration** (`~/.claude/claude_desktop_config.json`):

```json
{
  "mcpServers": {
    "harnesskit": {
      "command": "harnesskit",
      "args": ["export", "mcp"],
      "cwd": "/path/to/your/project"
    }
  }
}
```

**Cursor configuration** (`.cursor/mcp.json`):

```json
{
  "mcpServers": {
    "harnesskit": {
      "command": "harnesskit",
      "args": ["export", "mcp"]
    }
  }
}
```

### New CLI commands (Phase 8.7)

| Command | Description |
|---------|-------------|
| `harnesskit export agents-md` | Generate AGENTS.md (≤60 lines, stdout or `--output FILE`) |
| `harnesskit export mcp` | Start MCP stdio server exposing all Skills as MCP Tools |

### Phase 8.7 test coverage

Phase 8.7 ships with **18 pytest tests** in `tests/test_export.py`:

| Group | Tests | What's covered |
|-------|-------|----------------|
| `generate_agents_md` | 7 | empty harness, skills section, harnesses section, both sections, 60-line cap, no-trigger skill, many-skill harness truncation |
| `_build_input_schema` | 4 | empty inputs, required field, optional with default, type mapping (int/float/bool/array) |
| CLI `export agents-md` | 4 | stdout output, file write, empty harness, line count |
| CLI `export mcp` | 1 | missing mcp package → exit 1 with helpful message |
| `build_mcp_server` | 2 | ImportError path, mock mcp server construction |

---

## Phase 8.8 — Skills Registry

Phase 8.8 adds a **local Skills Registry** backed by `~/.harnesskit/registry.json`, plus three new
`harnesskit skill` sub-commands: `search`, `install`, and `publish`.  Skills can be packaged as
`.hsk` archives (zip bundles that include all asset dependencies) and shared across machines or
teammates.

### Skills Registry overview

```
~/.harnesskit/registry.json
  {
    "code-reviewer": {
      "name": "code-reviewer",
      "version": "v0.1.0",
      "source": "/path/to/code-reviewer.yaml",
      "description": "Review code for bugs and style issues",
      "tags": ["code", "review"],
      "installed_at": "2026-03-25T10:00:00+00:00"
    }
  }
```

The registry is a simple JSON file in your home directory — no server required.

### New CLI commands (Phase 8.8)

#### `harnesskit skill search <keyword>`

Search the local registry by name, description, or tag (case-insensitive):

```bash
harnesskit skill search code
# ┌────────────────┬─────────┬─────────────────────────────┬─────────┐
# │ Name           │ Version │ Description                 │ Source  │
# ├────────────────┼─────────┼─────────────────────────────┼─────────┤
# │ code-reviewer  │ v0.1.0  │ Review code for bugs        │ local   │
# └────────────────┴─────────┴─────────────────────────────┴─────────┘
```

#### `harnesskit skill install <source>`

Install a skill from multiple source types:

```bash
# From a local YAML file
harnesskit skill install ./my-skill.yaml

# From a .hsk package
harnesskit skill install my-skill-v0.1.0.hsk

# From a GitHub URL
harnesskit skill install github:anthropics/harnesskit-skills/main/code-reviewer/skill.yaml
```

After installation, the skill is registered in `~/.harnesskit/registry.json`.

#### `harnesskit skill publish <name>`

Package a skill and all its dependencies (prompts, schemas, rules, contexts) into a `.hsk` archive:

```bash
harnesskit skill publish code-reviewer
# ✓ Published: /path/to/code-reviewer-v0.1.0.hsk
#   Package contains skill + all asset dependencies.
#   Share and install with: harnesskit skill install code-reviewer-v0.1.0.hsk

# Publish a specific version to a custom output directory
harnesskit skill publish code-reviewer --version v0.1.0 --output ./dist/
```

The `.hsk` format is a standard zip archive containing:
- `manifest.json` — metadata (skill name, version, packaged_at, file list)
- `skills/{name}/{version}.yaml` — the skill definition
- `prompts/{name}/{version}.yaml` — bundled prompts (if any)
- `schemas/{name}/{version}.json` — bundled schemas (if any)
- `rules/{name}.yaml` — bundled rules (if any)
- `contexts/{name}/{version}.yaml` — bundled contexts (if any)

### Phase 8.8 test coverage

Phase 8.8 ships with **36 pytest tests** in `tests/test_registry.py`:

| Test class | Tests | What is covered |
|---|---|---|
| `TestRegistry` | 11 | register, unregister, list, search by name/description/tag, persistence |
| `TestPublish` | 6 | creates .hsk file, valid zip, manifest fields, skill yaml inside, unknown skill error, bundled rule |
| `TestInstallFromYaml` | 4 | creates skill, registers in registry, missing file error, unsupported extension error |
| `TestInstallFromHsk` | 2 | full roundtrip publish→install, _current marker written |
| `TestResolveRawUrl` | 3 | github: shorthand, https:// passthrough, invalid github: format |
| `TestCliSearch` | 3 | empty registry, finds registered skill, no-match tip |
| `TestCliInstall` | 3 | install from yaml, missing file exit 1, registers in registry |
| `TestCliPublish` | 3 | creates package, unknown skill exit 1, output contains .hsk hint |

---

## Roadmap

See [ROADMAP.md](ROADMAP.md) for the full 8-phase development plan.

Current status: **Phase 8.8 complete** — Skills Registry — 3 new CLI commands (`skill search`, `skill install`, `skill publish`), 36 new tests all passing.
