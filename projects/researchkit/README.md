# ResearchKit

> AI-powered automated research platform — configure data sources, describe your research goal, generate reports automatically.

[中文文档](README_CN.md)

---

## Features

- **Multi-source collection** — WeChat Official Accounts, RSS feeds, custom websites, Xiaohongshu (Little Red Book)
- **Configurable pipeline** — keyword filter → deduplication → AI relevance scoring → AI summarization → quality scoring → citation validation
- **AI report synthesis** — structured reports generated from YAML templates (competitor analysis, market research, trend reports, and more)
- **Multiple output formats** — Markdown, Feishu (Lark) Docs, PDF
- **Web UI** — FastAPI backend + Vue 3 frontend with real-time WebSocket progress
- **User authentication** — JWT login/registration, per-user data isolation
- **Scheduled tasks** — cron-based scheduling with Feishu/Webhook/email notifications
- **Plugin system** — register custom sources, processors, and outputs via decorator or `pyproject.toml` entry points

---

## Quick Start

```bash
# Clone
git clone https://github.com/nowsoar/openclaw-vibe-coding.git
cd openclaw-vibe-coding/projects/researchkit

# Install
pip install -e ".[all]"

# Initialize config files
researchkit init

# Edit ~/.researchkit/config.yaml (AI API key, model, cost limit)
# Edit ~/.researchkit/sources.yaml (data source credentials)

# Run your first research task
researchkit run examples/tasks/ai_tools_research.yaml
```

---

## Installation

### Requirements

- Python 3.10+
- (Optional) Node.js 18+ for the Web UI frontend

### Install options

```bash
# Core only
pip install -e .

# With PDF output support
pip install -e ".[pdf]"

# With Xiaohongshu source (requires Playwright)
pip install -e ".[xiaohongshu]"
playwright install chromium

# With Web UI backend
pip install -e ".[web]"

# Everything
pip install -e ".[all]"
```

---

## Configuration

ResearchKit uses a two-level configuration system:

### 1. Global config (`~/.researchkit/config.yaml`)

```yaml
ai:
  api_key: ${OPENAI_API_KEY}       # or set directly
  base_url: https://api.openai.com/v1
  default_model: gpt-4o-mini
  cost_limit_usd: 5.0              # abort if estimated cost exceeds this

output:
  dir: ~/Documents/research/

cache:
  enabled: true
  ttl_days: 3
```

### 2. Data source credentials (`~/.researchkit/sources.yaml`)

```yaml
wechat:
  cookie: "..."                    # WeChat MP backend cookie
  token: "569349538"

rss: {}                            # no auth needed

web:
  headers:
    User-Agent: "Mozilla/5.0 ..."
```

### 3. Task file (`your_task.yaml`)

```yaml
topic: "AI Agent frameworks comparison 2026"
date_range: 7d

sources:
  - type: wechat
    accounts: [量子位, 机器之心, 极客公园]
  - type: rss
    feeds:
      - https://rsshub.app/hackernews/best

pipeline:
  - keyword_filter:
      keywords: [AI, Agent, LLM]
  - deduplicator
  - ai_relevance:
      threshold: 0.6
  - ai_summarize

template: templates/market_research.yaml

output:
  - markdown
  - feishu
```

---

## CLI Reference

```bash
researchkit init                          # initialize config files
researchkit run <task.yaml>               # run a research task
researchkit check-sources                 # verify data source credentials
researchkit history                       # show past runs
researchkit plugins                       # list registered plugins

# Scheduling
researchkit schedule-add <task.yaml> --cron "0 8 * * *"
researchkit schedule-list
researchkit schedule-remove <task_id>
researchkit schedule-trigger <task_id>
```

---

## Web UI

### Start backend

```bash
cd projects/researchkit
.venv/bin/uvicorn web.backend.main:app --reload --port 8000
```

### Start frontend (development)

```bash
cd web/frontend
npm install
npm run dev        # http://localhost:5173
```

### Build frontend (production)

```bash
npm run build      # outputs to web/frontend/dist/
# FastAPI will serve static files automatically in production
```

