# HarnessKit — 详细开发路线图

> **定位**：本地 AI Harness 工程工具箱  
> **使命**：让开发者像管理代码一样管理 AI Agent 的「操作系统层」  
> **核心公式**：`coding agent = AI model(s) + harness`

---

## 技术架构总览

```
Agent（持续角色）
  └── Harness（完整运行时配置）
        ├── Skills（可复用能力单元）
        │     ├── Prompt（系统/用户提示词）
        │     ├── Schema（Function calling 工具定义）
        │     ├── Rule（约束规则）
        │     └── Context（上下文模板）
        ├── Model Config（模型参数）
        ├── Memory Policy（记忆策略）
        └── Constraints（全局约束）

Blueprint（工作流编排）
  └── [确定性节点] → [Harness] → [确定性节点] → ...

横切关注点：
  - Observability（调用日志、成本追踪）
  - Improvement Flywheel（自改进飞轮）
  - Skills Registry（技能市场）
```

---

## Phase 1：基础架构与 Primitive Assets

**目标**：建立项目骨架，实现四类原子资产的 CRUD 和版本管理。

### Phase 1.1：项目初始化 ✅
**任务**：
1. 创建项目目录结构
   - `harness_kit/` —— Python 包
   - `tests/` —— 测试目录
   - `pyproject.toml` —— 包配置
   - `README.md` —— 项目介绍

2. 实现 `harnesskit init` 命令
   - 在用户当前目录创建 `.harness/` 目录
   - 子目录结构：`prompts/`, `schemas/`, `contexts/`, `rules/`, `skills/`, `harnesses/`, `agents/`, `logs/`, `evals/`, `improvements/`
   - 生成 `.harness/config.yaml` 默认配置

3. 实现配置管理模块
   - 读取/写入 `.harness/config.yaml`
   - 配置项：默认模型、API key 引用、日志级别

**验收标准**：
- ✅ `harnesskit init` 执行成功，目录结构正确
- ✅ 重复执行提示已初始化
- ✅ 有单元测试覆盖

---

### Phase 1.2：Prompt 资产管理 ✅
**任务**：
1. Prompt 数据模型（YAML）
   ```yaml
   name: code-reviewer
   version: v0.1.0
   description: "资深代码审查工程师"
   created_at: "2026-03-23T10:00:00+08:00"
   tags: [code, review, security]
   variables:
     - name: language
       required: true
     - name: focus
       required: false
       default: "security,performance"
   content: |
     你是一位资深 {{language}} 工程师...
   ```

2. 实现 `harnesskit prompt` 子命令：
   - `save <name>` —— 从 stdin/文件/参数保存 prompt
   - `show <name>` —— 显示最新版本
   - `show <name>@v0.1.0` —— 显示指定版本
   - `list` —— 表格展示所有 prompt（rich 渲染）
   - `history <name>` —— 显示版本历史
   - `diff <name>@v1 <name>@v2` —— 彩色 diff（rich）
   - `delete <name>` —— 删除 prompt

3. 版本管理
   - 语义版本 `v0.0.1`，自动递增 patch
   - 存储路径：`.harness/prompts/{name}/v{x}.{y}.{z}.yaml`
   - `_current` 文本文件（内容为版本号，如 `v0.1.0`）替代软链接，跨平台兼容

**验收标准**：
- ✅ 所有 prompt 命令正常工作
- ✅ YAML 解析正确，多行文本保留格式
- ✅ diff 功能正确显示修改
- ✅ 单元测试覆盖率 > 80%

---

### Phase 1.3：Schema 资产管理 ✅
**任务**：
1. Schema 数据模型（JSON Schema）
   ```json
   {
     "name": "read-file",
     "version": "v0.1.0",
     "description": "读取文件内容",
     "parameters": {
       "type": "object",
       "properties": {
         "path": {"type": "string", "description": "文件路径"}
       },
       "required": ["path"]
     }
   }
   ```

2. 实现 `harnesskit schema` 子命令：
   - `save <name> --file schema.json`
   - `show <name>`
   - `list`
   - `validate <name>` —— JSON Schema 合法性检查
   - `delete <name>`

3. 版本管理同 Prompt

**验收标准**：
- ✅ JSON Schema 能正确验证示例数据
- ✅ validate 命令返回清晰的错误信息

---

### Phase 1.4：Context 模板管理 ✅
**任务**：
1. Context 数据模型（YAML）
   ```yaml
   name: code-review-ctx
   version: v0.1.0
   description: "代码审查上下文模板"
   slots:
     - name: code
       required: true
     - name: language
       required: false
       default: "auto"
   template: |
     请审查以下 {{language}} 代码：
     ```{{language}}
     {{code}}
     ```
   ```

