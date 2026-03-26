# HarnessKit 快速上手指南

> 5 分钟学会用 HarnessKit 管理你的 AI 提示词和工作流。

---

## 目录

- [HarnessKit 是什么？](#harnesskit-是什么)
- [安装](#安装)
- [第一步：初始化项目](#第一步初始化项目)
- [第二步：保存你的第一个提示词](#第二步保存你的第一个提示词)
- [第三步：添加约束规则](#第三步添加约束规则)
- [第四步：创建 Skill（可运行的 AI 单元）](#第四步创建-skill可运行的-ai-单元)
- [第五步：运行 Skill](#第五步运行-skill)
- [第六步：打开 Web 界面](#第六步打开-web-界面)
- [常用命令速查](#常用命令速查)
- [常见问题](#常见问题)

---

## HarnessKit 是什么？

想象你在使用 ChatGPT，每次都要粘贴一大段"你是一个资深工程师，请帮我审查代码……"这样的提示词。

**HarnessKit 做的事情：**
- 把这段提示词保存起来，给它起个名字
- 每次修改都自动记录历史版本（像 Git 一样）
- 可以对比两个版本的差异
- 一键运行，自动填入变量，调用 AI

```
你写的提示词模板 + 你的代码 → HarnessKit → AI 分析结果
```

---

## 安装

需要先安装 Python 3.10 或更高版本。

```bash
pip install harness-kit
```

安装完成后，验证一下：

```bash
harnesskit --help
```

看到命令列表就说明安装成功了。

---

## 第一步：初始化项目

在你想保存提示词的目录下运行：

```bash
mkdir my-ai-project
cd my-ai-project
harnesskit init
```

这会创建一个 `.harness/` 文件夹，你的所有提示词、规则、工作流都存在这里。

```
my-ai-project/
└── .harness/
    ├── config.yaml    ← AI 模型配置
    ├── prompts/       ← 提示词
    ├── rules/         ← 约束规则
    ├── skills/        ← 可运行的 AI 单元
    └── ...
```

---

## 第二步：保存你的第一个提示词

假设你想创建一个"代码审查助手"：

```bash
harnesskit prompt save code-reviewer \
  --content "你是一位资深 {{language}} 工程师。
请仔细审查以下代码，找出：
1. 可能的 bug
2. 安全漏洞
3. 性能问题
请用中文回答，按严重程度排列。" \
  --description "代码审查系统提示词" \
  --tags "代码,审查"
```

> **注意：** `{{language}}` 是变量，运行时会替换成实际的编程语言。

查看刚才保存的提示词：

```bash
harnesskit prompt show code-reviewer
```

**修改提示词（自动记录新版本）：**

```bash
harnesskit prompt save code-reviewer \
  --content "你是一位资深 {{language}} 工程师，拥有 10 年以上经验。
请仔细审查以下代码，找出：
1. 可能的 bug（标注：严重 / 中等 / 轻微）
2. 安全漏洞
3. 性能优化建议
用中文回答，每条问题请给出具体修复建议。" \
  --changelog "增加严重程度标注和修复建议"
```

查看历史和对比：

```bash
# 查看版本历史
harnesskit prompt history code-reviewer

# 对比两个版本
harnesskit prompt diff code-reviewer@v0.0.1 code-reviewer@v0.0.2
```

---

## 第三步：添加约束规则

规则用来保证 AI 输出符合你的要求：

```bash
# 硬规则：AI 回答里不能有推测性语言
harnesskit rule add no-speculation \
  --type hard \
  --pattern "(我猜测|可能是|也许|我认为可能)" \
  --description "禁止推测性表述" \
  --fix-hint "只陈述代码中确认存在的问题"

# 软规则：注入到提示词里的建议
harnesskit rule add use-chinese \
  --type soft \
  --pattern "." \
  --description "始终用中文回答"
```

**测试规则是否生效：**

```bash
# 应该触发（有推测性语言）
harnesskit rule test no-speculation --input "我猜测这里可能有内存泄漏"

# 应该通过
harnesskit rule test no-speculation --input "第 15 行存在空指针异常风险"
```

---

## 第四步：创建 Skill（可运行的 AI 单元）

Skill 把提示词、规则打包在一起，变成一个可以直接运行的 AI 工具。

创建一个配置文件 `code-reviewer.yaml`：

```yaml
name: code-reviewer
description: "审查代码，找出 bug、安全问题和性能瓶颈"
trigger: "当需要审查代码时使用"

inputs:
  - name: code      # 必填：要审查的代码
    type: string
    required: true
  - name: language  # 可选：编程语言（默认 python）
    type: string
    default: "python"

outputs:
  - name: issues
    type: string

assets:
  prompts:
    system: code-reviewer   # 使用刚才创建的提示词
  rules:
    - no-speculation        # 使用刚才创建的规则
    - use-chinese

changelog: "初始版本"
```

保存 Skill：

```bash
harnesskit skill save --file code-reviewer.yaml
```

---

## 第五步：运行 Skill

**预览（不调用 AI，只看组装后的提示词）：**

```bash
harnesskit skill run code-reviewer \
  --var language=python \
  --var "code=def divide(a, b):
    return a / b" \
  --dry-run
```

**真正运行（需要 API Key）：**

```bash
# 设置 OpenAI API Key
export OPENAI_API_KEY=sk-你的密钥

# 运行
harnesskit skill run code-reviewer \
  --var language=python \
  --var "code=def divide(a, b): return a / b"
```

AI 会返回代码审查结果，并且自动检查输出是否符合规则。

---

## 第六步：打开 Web 界面

除了命令行，HarnessKit 还有一个可视化的 Web 界面：

```bash
harnesskit serve
```

打开浏览器访问：**http://127.0.0.1:7749**

**Web 界面功能：**

| 页面 | 功能 |
|------|------|
| **Skills** | 浏览所有 Skill，填写参数直接运行 |
| **Compare** | 对比两个 Skill 版本的输出差异 |
| **Blueprints** | 查看工作流（Shell + AI 组合流程）|
| **Eval** | 查看测试套件的通过情况 |
| **Logs** | 查看历史 AI 调用记录 |
| **Settings** | 查看当前配置 |

---

## 常用命令速查

```bash
# 初始化
harnesskit init

# 提示词管理
harnesskit prompt save <名称> --content "内容"   # 保存/更新
harnesskit prompt list                           # 列出所有
harnesskit prompt show <名称>                    # 查看详情
harnesskit prompt history <名称>                 # 查看版本历史
harnesskit prompt diff <名称>@v0.0.1 <名称>@v0.0.2  # 对比版本

# 规则管理
harnesskit rule add <名称> --type hard --pattern "..." --description "..."
harnesskit rule list
harnesskit rule test <名称> --input "测试文本"

# Skill 管理
harnesskit skill save --file skill.yaml
harnesskit skill list
harnesskit skill run <名称> --var key=value --dry-run

# 健康检查
harnesskit doctor        # 检查引用是否完整
harnesskit health check  # 检查资产健康状态

# 启动 Web 界面
harnesskit serve         # 默认 http://127.0.0.1:7749
harnesskit serve --port 8080  # 自定义端口
```

---

## 常见问题

**Q：运行 Skill 报错 "No API key configured"？**

需要设置 AI 服务的 API Key：
```bash
export OPENAI_API_KEY=sk-你的密钥
```
或者修改 `.harness/config.yaml`：
```yaml
default_model: gpt-4o
api_key: sk-你的密钥
```

**Q：想用国产 AI（如 DeepSeek）？**

修改 `.harness/config.yaml`：
```yaml
default_model: deepseek-chat
api_key: 你的DeepSeek密钥
base_url: https://api.deepseek.com/v1
```

**Q：提示词里的 `{{变量}}` 是什么语法？**

这是 Jinja2 模板语法。运行时用 `--var 变量名=值` 传入：
```bash
harnesskit skill run code-reviewer --var language=Java --var "code=..."
```

**Q：`.harness/` 文件夹能提交到 Git 吗？**

可以，而且推荐这样做！这样团队成员可以共享同一套提示词和规则。但注意：如果 `config.yaml` 里写了 API Key，要把它加到 `.gitignore`。

**Q：Web 界面上点 Run 没反应？**

Web 界面的 Run 功能需要配置好 API Key，和命令行一样。

---

## 下一步

- 📖 [完整命令文档](README.md)
- 🗺️ [开发路线图](ROADMAP.md)
- 💡 尝试创建一个 **Blueprint 工作流**：把"语法检查 + AI 代码审查"串成一条自动化流水线