### API endpoints

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/api/auth/register` | Register new user |
| `POST` | `/api/auth/token` | Login (returns JWT) |
| `GET` | `/api/tasks` | List tasks |
| `POST` | `/api/tasks` | Create task |
| `POST` | `/api/tasks/{id}/run` | Run task |
| `GET` | `/api/tasks/{id}/report` | Get report |
| `WS` | `/ws/tasks/{id}` | Real-time progress |
| `GET` | `/api/schedules` | List scheduled tasks |
| `POST` | `/api/schedules` | Create schedule |
| `GET` | `/api/plugins` | List plugins |

---

## Built-in Plugins

### Sources

| Name | Description |
|------|-------------|
| `wechat` | WeChat Official Accounts (cookie-based) |
| `rss` | RSS / Atom feeds |
| `web` | Custom websites (HTML scraping) |
| `xiaohongshu` | Xiaohongshu / Little Red Book (Playwright + cookie) |

### Processors

| Name | Description |
|------|-------------|
| `keyword_filter` | Filter by keyword whitelist/blacklist |
| `deduplicator` | Remove duplicate articles by URL/title |
| `content_fetcher` | Fetch full article body |
| `ai_relevance` | AI-based relevance scoring (threshold filter) |
| `ai_summarize` | AI-generated article summaries |
| `quality_scorer` | Content quality scoring (rule/AI/hybrid) |
| `reference_validator` | Validate source URLs are accessible |

### Outputs

| Name | Description |
|------|-------------|
| `markdown` | Markdown report file |
| `feishu` | Feishu (Lark) cloud document |
| `pdf` | PDF report (weasyprint / reportlab) |

---

## Custom Plugins

```python
from researchkit.plugins import register_plugin, PluginType
from researchkit.sources.base import BaseSource

@register_plugin(PluginType.SOURCE, "my_source")
class MySource(BaseSource):
    async def fetch(self, config: dict) -> list[dict]:
        ...
```

Or declare via `pyproject.toml`:

```toml
[project.entry-points."researchkit.sources"]
my_source = "my_package.sources:MySource"
```

---

## Built-in Templates

| Template | Description |
|----------|-------------|
| `competitor_analysis.yaml` | Competitor landscape analysis |
| `market_research.yaml` | Market sizing and trends |
| `trend_report.yaml` | Emerging technology trends |
| `user_research.yaml` | User behavior and needs |
| `tech_review.yaml` | Technical evaluation report |
| `policy_analysis.yaml` | Policy and regulatory analysis |

---

## Project Structure

```
researchkit/
├── researchkit/          # Core library
│   ├── core/             # Data models, config, pipeline
│   ├── sources/          # Data source plugins
│   ├── processors/       # Pipeline processor plugins
│   ├── outputs/          # Output format plugins
│   └── plugins/          # Plugin registry
├── web/
│   ├── backend/          # FastAPI application
│   │   ├── main.py
│   │   ├── routers/auth.py
│   │   ├── scheduler.py
│   │   └── notifications.py
│   └── frontend/         # Vue 3 application
│       └── src/views/    # Dashboard, NewTask, TaskProgress, ReportView, ...
├── templates/            # Report structure templates (YAML)
├── examples/             # Config and task examples
└── tests/                # Test suite (89 tests)
```

---

## Development

```bash
# Run tests
pytest tests/ -v

# Run specific phase tests
pytest tests/test_phase2.py -v

# Type checking (optional)
mypy researchkit/
```

---

## Roadmap

See [ROADMAP.md](ROADMAP.md) for the full development roadmap.

- ✅ Phase 1 — Core pipeline (sources → processors → Markdown report)
- ✅ Phase 2 — Xiaohongshu, quality scoring, Feishu/PDF output, more templates
- ✅ Phase 3 — Web UI (FastAPI + Vue 3 + WebSocket)
- ✅ Phase 4 — User authentication, JWT, data isolation
- ✅ Phase 5 — Scheduled tasks, notifications, plugin ecosystem

---

## License

MIT