2. 实现 `harnesskit context` 子命令：
   - `save <name>`
   - `render <name> --var code="..." --var language=python` —— 渲染模板
   - `show <name>`
   - `list`
   - `delete <name>`

3. 使用 Jinja2 引擎

**验收标准**：
- ✅ `render` 命令正确替换变量
- ✅ 支持变量默认值和必填校验
- ✅ 支持复杂类型（list, dict）

---

### Phase 1.5：Rule 约束管理 ✅
**任务**：
1. Rule 数据模型（YAML）
   ```yaml
   name: no-hallucination
   type: hard  # hard 走 linter，soft 走 prompt
   description: "禁止输出不存在的信息"
   check:
     type: regex
     pattern: "(根据我所知|我猜测|可能是)"
   fix_hint: "请删除推测性表述，只陈述确认的事实"
   ```
   > **注意**：Rule 无版本号，是全局配置，直接覆盖（修改即生效，不需要版本追踪）

2. 实现 `harnesskit rule` 子命令：
   - `add <name> --type hard --pattern "..."`
   - `list`
   - `show <name>`
   - `test <name> --input "..."` —— 测试规则是否触发
   - `delete <name>`

3. Rule Checker 基础框架
   - 支持 regex 类型
   - 返回匹配结果和 fix_hint

**验收标准**：
- ✅ `test` 命令正确检测违规内容
- ✅ hard/soft 类型正确区分

---

### Phase 1.6：资产间引用解析 ✅
**任务**：
1. 实现引用语法解析（统一格式：`{name}@{version}`，类型从上下文推断）
   - `code-reviewer@v0.1.0` → 精确版本
   - `code-reviewer` → current 版本
   - `code-reviewer@production` → tag 别名
   - 支持跨类型引用检查

2. 依赖检查工具
   - 检查引用的资产是否存在
   - 检查循环引用

3. 实现 `harnesskit doctor` 命令
   - 扫描 `.harness/` 健康状态
   - 检查损坏的引用
   - 报告未使用的资产

**验收标准**：
- ✅ 能正确解析各种引用语法
- ✅ doctor 命令能发现常见问题

---

### Phase 1.7：Phase 1 集成测试与文档 ✅
**任务**：
1. 集成测试
   - 完整的用户场景测试：init → save prompt → save schema → create context → 引用它们

2. README 更新
   - 安装方法
   - 快速上手示例
   - Phase 1 功能完整说明

3. 代码审查和重构
   - 确保代码结构清晰
   - 错误处理完善

**验收标准**：
- ✅ 所有命令通过集成测试（31 个集成测试，100% 通过）
- ✅ README 清晰完整（安装、快速上手、所有 Phase 1 命令说明、速查表）
- ✅ 可以通过 `pip install .` 安装

---

## Phase 2：Skill 层

**目标**：实现 Skill 定义、I/O 契约、独立运行。

### Phase 2.1：Skill 数据模型与存储 ✅
**任务**：
1. Skill YAML 格式
   ```yaml
   name: code-reviewer
   version: v0.1.0
   description: "审查代码，输出问题列表"
   trigger: "当需要审查代码时"
   
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
       schema: issue-schema.json
   
   assets:
     prompts:
       system: code-reviewer-system@v0.1.0
       user: code-reviewer-user@v0.0.1
     schemas:
       - read-file@v0.0.1
     rules:
       - output-json
       - no-hallucination
     context: code-review-ctx@v0.0.1
   
   examples:
     - input:
         code: "def foo(): pass"
         language: python
       expected_contains: ["缺少实现"]
   
   changelog: "首个版本"
   ```

2. 存储路径：`.harness/skills/{name}/v{x}.{y}.{z}.yaml`

3. 实现 `harnesskit skill save` —— 从配置文件创建 Skill

**验收标准**：
- ✅ Skill YAML 结构正确（name/version/description/trigger/inputs/outputs/assets/examples/changelog 全字段支持）
- ✅ 存储路径 `.harness/skills/{name}/v{x}.{y}.{z}.yaml` + `_current` 文件正确
- ✅ `harnesskit skill save --file <yaml>` 命令正常工作（创建/更新，自动递增 patch 版本）
- ✅ 能引用 Phase 1 创建的资产（assets 字段支持 prompts/schemas/rules/context 任意引用）
- ✅ 36 个 pytest 测试全部通过（unit + CLI integration）

