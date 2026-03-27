# ResearchKit

> AI 驱动的自动化调研平台 — 配置数据源，描述研究目标，一键生成报告。

[English Documentation](README.md)

---

## 功能特性

- **多源数据采集** — 微信公众号、RSS 订阅、指定网站、小红书
- **可配置处理流水线** — 关键词过滤 → 去重 → AI 相关性评分 → AI 摘要 → 质量评分 → 引用验证
- **AI 报告合成** — 基于 YAML 模板生成结构化报告（竞品分析、市场调研、趋势报告等）
- **多种输出格式** — Markdown、飞书云文档、PDF
- **Web 可视化界面** — FastAPI 后端 + Vue 3 前端，WebSocket 实时推送进度
- **用户认证系统** — JWT 登录/注册，用户数据隔离
- **定时任务** — Cron 调度，支持飞书 / Webhook / 邮件通知
- **插件机制** — 通过装饰器或 `pyproject.toml` 入口点注册自定义数据源、处理器、输出格式

---

## 快速上手

```bash
# 克隆项目
git clone https://github.com/nowsoar/openclaw-vibe-coding.git
cd openclaw-vibe-coding/projects/researchkit

# 安装
pip install -e ".[all]"

# 初始化配置文件
researchkit init

# 编辑 ~/.researchkit/config.yaml（AI 接口密钥、模型、费用限额）
# 编辑 ~/.researchkit/sources.yaml（数据源账号凭证）

# 运行第一次调研
researchkit run examples/tasks/ai_tools_research.yaml
```

---

## 安装说明

### 环境要求

- Python 3.10+
- （可选）Node.js 18+，用于 Web 前端

### 安装选项

```bash
# 仅核心功能
pip install -e .

# 含 PDF 输出
pip install -e ".[pdf]"

# 含小红书数据源（需要 Playwright）
pip install -e ".[xiaohongshu]"
playwright install chromium

# 含 Web 界面后端
pip install -e ".[web]"

# 安装全部功能
pip install -e ".[all]"
```

---

## 配置说明

ResearchKit 采用两层配置体系：

### 1. 全局配置（`~/.researchkit/config.yaml`）

```yaml
ai:
  api_key: ${OPENAI_API_KEY}       # 或直接填写
  base_url: https://api.openai.com/v1
  default_model: gpt-4o-mini
  cost_limit_usd: 5.0              # 预估费用超限时中止

output:
  dir: ~/Documents/research/

cache:
  enabled: true
  ttl_days: 3
```

### 2. 数据源凭证（`~/.researchkit/sources.yaml`）

```yaml
wechat:
  cookie: "..."                    # 微信公众号后台 Cookie
  token: "569349538"

rss: {}                            # 无需认证

web:
  headers:
    User-Agent: "Mozilla/5.0 ..."
```

### 3. 调研任务文件（`your_task.yaml`）

```yaml
topic: "2026年 AI Agent 框架对比分析"
date_range: 7d

sources:
  - type: wechat
    accounts: [量子位, 机器之心, 极客公园]
  - type: rss
    feeds:
      - https://rsshub.app/hackernews/best

pipeline:
  - keyword_filter:
      keywords: [AI, Agent, 大模型]
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

## CLI 命令参考

```bash
researchkit init                          # 初始化配置文件
researchkit run <task.yaml>               # 运行调研任务
researchkit check-sources                 # 验证数据源可用性
researchkit history                       # 查看历史运行记录
researchkit plugins                       # 列出已注册插件

