# HarnessKit 快速上手指南

> 5 分钟学会用 HarnessKit 管理你的 AI 提示词和工作流。

---

## 目录

- [HarnessKit 是什么？](#harnesskit-是什么)
- [安装](#安装)
- [第一步：初始化项目](#第一步初始化项目)
- [第二步：配置 AI 接口](#第二步配置-ai-接口)
- [第三步：保存你的第一个提示词](#第三步保存你的第一个提示词)
- [第四步：添加约束规则](#第四步添加约束规则)
- [第五步：创建 Skill（可运行的 AI 单元）](#第五步创建-skill可运行的-ai-单元)
- [第六步：运行 Skill](#第六步运行-skill)
- [第七步：打开 Web 界面](#第七步打开-web-界面)
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

### 方式 A：从 GitHub 安装（推荐）

```bash
pip install "git+https://github.com/nowsoar/openclaw-vibe-coding.git#subdirectory=projects/harnesskit"
```

### 方式 B：克隆到本地安装

```bash
git clone https://github.com/nowsoar/openclaw-vibe-coding.git
cd openclaw-vibe-coding/projects/harnesskit
pip install .
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
    ├── config.yaml    ← AI 模型配置（下一步填写）
    ├── prompts/       ← 提示词
    ├── rules/         ← 约束规则
    ├── skills/        ← 可运行的 AI 单元
    └── ...
```

---

## 第二步：配置 AI 接口

> ⚠️ **这一步必须先做**，否则后面运行 Skill 时会报错。

打开 `.harness/config.yaml`，填入你的 AI 服务配置：

### 方式 A：OpenAI

```yaml
default_model: gpt-4o
api_key: sk-你的OpenAI密钥
log_level: INFO
```

### 方式 B：自定义接口（OpenAI 兼容格式）

如果你用的是公司内部接口或其他 AI 服务（比如 DeepSeek、Azure、国内代理等），只需额外加一个 `base_url`：

```yaml
default_model: 你的模型名称
api_key: 你的密钥
base_url: https://你的接口地址/v1
log_level: INFO
```

> ⚠️ **常见错误：** `base_url` 只写到基础路径，**不要** 加 `/chat/completions`。
> SDK 会自动拼接后缀，手动加了会导致 `404 page not found`。
>
> ```yaml
> # ❌ 错误
> base_url: https://api.example.com/v1/chat/completions
>
> # ✅ 正确
> base_url: https://api.example.com/v1
> ```

**真实示例（DeepSeek）：**

```yaml
default_model: deepseek-chat
api_key: sk-你的DeepSeek密钥
base_url: https://api.deepseek.com/v1
log_level: INFO
```

> 💡 **技巧：** 直接写在 `config.yaml` 里，不需要每次都 `export` 环境变量，更方便。
>
> ⚠️ **安全提示：** `config.yaml` 里有密钥，记得把它加进 `.gitignore`，不要提交到 Git 仓库。

---

## 第三步：保存你的第一个提示词

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

## 第四步：添加约束规则

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

## 第五步：创建 Skill（可运行的 AI 单元）

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

## 第六步：运行 Skill

### 先预览，确认提示词正确（不调用 AI，免费）

```bash
harnesskit skill run code-reviewer \
  --var language=python \
  --var "code=def divide(a, b):
    return a / b" \
  --dry-run
```

输出效果：

```
── Assembled Messages (dry-run) ──

[SYSTEM]
你是一位资深 python 工程师，拥有 10 年以上经验。
...（完整提示词，变量已替换）...
规则：始终用中文回答

[USER]
language: python
code: def divide(a, b):
    return a / b

Model: gpt-4o
```

### 真正运行（调用 AI）

确认第二步的 `config.yaml` 已配置好，然后：

```bash
harnesskit skill run code-reviewer \
  --var language=python \
  --var "code=def divide(a, b):
    return a / b

def get_user(user_id):
    query = 'SELECT * FROM users WHERE id=' + user_id
    return db.execute(query)

password = 'admin123'"
```

**运行结果示例（AI 真实输出）：**

```
## 代码审查报告

### 🔴 严重问题

**1. 除零风险【严重】**
`divide(a, 0)` 会抛出 ZeroDivisionError，程序崩溃。
修复：添加 `if b == 0: raise ValueError("除数不能为零")`

**2. SQL 注入漏洞【严重】**
字符串拼接 SQL 查询，攻击者可注入恶意 SQL。
修复：改用参数化查询 `WHERE id = %s`，传入 `(user_id,)`

**3. 硬编码密码【严重】**
`password = 'admin123'` 明文存储，代码泄露即密码泄露。
修复：改用环境变量 `os.getenv("DB_PASSWORD")`

...

Model: gpt-4o | Tokens: 204↑ 1558↓ | Duration: 28.97s
```

查看调用记录：

```bash
harnesskit logs tail
```

---

## 第七步：打开 Web 界面

```bash
harnesskit serve
```

打开浏览器访问：**http://127.0.0.1:7749**

> 💡 **Web 界面的 Run 按钮** 同样需要 `config.yaml` 配置好 API Key，配置方法和上面第二步完全一样。

**Web 界面功能：**

| 页面 | 功能 |
|------|------|
| **Skills** | 浏览所有 Skill，填写参数直接点 Run 运行 |
| **Compare** | 对比同一 Skill 两个版本的输出差异 |
| **Blueprints** | 查看工作流（Shell + AI 组合流程）|
| **Eval** | 查看测试套件的通过情况 |
| **Logs** | 查看历史 AI 调用记录（含 Token 用量）|
| **Settings** | 查看当前模型和接口配置 |

---

## 常用命令速查

```bash
# 初始化
harnesskit init

# 提示词管理
harnesskit prompt save <名称> --content "内容"        # 保存/更新
harnesskit prompt list                               # 列出所有
harnesskit prompt show <名称>                        # 查看详情
harnesskit prompt history <名称>                     # 查看版本历史
harnesskit prompt diff <名称>@v0.0.1 <名称>@v0.0.2  # 对比版本

# 规则管理
harnesskit rule add <名称> --type hard --pattern "..." --description "..."
harnesskit rule list
harnesskit rule test <名称> --input "测试文本"

# Skill 管理
harnesskit skill save --file skill.yaml
harnesskit skill list
harnesskit skill run <名称> --var key=value --dry-run  # 预览
harnesskit skill run <名称> --var key=value            # 真实运行

# 查看记录
harnesskit logs tail        # 最近调用记录
harnesskit cost report      # 费用统计
harnesskit rule stats       # 规则违规统计

# 健康检查
harnesskit doctor           # 检查引用是否完整
harnesskit health check     # 检查资产健康状态

# 启动 Web 界面
harnesskit serve            # 默认 http://127.0.0.1:7749
harnesskit serve --port 8080  # 自定义端口
```

---

## 常见问题

**Q：运行报错 "404 page not found"？**

`base_url` 多写了 `/chat/completions`。SDK 会自动追加这段路径，手动写进去会拼出错误地址：

```yaml
# ❌ 错误
base_url: https://api.example.com/v1/chat/completions

# ✅ 正确
base_url: https://api.example.com/v1
```

**Q：运行 Skill 报错 "No API key configured"？**

打开 `.harness/config.yaml`，按第二步的格式填入 `api_key`。不需要设置环境变量，直接写进配置文件即可。

**Q：我用的 AI 接口不是 OpenAI，怎么配置？**

只要接口是 OpenAI 兼容格式（绝大多数国内外 AI 服务都是），加一个 `base_url` 就行：

```yaml
default_model: 你的模型名
api_key: 你的密钥
base_url: https://你的接口地址/v1
```

**Q：提示词里的 `{{变量}}` 是什么语法？**

Jinja2 模板语法。运行时用 `--var 变量名=值` 传入：
```bash
harnesskit skill run code-reviewer --var language=Java --var "code=..."
```

**Q：`.harness/` 文件夹能提交到 Git 吗？**

可以，推荐这样做——团队成员可以共享同一套提示词和规则。
但 `config.yaml` 里有密钥，记得加进 `.gitignore`：

```bash
echo ".harness/config.yaml" >> .gitignore
```

**Q：Web 界面点 Run 没反应？**

原因是 `config.yaml` 里没有配置 API Key。按第二步配置好后，刷新页面再试。

**Q：怎么看 AI 用了多少 Token / 花了多少钱？**

```bash
harnesskit logs tail      # 每次调用的 Token 用量
harnesskit cost report    # 汇总费用报表
```

---

## 下一步

- 📖 [完整命令文档](README.md)
- 🗺️ [开发路线图](ROADMAP.md)
- 💡 尝试创建一个 **Blueprint 工作流**：把"语法检查 + AI 代码审查"串成一条自动化流水线