---

### Phase 2.2：Skill CLI 命令 ✅
**任务**：
1. 实现 `harnesskit skill` 子命令：
   - `save <name> --file skill.yaml`
   - `show <name>` —— 显示完整定义
   - `show <name> --render` —— 显示渲染后的完整 prompt
   - `list`
   - `diff <name>@v1 <name>@v2`
   - `delete <name>`

2. Skill 引用验证
   - 检查所有引用的 assets 是否存在
   - 检查版本号是否有效

**验收标准**：
- ✅ 所有命令正常工作
- ✅ 错误引用给出清晰提示

---

### Phase 2.3：Skill 独立运行 ✅
**任务**：
1. LLM 调用基础模块
   - 支持 OpenAI API 格式
   - 可配置 base_url（支持任意兼容接口）
   - 从环境变量读取 API key

2. 实现 `harnesskit skill run <name>`
   - 读取 Skill 定义
   - 解析 inputs，支持 `--var key=value`
   - 组装完整 prompt（system + user + context 渲染）
   - 调用 LLM
   - 应用 rules 检查输出
   - 返回结果

3. 调用日志记录
   - 写入 `.harness/logs/calls.jsonl`
   - 记录：时间、skill、模型、input、output、token 数、耗时

**验收标准**：
- ✅ 能成功调用 LLM 并返回结果
- ✅ 日志文件正确生成
- ✅ 支持流式输出（--stream）

---

### Phase 2.4：Rule 运行时检查 ✅
**任务**：
1. 硬规则（hard rule）运行时检查
   - LLM 输出后自动运行所有 hard rules
   - 违规时返回错误和 fix_hint
   - 统计违规次数

2. 软规则（soft rule）注入
   - 自动将 soft rules 追加到 system prompt
   - 格式："规则：{description}"

3. 实现 `harnesskit skill run --check-rules strict`
   - strict 模式：hard rule 违规即失败
   - lenient 模式：仅警告

**验收标准**：
- ✅ hard rule 能拦截违规输出
- ✅ soft rule 正确注入 prompt
- ✅ 命令行参数生效
- ✅ 违规记录到日志（violations 字段 + violation_count）
- ✅ `harnesskit rule stats` 统计违规次数

---

### Phase 2.5：Skill 版本管理进阶 ✅
**任务**：
1. Skill Tag 功能
   - `harnesskit skill tag <name> --name production`
   - 创建别名链接
   - `harnesskit skill show <name>@production`

2. Skill Clone
   - `harnesskit skill clone <name> <new-name>`
   - 复制 Skill 定义，重置版本为 v0.0.1

3. Skill 依赖导出
   - `harnesskit skill deps <name>` —— 列出所有依赖的资产

**验收标准**：
- ✅ tag 和 clone 功能正常
- ✅ 依赖列表准确

---

### Phase 2.6：Phase 2 集成测试 ✅
**任务**：
1. 完整 Skill 使用流程测试
   - 创建 Prompt → 创建 Rule → 创建 Skill → 运行 → 检查结果

2. 性能测试
   - 测量 LLM 调用耗时
   - 优化日志写入性能

3. 文档更新
   - Skill 使用教程
   - 最佳实践：如何设计一个好的 Skill

**验收标准**：
- ✅ 端到端流程通过（31 个集成测试，100% 通过）
- ✅ 文档清晰可用（Skill 使用教程 + 最佳实践 + 完整命令速查表）

---

## Phase 3：Harness 与 Agent 层

**目标**：实现 Harness 配置组合、Agent 持续运行、上下文管理。

### Phase 3.1：Harness 数据模型 ✅
**任务**：
1. Harness YAML 格式
   ```yaml
   name: my-code-review
   version: v0.1.0
   description: "完整的代码审查 Harness"
   
   skills:
     - code-reviewer@v0.1.0
     - explain-error@v0.0.2
   
   model:
     provider: openai
     name: gpt-4o
     temperature: 0.3
     max_tokens: 2000
   
   memory:
     scope: session  # session / harness / global
     max_turns: 10
   
   constraints:
     rules: [no-hallucination]
     max_cost_per_call: 0.01  # USD
     timeout: 30  # seconds
   
   context_budget: 4000  # tokens
   ```

2. 存储路径：`.harness/harnesses/{name}/v{x}.{y}.{z}.yaml`

3. 实现 `harnesskit harness create`

**验收标准**：
- ✅ Harness 结构正确
- ✅ 能引用多个 Skills

---

