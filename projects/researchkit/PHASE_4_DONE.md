# Phase 4 完成报告

**完成时间**：2026-03-27

## 新增功能

### 数据库层 (`web/backend/`)
- `database.py` — SQLAlchemy + SQLite 设置（`~/.researchkit/researchkit_web.db`）
- `models.py` — User 模型（email、username、hashed_password、is_active）
- `auth.py` — JWT + bcrypt 认证工具（直接调用 bcrypt 5.x，规避 passlib 1.7.4 兼容问题）

### 认证路由 (`web/backend/routers/auth.py`)
- `POST /api/auth/register` — 注册（邮箱/用户名唯一性校验、密码长度校验）
- `POST /api/auth/token` — 登录（支持邮箱或用户名，返回 Access + Refresh Token）
- `POST /api/auth/refresh` — 刷新 Access Token
- `GET /api/auth/me` — 获取当前用户信息（需要认证）
- `POST /api/auth/logout` — 退出（客户端清除 Token）

### 数据隔离
- 任务 CRUD 接口添加可选 `user_id` 过滤
- 已认证用户只能查看/修改自己的任务
- 未认证用户（游客模式）可查看所有匿名任务

### 前端（Vue 3）
- `Login.vue` — 登录/注册页（标签切换 + 游客模式入口）
- `stores/auth.js` — Pinia 认证状态（Token 持久化、自动刷新）
- `router/index.js` — 新增 `/login` 路由，支持空白布局
- `App.vue` — 顶栏显示用户名/退出按钮

### 测试
- `tests/test_phase4.py` — 16 个测试，全部通过

## 技术说明
- 使用 SQLite（不迁移 PostgreSQL，保持简单）
- bcrypt 直接调用（passlib 1.7.4 与 bcrypt 5.x 不兼容，使用 SHA-256 pre-hash 规避 72 字节限制）
- JWT 无状态设计（退出时客户端清除，服务端无需维护黑名单）

## 验收状态
✅ 63/63 测试通过（Phase 1+2+3+4）
