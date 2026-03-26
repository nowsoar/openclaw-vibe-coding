# ResearchKit — 开发路线图

> **定位**：动态信息源配置 × AI 驱动的自动化调研平台
> **使命**：配置数据从哪来、研究什么、结果长什么样，系统自动完成全流程

---

## Phase 1：MVP 核心流水线 ✅

**目标**：跑通从数据源到 Markdown 报告的完整链路

- [x] 核心数据模型（Article / ResearchContext / ResearchTask）
- [x] 配置系统（config.yaml + task.yaml 双层配置）
- [x] 数据源：微信公众号 / RSS / 指定网站
- [x] 处理器：关键词过滤 / 去重 / AI 相关性 / AI 摘要
- [x] 报告模板系统（YAML 定义章节结构）
- [x] Markdown 报告输出（AI 合成完整报告）
- [x] CLI：init / run / check-sources / history
- [x] 基础测试套件

**验收标准**：`researchkit run task.yaml` 能生成完整 Markdown 报告

---

## Phase 2：小红书 + 质量提升

**目标**：接入小红书，提升报告质量

- [ ] 小红书数据源（Playwright + Cookie 模式）
- [ ] 正文补充抓取（对有价值的文章获取全文）
- [ ] 更多报告模板（用户研究、技术评测、政策分析）
- [ ] 模板在线编辑（支持用户自定义 AI Prompt）
- [ ] 引用验证（确认来源链接可访问）
- [ ] 内容质量评分（自动判断文章信息密度）
- [ ] 飞书文档输出
- [ ] PDF 输出

---

## Phase 3：Web 前端（Vue 3 + FastAPI）

**目标**：提供可视化界面，无需命令行即可使用

前端技术栈：Vue 3 + Element Plus + Pinia + Vite
后端：FastAPI + WebSocket（实时进度推送）

- [ ] FastAPI 后端服务
  - 任务管理 CRUD API
  - 数据源状态 API
  - WebSocket 实时进度推送
- [ ] 前端页面
  - Dashboard（数据概览）
  - 新建调研（三步引导式表单）
  - 任务运行进度（实时进度条 + 日志流）
  - 报告查看（Markdown 渲染 + 目录导航）
  - 数据源管理（状态检查 + 账号管理）
  - 报告模板管理

---

## Phase 4：用户注册登录 + 多用户支持

**目标**：支持多用户使用，数据隔离

- [ ] 数据库迁移：SQLite → PostgreSQL（多用户需要）
- [ ] 用户表设计（User / Organization）
- [ ] JWT 认证（注册 / 登录 / 刷新 Token）
- [ ] 邮箱注册 + 密码重置
- [ ] Google OAuth 登录
- [ ] 飞书 OAuth 登录
- [ ] 数据隔离（每个用户的任务/数据源/报告独立）
- [ ] 权限控制（个人版 / 团队版）

---

## Phase 5：定时任务 + 团队协作 + 插件生态

**目标**：支持自动化运行，建立社区生态

- [ ] 定时调研（Cron 配置，自动运行）
- [ ] 增量更新（追加新内容到已有报告）
- [ ] 事件触发（关键词热度突增时触发调研）
- [ ] 团队共享（调研任务 / 模板 / 数据源共享）
- [ ] 通知推送（飞书 / 邮件 / Webhook）
- [ ] 插件机制（社区贡献新数据源 / 处理器）
- [ ] 数据源插件市场（知乎、B站、Twitter 等）
- [ ] 报告模板市场（各行业专业模板）

---

## 技术架构总览

```
researchkit/
├── researchkit/
│   ├── core/          ← 数据模型、配置、流水线调度
│   ├── sources/       ← 数据源插件（每个文件一个平台）
│   ├── processors/    ← 流水线处理器插件
│   └── outputs/       ← 输出格式插件
├── templates/         ← 报告结构模板（YAML）
├── examples/          ← 配置示例
└── tests/             ← 测试套件
```

## 可配置维度

| 维度 | 配置文件 | 说明 |
|------|----------|------|
| AI 接口 + 成本控制 | config.yaml | 全局，配一次 |
| 数据源账号认证 | sources.yaml | 偶尔维护 |
| 调研主题 + 来源 | task.yaml | 每次调研必填 |
| 处理流水线 | task.yaml | 每次可调整 |
| 报告结构 + AI Prompt | templates/*.yaml | 做好后复用 |
| 输出格式 | task.yaml | 每次选择 |