### Phase 3.2：Harness CLI 命令 ✅
**任务**：
1. 实现 `harnesskit harness` 子命令：
   - `create <name> --skills skill1,skill2`
   - `show <name>`
   - `list`
   - `diff <name>@v1 <name>@v2`
   - `clone <name> <new-name>`
   - `delete <name>`

2. 实现 `harnesskit harness run <name>`
   - 加载 Harness 配置
   - 加载所有引用的 Skills
   - 解析输入，分发到对应 Skill
   - 管理上下文预算
   - 执行完整的 LLM 调用流程

**验收标准**：
- 能成功运行多 Skill Harness
- 上下文预算管理正确

---

### Phase 3.3：Memory 记忆系统 ✅
**任务**：
1. Memory 存储实现
   - Session Memory：内存中，进程结束消失
   - Harness Memory：`.harness/memory/{harness_name}.json`
   - Global Memory：`.harness/memory/global.json`

2. Memory 数据结构
   ```json
   {
     "turns": [
       {"role": "user", "content": "...", "timestamp": "..."},
       {"role": "assistant", "content": "...", "timestamp": "..."}
     ],
     "metadata": {
       "total_tokens": 1234,
       "summary": "用户询问 Python 异常处理"
     }
   }
   ```

3. 上下文压缩
   - 超过 max_turns 时，自动摘要旧对话
   - 使用 LLM 生成摘要

4. Memory 查询
   - 语义搜索历史对话（Phase 6 再实现）
   - 先实现简单的关键词匹配

**验收标准**：
- ✅ Memory 能跨调用持久化
- ✅ 超过 max_turns 自动压缩

---

### Phase 3.4：Agent 定义与运行 ✅
**任务**：
1. Agent YAML 格式
   ```yaml
   name: code-assistant
   harness: my-code-review@v0.1.0
   identity:
     name: "代码助手"
     description: "帮助你审查和改进代码"
   memory:
     scope: session
     persist: true
   max_iterations: 10
   ```

2. 存储路径：`.harness/agents/{name}.yaml`

3. 实现 `harnesskit agent` 子命令：
   - `create <name> --harness harness-name`
   - `run <name>` —— 启动交互式对话
   - `list`
   - `delete <name>`

4. Agent 交互模式
   - REPL 界面
   - 支持 `/reset` 清空记忆
   - 支持 `/save` 保存对话到文件
   - 支持 `/quit` 退出

**验收标准**：
- ✅ 能启动交互式 Agent 对话
- ✅ 记忆能跨轮次保持
- ✅ 命令工作正常

---

### Phase 3.5：Phase 3 集成与测试 ✅
**任务**：
1. 完整流程测试
   - init → create prompt → create skill → create harness → create agent → run

2. 错误处理完善
   - 所有错误都有清晰的错误信息
   - 建议修复方法

3. 性能优化
   - 启动时间优化
   - 内存使用优化

4. 文档更新
   - Harness 和 Agent 使用教程

**验收标准**：
- ✅ 完整端到端流程可用（41 个 Phase 3 集成测试，100% 通过）
- ✅ 文档完整（Harness + Agent 使用教程 + 最佳实践 + 完整命令速查表）

---

## Phase 4：Blueprint 工作流编排

**目标**：实现确定性节点 + Agentic 节点的混合工作流。

### Phase 4.1：Blueprint YAML 格式 ✅
**任务**：
1. Blueprint 数据结构
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
       on_fail: stop
       timeout: 10
   
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

2. 存储路径：`.harness/blueprints/{name}/v{x}.{y}.{z}.yaml`

3. 实现 `harnesskit blueprint create`

**验收标准**：
- ✅ Blueprint 结构正确
- ✅ 支持变量插值语法 `{{steps.xxx.output}}`

---

### Phase 4.2：Blueprint 验证 ✅
**任务**：
1. 静态验证
   - 检查所有引用的 Harness/Skill 是否存在
   - 检查步骤 ID 是否唯一
   - 检查变量引用是否合法（没有循环依赖）

2. 实现 `harnesskit blueprint validate <name>`
   - 返回详细的验证报告
   - 标记错误位置和修复建议

**验收标准**：
- ✅ 能发现常见的 Blueprint 错误
- ✅ 验证报告清晰可读

---

### Phase 4.3：确定性节点执行器 ✅
**任务**：
1. 本地命令执行
   - 使用 subprocess 执行 shell 命令
   - 捕获 stdout/stderr
   - 支持超时控制

2. Python 函数执行
   - 支持调用 Python 函数（未来扩展）

