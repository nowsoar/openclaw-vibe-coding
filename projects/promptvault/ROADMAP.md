# PromptVault — Roadmap

> Git for Prompts. 给 AI 时代的 Prompt 工程师一个趁手的版本管理工具。

## 项目定位

一个 CLI-first 的 Prompt 版本管理系统，让你像管理代码一样管理 Prompt：存储、版本追踪、变量模板、测试、对比、分享。

技术栈：Python 3.10+，尽量用标准库 + 少量精选依赖。

---

## Phase 1: MVP — 基础 CLI（Day 1-4）

核心：让 prompt 的存取和版本管理像 git 一样自然。

- [ ] 项目初始化：`promptvault init`（在当前目录创建 `.promptvault/` 存储目录）
- [ ] 存储 prompt：`promptvault save <name> --tag v1 --desc "描述"`（支持从 stdin/文件/参数读入）
- [ ] 查看 prompt：`promptvault show <name>` / `promptvault show <name>@v2`
- [ ] 列出所有 prompt：`promptvault list`（表格展示 name/tags/更新时间/描述）
- [ ] 版本历史：`promptvault history <name>`（展示所有版本、时间、diff 摘要）
- [ ] 版本对比：`promptvault diff <name>@v1 <name>@v2`（彩色 diff 输出）
- [ ] 删除 prompt：`promptvault delete <name>` / `promptvault delete <name>@v2`
- [ ] 存储格式：每个 prompt 一个 JSON 文件（metadata + content + versions）
- [ ] 单元测试：核心存储/检索/版本逻辑覆盖
- [ ] README.md：安装方法 + 快速上手 + 所有命令说明

## Phase 2: 模板与测试（Day 5-8）

核心：让 prompt 可复用、可测试。

- [ ] 变量模板：`promptvault render <name> --var role=工程师 --var lang=Python`（Jinja2 语法）
- [ ] 模板验证：`promptvault validate <name>`（检查变量是否都有值）
- [ ] Prompt 测试套件：`promptvault test <name> --provider openai --model gpt-4`
  - 读取 `tests/<name>.yaml` 定义测试用例（输入变量 + 期望输出关键词/正则）
  - 运行 LLM 并断言输出
  - 输出测试报告（通过/失败/耗时/token 数）
- [ ] 批量渲染：`promptvault render <name> --vars-file data.csv`（批量生成）
- [ ] 导入导出：`promptvault export <name> > prompt.json` / `promptvault import prompt.json`
- [ ] 搜索：`promptvault search <keyword>`（全文搜索 prompt 内容和描述）

## Phase 3: 多模型对比与成本追踪（Day 9-13）

核心：让 prompt 的效果和成本可量化。

- [ ] 多模型对比：`promptvault compare <name> --models gpt-4,claude-3,deepseek`
  - 同一 prompt 发给多个模型，对比输出质量
  - 表格展示：模型/输出摘要/token 数/耗时/费用
- [ ] Token 计算器：`promptvault tokens <name>`（估算 token 数，支持不同 tokenizer）
- [ ] 成本追踪：记录每次运行的 token 消耗和费用，`promptvault cost-report`
- [ ] Prompt 评分：`promptvault rate <name> --score 8 --note "输出太啰嗦"`
- [ ] 最佳版本标记：`promptvault best <name>@v3`
- [ ] 配置文件：`~/.promptvault/config.yaml`（API keys、默认模型、token 价格）

## Phase 4: 工程化与协作（Day 14-18）

核心：从个人工具变成团队工具。

- [ ] Git 集成：`.promptvault/` 可直接用 git 管理，提供 `.gitignore` 模板
- [ ] Lock 文件：`promptvault.lock`（锁定 prompt 版本，团队共享一致的 prompt 版本）
- [ ] CI 集成：`promptvault test --ci`（GitHub Actions 模板，PR 时自动测试 prompt）
- [ ] 发布/分享：`promptvault publish <name>`（导出为标准格式，含 metadata）
- [ ] Prompt 组合：`promptvault chain <system> <user> <few-shot>`（组装多段 prompt）
- [ ] Hooks：`promptvault hook pre-save "python lint.py"`（保存前自动检查）
- [ ] pyproject.toml + setuptools 打包，发布到 PyPI

## Phase 5: 可视化与高级功能（Day 19-25）

核心：从 CLI 扩展到 Web UI。

- [ ] Web UI：`promptvault serve`（本地 Web 界面，浏览/编辑/测试 prompt）
- [ ] Playground：在 Web UI 中直接调试 prompt，实时预览输出
- [ ] Dashboard：prompt 使用统计、成本趋势图、模型对比图表
- [ ] MCP Server：`promptvault mcp`（作为 MCP tool 暴露给 Claude/Cursor 等）
- [ ] VS Code 插件：在编辑器中直接搜索和插入 prompt（如果时间允许）

---

## 开发原则

1. **每次提交一个完整功能**，不留半成品
2. **先写测试再写实现**（或至少同步写）
3. **README 随功能同步更新**
4. **commit message 遵循 Conventional Commits**（feat/fix/docs/refactor）
5. **代码可读性优先**，不过度抽象
6. **每个 Phase 结束时**，确保 `pip install .` 能直接用
