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
| `harnesskit blueprint validate <name>` | Validate structure + variable refs |
| `harnesskit blueprint delete <name[@ver]>` | Delete a blueprint |

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

### Variable Interpolation

| Syntax | Meaning |
|--------|---------|
| `{{inputs.file_path}}` | Blueprint-level input value |
| `{{steps.lint.output}}` | stdout / result of the `lint` step |
| `{{steps.lint.exit_code}}` | Exit code of a deterministic step |
| `{{env.MY_VAR}}` | Environment variable (Phase 4.5) |

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

## Roadmap

See [ROADMAP.md](ROADMAP.md) for the full 8-phase development plan.

Current status: **Phase 4.1 complete** — Blueprint YAML format, versioned storage, and CLI commands (`create`, `show`, `list`, `diff`, `validate`, `delete`): supports deterministic + agentic step types, variable interpolation syntax (`{{steps.xxx.output}}`), and structural/reference validation. 43 new pytest tests (715 total) all passing.