3. 条件分支
   - `on_fail: stop / continue / goto:step_id`
   - 支持简单的条件判断

**验收标准**：
- ✅ 能正确执行 shell 命令
- ✅ 超时控制有效
- ✅ 错误处理正确

---

### Phase 4.4：Agentic 节点执行器 ✅
**任务**：
1. 调用 Harness/Skill
   - 根据配置调用对应的 Harness 或 Skill
   - 传递输入参数
   - 获取输出结果

2. 重试机制
   - max_retries 支持
   - 指数退避

3. 错误处理
   - 区分可重试错误和致命错误
   - 记录失败原因

**验收标准**：
- ✅ Agentic 节点正确调用
- ✅ 重试机制工作正常

---

### Phase 4.5：变量传递系统 ✅
**任务**：
1. 全局上下文
   - `{{inputs.xxx}}` —— Blueprint 输入
   - `{{env.XXX}}` —— 环境变量

2. 步骤间传递
   - `{{steps.xxx.output}}` —— 某步骤的输出
   - `{{steps.xxx.exit_code}}` —— 退出码

3. 字符串处理函数
   - `{{steps.xxx.output | truncate:100}}`
   - `{{steps.xxx.output | json}}`

**验收标准**：
- ✅ 变量能正确解析和传递
- ✅ 字符串函数工作正常

---

### Phase 4.6：Blueprint 运行与调试 ✅
**任务**：
1. 实现 `harnesskit blueprint run <name>`
   - 按顺序执行所有步骤
   - 实时显示进度（Rich Progress spinner，每步开始/完成即时刷新）
   - 生成执行报告

2. 调试模式
   - `harnesskit blueprint run --dry-run` —— 模拟运行，不执行实际命令
   - `harnesskit blueprint run --step step_id` —— 从指定步骤开始
   - `harnesskit blueprint run --verbose` —— 显示详细日志

3. 执行报告
   - 每个步骤的耗时、状态、输出摘要
   - 保存到 `.harness/logs/blueprints/{name}-{timestamp}.json`

**验收标准**：
- ✅ 能成功运行完整的 Blueprint
- ✅ 调试工具实用（--dry-run / --step / --verbose 全部可用）
- ✅ 执行报告清晰（summary + per-step detail + outputs 保存至日志目录）

---

## Phase 5：评估引擎

**目标**：量化测试 Harness/Skill 效果，支持 A/B 对比。

### Phase 5.1：Test Suite 定义 ✅
**任务**：
1. Test Suite YAML 格式
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
         - type: contains
           path: "$.issues[*].severity"
           value: "high"
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

2. 存储路径：`.harness/evals/suites/{name}.yaml`

**验收标准**：
- ✅ Test Suite 结构正确
- ✅ 支持多种断言类型

---

### Phase 5.2：断言引擎 ✅
**任务**：
1. 实现断言类型
   - `contains` —— 包含指定值
   - `regex` —— 匹配正则
   - `json_schema` —— 符合 JSON Schema
   - `similarity` —— 语义相似度（Phase 6 再实现）
   - `custom` —— 自定义 Python 函数

2. JSON Path 解析
   - 使用 `jsonpath-ng` 库
   - 支持复杂路径查询

3. 断言结果报告
   - 每个断言通过/失败
   - 实际值 vs 期望值对比

**验收标准**：
- ✅ 所有断言类型工作正常
- ✅ 错误提示清晰

---

### Phase 5.3：单次评估运行
**任务**：
1. 实现 `harnesskit eval run <skill/harness> --suite <suite-name>`
   - 加载 Test Suite
   - 对每个 case 调用 Skill/Harness
   - 运行所有断言
   - 生成结果报告

2. 结果报告格式
   ```json
   {
     "timestamp": "...",
     "target": "code-reviewer@v0.1.0",
     "suite": "code-review-suite",
     "summary": {
       "total": 10,
       "passed": 8,
       "failed": 2
     },
     "cases": [
       {
         "id": "detect-bug",
         "status": "passed",
         "duration": 2.3,
         "tokens": 150
       }
     ]
   }
   ```

3. 保存结果到 `.harness/evals/results/{timestamp}.json`

**验收标准**：
- 能正确运行测试套件
- 报告信息完整

---

### Phase 5.4：A/B 对比
**任务**：
1. 实现 `harnesskit eval compare --a skill@v1 --b skill@v2 --suite suite-name`
   - 两个版本跑同一个测试集
   - 对比成功率、token 消耗、耗时
   - 生成对比报告

