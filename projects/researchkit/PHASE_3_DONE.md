# Phase 3 完成报告

**完成时间**：2026-03-27

## 新增功能

### FastAPI 后端 (`web/backend/`)
- `main.py` — FastAPI 应用主入口
  - 任务管理 CRUD：`GET/POST /api/tasks`、`GET/DELETE /api/tasks/{id}`
  - 任务运行：`POST /api/tasks/{id}/run`（异步 Pipeline 执行）
  - 报告获取：`GET /api/tasks/{id}/report`
  - 数据源状态：`GET /api/sources`
  - 模板管理：`GET/PUT /api/templates/{id}`
  - WebSocket 实时进度：`ws://localhost:8000/ws/tasks/{id}`
  - 生产模式自动挂载前端静态文件
- `schemas.py` — Pydantic 数据模型（TaskCreate、TaskResponse、SourceStatusResponse）
- `storage.py` — 线程安全 JSON 文件存储（Phase 4 将迁移至 SQLite）

### Vue 3 前端 (`web/frontend/`)
技术栈：Vue 3 + Element Plus + Pinia + Vite + Axios + Marked

**页面**：
- `Dashboard.vue` — 任务数据概览（统计卡片 + 任务列表）
- `NewTask.vue` — 三步引导式新建调研（基本信息 → 数据来源 → 输出配置）
- `TaskProgress.vue` — 实时进度（WebSocket + 三阶段进度条 + 日志流）
- `ReportView.vue` — Markdown 报告渲染（代码高亮 + 目录导航 + 复制/下载）
- `Sources.vue` — 数据源状态管理
- `Templates.vue` — 报告模板在线编辑

**配置**：
- `vite.config.js` — 开发代理（/api → :8000，/ws → ws://:8000）
- `router/index.js` — Vue Router 路由配置
- `stores/tasks.js` — Pinia 任务状态管理
- `api.js` — Axios 封装（含 JWT 拦截器，Phase 4 启用）

### 测试
- `tests/test_phase3.py` — 16 个测试，全部通过

## 启动方式

```bash
# 后端
cd projects/researchkit
.venv/bin/uvicorn web.backend.main:app --reload --port 8000

# 前端（开发）
cd web/frontend
npm install && npm run dev   # http://localhost:5173
```

## 验收状态
✅ 47/47 测试通过（Phase 1+2+3）
