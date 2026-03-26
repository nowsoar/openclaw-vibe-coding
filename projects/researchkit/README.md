# ResearchKit

> AI 驱动的自动化调研平台 — 配置数据源，描述研究目标，一键生成报告。

## 快速上手

```bash
# 安装
git clone https://github.com/nowsoar/openclaw-vibe-coding.git
cd openclaw-vibe-coding/projects/researchkit
pip install -e .

# 初始化
researchkit init

# 配置 AI 接口（编辑 ~/.researchkit/config.yaml）
# 配置数据源（编辑 ~/.researchkit/sources.yaml）

# 运行第一次调研
researchkit run examples/tasks/ai_tools_research.yaml
```

## 架构

```
用户调研需求 (task.yaml)
        ↓
  数据源并行抓取
  ├── 微信公众号
  ├── RSS 订阅
  └── 指定网站
        ↓
  处理流水线（可配置）
  ├── 关键词过滤
  ├── 去重
  ├── AI 相关性过滤
  └── AI 摘要生成
        ↓
  AI 报告合成（按模板结构）
        ↓
  输出：Markdown / 飞书 / PDF
```

## 配置说明

详见 [examples/](examples/) 目录，包含完整的配置示例。

## 开发路线图

详见 [ROADMAP.md](ROADMAP.md)