2. 对比报告格式
   - 表格展示：指标 | v1 | v2 | 变化
   - 失败的 case 对比
   - 建议哪个版本更好

**验收标准**：
- 对比结果清晰
- 变化趋势明显

---

### Phase 5.5：多模型 Benchmark
**任务**：
1. 实现 `harnesskit eval benchmark <skill> --suite suite-name --models "gpt-4o,claude-3-5,deepseek-v3"`
   - 同一个 Skill 用不同模型跑
   - 对比各模型的表现

2. Benchmark 报告
   - 每个模型的成功率、成本、速度
   - 推荐最佳模型
   - 雷达图（Phase 6 再实现）

**验收标准**：
- 支持多个模型对比
- 报告有参考价值

---

### Phase 5.6：评估系统集成
**任务**：
1. 与 Harness 集成
   - `harnesskit harness create --eval-suite suite-name`
   - 创建时绑定测试集

2. CI 模式
   - `harnesskit eval run --ci`
   - 失败时返回非零退出码
   - 生成 JUnit XML 格式报告（供 CI 系统使用）

3. 历史趋势
   - 记录每次评估结果
   - 显示成功率趋势（命令行简单图表）

**验收标准**：
- CI 集成可用
- 趋势数据正确

---

## Phase 6：可观测性与自改进

**目标**：调用追踪、成本分析、Harness 健康检查、改进飞轮。

### Phase 6.1：调用日志系统
**任务**：
1. 日志格式（JSON Lines）
   ```json
   {"timestamp": "2026-03-23T10:00:00", "type": "llm_call", "skill": "code-reviewer", "model": "gpt-4o", "input_tokens": 500, "output_tokens": 200, "cost": 0.015, "duration": 2.5, "status": "success"}
   ```

2. 实现 `harnesskit logs tail` —— 实时查看日志
3. 实现 `harnesskit logs search --skill code-reviewer --since 1d` —— 搜索日志
4. 实现 `harnesskit logs export --format csv --since 7d` —— 导出日志

**验收标准**：
- 日志记录完整
- 搜索和导出功能正常

---

### Phase 6.2：成本追踪
**任务**：
1. Token 价格配置
   - `.harness/config.yaml` 中配置各模型的 input/output 价格

2. 实现 `harnesskit cost report`
   - 日报/周报/月报
   - 按 Skill、Harness、模型分组
   - 总费用、平均费用、最贵调用

3. 成本预警
   - 单次调用超过阈值时警告
   - 日累计超过阈值时警告

**验收标准**：
- 成本计算准确
- 报告清晰有用

---

### Phase 6.3：统计仪表盘
**任务**：
1. 实现 `harnesskit stats show <skill/harness>`
   - 调用次数、成功率、平均耗时
   - Token 消耗分布
   - 错误类型分布

2. 命令行图表
   - 使用 `rich` 的表格和进度条
   - 简单的柱状图（用字符画）

**验收标准**：
- 统计数据准确
- 可视化清晰

---

### Phase 6.4：改进飞轮核心
**任务**：
1. 改进日志格式
   ```json
   {"timestamp": "...", "type": "improvement", "skill": "code-reviewer", "issue": "输出了不存在的函数", "root_cause": "缺少 hallucination 检查", "fix": "添加 no-hallucination rule", "before_version": "v0.1.0", "after_version": "v0.1.1", "eval_improvement": "+12%"}
   ```

2. 实现 `harnesskit improve log`
   - 交互式记录改进
   - 关联到具体的失败案例

3. 实现 `harnesskit improve history <skill>` —— 查看改进历史
4. 实现 `harnesskit improve report --period week` —— 改进周报

**验收标准**：
- 能记录完整的改进信息
- 能追踪改进效果

---

### Phase 6.5：Harness 健康检查
**任务**：
1. 健康检查规则
   - 检查是否有 Skill 超过 14 天未更新
   - 检查是否有 Skill 成功率低于阈值
   - 检查是否有未使用的资产
   - 检查 Schema 是否过期

2. 实现 `harnesskit health check`
   - 输出健康报告
   - 标记问题等级（警告/严重）

3. 实现 `harnesskit health fix`
   - 自动修复可修复的问题
   - 生成修复报告

**验收标准**：
- 能发现常见的 Harness 问题
- 自动修复安全可靠

---

### Phase 6.6：Phase 6 集成与优化
**任务**：
1. 完整的可观测性流程测试
2. 性能优化（日志写入、查询速度）
3. 文档更新

**验收标准**：
- 端到端流程可用
- 文档完整

---

## Phase 7：TUI 终端界面

