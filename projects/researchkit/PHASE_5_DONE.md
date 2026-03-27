# Phase 5 完成报告

**完成时间**：2026-03-27

## 新增功能

### 定时调度 (`web/backend/scheduler.py`)
- `ResearchScheduler` — APScheduler `BackgroundScheduler` 封装
- `add_task(task_id, task_config, cron_expr, incremental, notification_config)` — 添加 Cron 定时任务
- `remove_task / pause_task / resume_task / trigger_now` — 任务生命周期管理
- 调度配置持久化到 `~/.researchkit/schedules.json`，进程重启后自动恢复 (`_restore_schedules`)
- 模块级单例 `scheduler = ResearchScheduler()`，供 FastAPI lifespan 使用

### 通知推送 (`web/backend/notifications.py`)
- `NotificationService` — 统一多渠道通知服务
- 支持：飞书机器人 Webhook（富文本卡片）/ 通用 Webhook（POST JSON）/ SMTP 邮件
- 单个渠道失败不影响其他渠道（静默降级）

### 插件机制 (`researchkit/plugins/__init__.py`)
- `PluginType` 枚举：SOURCE / PROCESSOR / OUTPUT
- `register_plugin(type, name)` 装饰器：内联注册自定义插件
- `get_plugin / list_plugins` — 查找与枚举插件（支持 `importlib.metadata` 入口点）
- 内置插件自动注册：4 个 source / 7 个 processor / 3 个 output

### 调度 API 路由 (`web/backend/main.py`)
- `GET /api/schedules` — 列出所有定时任务
- `POST /api/schedules` — 创建定时任务（body: task_id, task_config, cron_expr, incremental）
- `GET /api/schedules/{task_id}` — 获取单个任务详情
- `DELETE /api/schedules/{task_id}` — 删除定时任务
- `POST /api/schedules/{task_id}/pause` — 暂停
- `POST /api/schedules/{task_id}/resume` — 恢复
- `POST /api/schedules/{task_id}/trigger` — 立即触发一次
- `GET /api/plugins` — 列出所有已注册插件

### CLI 调度命令 (`researchkit/cli.py`)
- `researchkit schedule-add <task.yaml> --cron "0 8 * * *"` — 添加定时任务
- `researchkit schedule-list` — 列出所有定时任务
- `researchkit schedule-remove <task_id>` — 删除定时任务
- `researchkit schedule-trigger <task_id>` — 立即触发
- `researchkit plugins` — 列出所有插件

### 测试 (`tests/test_phase5.py`)
- 26 个测试，全部通过
  - 调度器单元测试：10 个（启动/添加/持久化/删除/恢复/触发/pause-resume）
  - 通知服务测试：4 个（飞书/Webhook/失败降级）
  - 插件注册表测试：5 个（内置注册/装饰器/get/list）
  - API 路由测试：7 个（CRUD + 插件端点）

## 技术说明
- APScheduler `BackgroundScheduler`（线程池，timezone=Asia/Shanghai）
- 调度配置使用线程安全 JSON 文件持久化（与 Phase 3 TaskStore 模式一致）
- 插件支持两种发现方式：装饰器内联注册 + `pyproject.toml` 入口点声明
- 通知使用标准库 `urllib.request`（无额外依赖）

## 验收状态
✅ 89/89 测试通过（Phase 1+2+3+4+5）