# 定时任务
researchkit schedule-add <task.yaml> --cron "0 8 * * *"
researchkit schedule-list
researchkit schedule-remove <task_id>
researchkit schedule-trigger <task_id>
```

---

## Web 界面

### 启动后端

```bash
cd projects/researchkit
.venv/bin/uvicorn web.backend.main:app --reload --port 8000
```

### 启动前端（开发模式）

```bash
cd web/frontend
npm install
npm run dev        # 访问 http://localhost:5173
```

### 构建前端（生产模式）

```bash
npm run build      # 输出到 web/frontend/dist/
# 生产模式下 FastAPI 自动托管静态文件
```

### API 接口一览

| 方法 | 路径 | 说明 |
|------|------|------|
| `POST` | `/api/auth/register` | 注册新用户 |
| `POST` | `/api/auth/token` | 登录（返回 JWT）|
| `GET` | `/api/tasks` | 获取任务列表 |
| `POST` | `/api/tasks` | 创建调研任务 |
| `POST` | `/api/tasks/{id}/run` | 执行任务 |
| `GET` | `/api/tasks/{id}/report` | 获取报告 |
| `WS` | `/ws/tasks/{id}` | 实时进度推送 |
| `GET` | `/api/schedules` | 列出定时任务 |
| `POST` | `/api/schedules` | 创建定时任务 |
| `GET` | `/api/plugins` | 列出已注册插件 |

---

## 内置插件

### 数据源（Sources）

| 名称 | 说明 |
|------|------|
| `wechat` | 微信公众号（Cookie 模式）|
| `rss` | RSS / Atom 订阅源 |
| `web` | 自定义网站（HTML 抓取）|
| `xiaohongshu` | 小红书（Playwright + Cookie）|

### 处理器（Processors）

| 名称 | 说明 |
|------|------|
| `keyword_filter` | 关键词白名单/黑名单过滤 |
| `deduplicator` | 按 URL/标题去重 |
| `content_fetcher` | 抓取文章正文 |
| `ai_relevance` | AI 相关性评分（阈值过滤）|
| `ai_summarize` | AI 摘要生成 |
| `quality_scorer` | 内容质量评分（规则/AI/混合）|
| `reference_validator` | 验证来源链接可访问性 |

### 输出格式（Outputs）

| 名称 | 说明 |
|------|------|
| `markdown` | Markdown 报告文件 |
| `feishu` | 飞书云文档 |
| `pdf` | PDF 报告（weasyprint / reportlab）|

---

## 自定义插件

```python
from researchkit.plugins import register_plugin, PluginType
from researchkit.sources.base import BaseSource

@register_plugin(PluginType.SOURCE, "my_source")
class MySource(BaseSource):
    async def fetch(self, config: dict) -> list[dict]:
        ...
```

或在 `pyproject.toml` 中声明入口点：

```toml
[project.entry-points."researchkit.sources"]
my_source = "my_package.sources:MySource"
```

---

## 内置报告模板

| 模板 | 说明 |
|------|------|
| `competitor_analysis.yaml` | 竞品格局分析 |
| `market_research.yaml` | 市场规模与趋势 |
| `trend_report.yaml` | 新兴技术趋势 |
| `user_research.yaml` | 用户行为与需求 |
| `tech_review.yaml` | 技术评测报告 |
| `policy_analysis.yaml` | 政策与监管分析 |

---

## 项目结构

```
researchkit/
├── researchkit/          # 核心库
│   ├── core/             # 数据模型、配置、流水线调度
│   ├── sources/          # 数据源插件
│   ├── processors/       # 处理器插件
│   ├── outputs/          # 输出格式插件
│   └── plugins/          # 插件注册表
├── web/
│   ├── backend/          # FastAPI 应用
│   │   ├── main.py
│   │   ├── routers/auth.py
│   │   ├── scheduler.py
│   │   └── notifications.py
│   └── frontend/         # Vue 3 应用
│       └── src/views/    # Dashboard、NewTask、TaskProgress、ReportView...
├── templates/            # 报告结构模板（YAML）
├── examples/             # 配置与任务示例
└── tests/                # 测试套件（89 个测试）
```

---

## 开发

```bash
# 运行全部测试
pytest tests/ -v

# 按 Phase 运行测试
pytest tests/test_phase2.py -v

# 类型检查（可选）
mypy researchkit/
```

---

## 开发路线图

完整路线图详见 [ROADMAP.md](ROADMAP.md)。

- ✅ Phase 1 — 核心流水线（数据源 → 处理器 → Markdown 报告）
- ✅ Phase 2 — 小红书、质量评分、飞书/PDF 输出、更多模板
- ✅ Phase 3 — Web 界面（FastAPI + Vue 3 + WebSocket）
- ✅ Phase 4 — 用户认证、JWT、数据隔离
- ✅ Phase 5 — 定时任务、通知推送、插件生态

---

## 许可证

MIT