**目标**：用 `textual` 实现可交互的终端界面。

### Phase 7.1：TUI 框架搭建
**任务**：
1. 引入 `textual` 依赖
2. 实现 `harnesskit tui` 命令入口
3. 基础布局：Header / Sidebar / Main / Footer
4. 快捷键系统（Vim 风格：j/k 上下，q 退出）

**验收标准**：
- TUI 能正常启动
- 布局合理
- 快捷键响应

---

### Phase 7.2：Skill 浏览器
**任务**：
1. 左侧：Skill 列表（可搜索、过滤）
2. 右侧：Skill 详情（版本、描述、I/O 定义）
3. 快捷键：
   - `Enter` 查看详情
   - `r` 运行 Skill
   - `d` 查看 diff
   - `e` 编辑

**验收标准**：
- 浏览流畅
- 快捷键工作正常

---

### Phase 7.3：Prompt Diff 可视化
**任务**：
1. 选择两个 Prompt 版本
2. 并排对比显示（左旧右新）
3. 高亮差异（增/删/改）
4. 支持行内 diff

**验收标准**：
- diff 显示清晰
- 高亮准确

---

### Phase 7.4：Eval 结果可视化
**任务**：
1. 测试套件列表
2. 选择套件后显示所有 cases
3. 通过/失败用颜色区分（绿/红）
4. 选择 case 查看详细断言结果

**验收标准**：
- 结果一目了然
- 详情查看方便

---

### Phase 7.5：实时日志流
**任务**：
1. 类似 `tail -f` 的实时日志显示
2. 支持过滤（按 Skill、按时间）
3. 支持暂停/继续
4. 支持搜索高亮

**验收标准**：
- 实时性良好
- 过滤和搜索有效

---

### Phase 7.6：TUI 优化与完善
**任务**：
1. 添加帮助页面（`?` 键）
2. 主题切换（light/dark）
3. 响应式布局适配
4. 错误处理和恢复

**验收标准**：
- 用户体验流畅
- 帮助信息完整

---

## Phase 8：Web Playground

**目标**：FastAPI + 轻量前端，实现 Web UI。

### Phase 8.1：Web 服务框架
**任务**：
1. 引入 `fastapi` 和 `uvicorn`
2. 实现 `harnesskit serve` 命令
3. 基础 API 结构：
   - `GET /api/skills` —— 列出所有 Skills
   - `GET /api/skills/{name}` —— 获取 Skill 详情
   - `POST /api/skills/{name}/run` —— 运行 Skill

4. CORS 配置

**验收标准**：
- API 能正常响应
- 能正确加载本地 .harness 数据

---

### Phase 8.2：前端框架搭建
**任务**：
1. 前端技术选型：**HTMX + Alpine.js**（无需 React/Vue，配合 FastAPI 极简高效）
2. 创建前端目录 `harness_kit/web/static/`
3. 基础 HTML 框架 + TailwindCSS CDN（样式）
4. 导航栏：Skills / Harness / Eval / Logs / Settings
5. 静态文件挂载到 `/`

**验收标准**：
- 访问 `http://localhost:7749` 能看到完整页面框架
- 导航正常跳转
- HTMX 动态加载工作正常

---

### Phase 8.3：Prompt Playground
**任务**：
1. 前端界面：
   - 左侧：变量输入表单（根据 Skill inputs 动态生成）
   - 右侧：模型选择 + 运行按钮
   - 底部：输出区域

2. API 集成：
   - 表单提交调用 `POST /api/skills/{name}/run`
   - 显示加载状态
   - 渲染输出结果

**验收标准**：
- 表单能根据 Skill 定义动态生成
- 能成功运行并显示结果

---

### Phase 8.4：A/B 对比界面
**任务**：
1. 选择两个版本（左 v1，右 v2）
2. 同时发送请求
3. 并排显示输出
4. 高亮差异

**验收标准**：
- 对比效果清晰
- 响应同步

---

### Phase 8.5：Eval Dashboard
**任务**：
1. 测试套件列表
2. 运行按钮
3. 结果显示（表格 + 图表）
4. 历史趋势（简单折线图）

**验收标准**：
- 数据可视化清晰
- 图表可用

---

### Phase 8.6：Blueprint 可视化
**任务**：
1. 简单的节点图（用 Mermaid.js 或 SVG）
2. 显示步骤和依赖关系
3. 运行时高亮当前步骤

**验收标准**：
- 流程图清晰
- 运行时状态更新

---

### Phase 8.7：MCP Server 导出 + AGENTS.md 导出
**任务**：
1. 实现 `harnesskit export mcp`
2. 启动 MCP Server
3. 暴露所有 Skills 为 MCP Tools
4. 供 Claude/Cursor 调用

5. 实现 `harnesskit export agents-md`（重要功能）
   - 根据已注册的 Skills 和 Harness 自动生成 AGENTS.md
   - 严格控制在 60 行以内（ETH Zurich 研究：超过 60 行反而降低 Agent 表现）
   - 格式：顶层是「技能目录」，每个 Skill 一行描述 + 指向详细文档的路径
   - 每次更新 Skill 后可重新生成

**验收标准**：
- MCP Server 能启动，Claude/Cursor 能发现并调用
- 生成的 AGENTS.md 不超过 60 行
- AGENTS.md 内容清晰，指向正确的 Skill 文档

---

### Phase 8.8：Skills Registry
**任务**：
1. 本地 Registry 索引：`~/.harnesskit/registry.json`
   - 已安装的 Skills 列表
   - 版本、来源、安装时间

2. 实现 `harnesskit skill search <keyword>`
   - 先搜索本地已有 Skills
   - 后期支持远程 Registry

3. 实现 `harnesskit skill install <name>`
   - 从本地路径安装：`harnesskit skill install ./my-skill.yaml`
   - 从 Git URL 安装：`harnesskit skill install github:user/repo/skills/name`
   - 从远程 Registry 安装（Phase 完成后）

4. 实现 `harnesskit skill publish <name>`
   - 打包 Skill 及其依赖的 Prompts/Rules/Schemas
   - 导出为 `.hsk` 包格式（实际是 zip）
   - 后期支持推送到中央 Registry

**验收标准**：
- 本地安装/导出流程可用
- 打包格式正确，包含所有依赖

---

### Phase 8.9：打包发布
**任务**：
1. 完善 `pyproject.toml`
2. 发布到 PyPI
3. 安装测试：`pip install harness-kit`
4. 更新 README：安装方法、快速上手

**验收标准**：
- PyPI 安装成功
- 所有功能可用

---

## 附录：数据格式规范

### 存储路径规范
```
.harness/
├── config.yaml
├── prompts/{name}/v{x}.{y}.{z}.yaml + current
├── schemas/{name}/v{x}.{y}.{z}.json + current
├── contexts/{name}/v{x}.{y}.{z}.yaml + current
├── rules/{name}.yaml               # Rule 无版本（全局配置，直接覆盖）
├── skills/{name}/v{x}.{y}.{z}.yaml + current
├── harnesses/{name}/v{x}.{y}.{z}.yaml + current
├── agents/{name}.yaml  # 无版本子目录，直接覆盖
├── blueprints/{name}/v{x}.{y}.{z}.yaml + current
├── logs/calls.jsonl
├── evals/suites/{name}.yaml
├── evals/results/{timestamp}.json
├── improvements/{skill_name}.jsonl
└── memory/{harness_name}.json
```

### 版本号规则
- 语义版本 `v{major}.{minor}.{patch}`
- patch：措辞、格式调整
- minor：新增变量、重构段落
- major：整体重写或方向变化
- 自动递增 patch，major/minor 手动指定

### CLI 命令总览
```
harnesskit init

harnesskit prompt save/show/list/diff/history/delete/tag
harnesskit schema save/show/list/validate/delete
harnesskit context save/render/list/show/delete
harnesskit rule add/list/show/delete/test

harnesskit skill save/show/list/diff/run/clone/delete/tag/install/publish/search
harnesskit harness create/show/list/diff/run/clone/delete
harnesskit agent create/run/list/delete
harnesskit blueprint create/validate/list/show/run

harnesskit eval suite-add/run/compare/benchmark/report
harnesskit improve log/history/report
harnesskit logs tail/search/export
harnesskit cost report/breakdown
harnesskit stats show
harnesskit health check/fix
harnesskit doctor

harnesskit tui
harnesskit serve
harnesskit export agents-md/mcp
```

---

## 关键设计原则

1. **本地优先**：所有数据存储在本地 `.harness/`，可 git 管理
2. **版本化一切**：Prompt、Skill、Harness 都有版本历史
3. **可组合**：Primitive → Skill → Harness → Agent，层层组合
4. **可观测**：调用日志、成本、成功率全部可追踪
5. **自改进**：每次失败都变成 Harness 的进化机会
6. **CLI 为核心**：所有功能都有 CLI 入口，UI 是增强

---

ROADMAP 完毕，确认后让 Claude Code 开始执行 Phase 1。
