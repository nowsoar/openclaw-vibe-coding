"""HarnessKit TUI — main Textual application."""

from __future__ import annotations

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Container, Horizontal, Vertical
from textual.reactive import reactive
from textual.widgets import Footer, Header, Label, ListItem, ListView, Static

from harness_kit.tui.eval_browser import EvalBrowserScreen
from harness_kit.tui.logs_browser import LogsBrowserScreen
from harness_kit.tui.prompt_diff import PromptDiffScreen
from harness_kit.tui.skill_browser import SkillBrowserScreen


# ---------------------------------------------------------------------------
# Navigation items definition
# ---------------------------------------------------------------------------

NAV_ITEMS: list[tuple[str, str, str]] = [
    # (id, label, description)
    (
        "skills",
        "⚙  Skills",
        "[bold]Skills[/bold]\n\n"
        "可复用的 AI 能力单元。每个 Skill 封装了 Prompt、Schema、Rule 和 Context，\n"
        "可独立运行，也可组合进 Harness。\n\n"
        "[dim]命令：[/dim] harnesskit skill save / show / list / run / diff / clone",
    ),
    (
        "prompts",
        "📝  Prompts",
        "[bold]Prompt Diff 可视化[/bold]\n\n"
        "并排对比两个 Prompt 版本的差异。\n"
        "删除行高亮为红色，新增行高亮为绿色，支持行内字符级 diff。\n\n"
        "[dim]按 Enter 进入 Prompt Diff 浏览器[/dim]\n\n"
        "[dim]命令：[/dim] harnesskit prompt save / show / list / diff / history",
    ),
    (
        "harnesses",
        "🔧  Harnesses",
        "[bold]Harnesses[/bold]\n\n"
        "完整的 AI 运行时配置。组合多个 Skills，配置模型参数、记忆策略和约束规则。\n\n"
        "[dim]命令：[/dim] harnesskit harness create / show / list / run / clone",
    ),
    (
        "blueprints",
        "📋  Blueprints",
        "[bold]Blueprints[/bold]\n\n"
        "工作流编排。混合确定性节点（Shell 命令）和 Agentic 节点（Harness/Skill），\n"
        "支持步骤间变量传递与条件分支。\n\n"
        "[dim]命令：[/dim] harnesskit blueprint create / validate / run / list",
    ),
    (
        "eval",
        "🧪  Eval",
        "[bold]Eval（评估引擎）[/bold]\n\n"
        "量化测试 Harness/Skill 效果。支持 A/B 对比、多模型 Benchmark，\n"
        "断言类型：contains / regex / json_schema / custom。\n\n"
        "[dim]命令：[/dim] harnesskit eval suite-add / run / compare / benchmark",
    ),
    (
        "logs",
        "📜  Logs",
        "[bold]Logs（调用日志）[/bold]\n\n"
        "完整的 LLM 调用追踪。记录时间、Skill、模型、Token 数、成本、耗时。\n"
        "支持实时 tail、关键词搜索、CSV 导出。\n\n"
        "[dim]命令：[/dim] harnesskit logs tail / search / export",
    ),
    (
        "cost",
        "💰  Cost",
        "[bold]Cost（成本追踪）[/bold]\n\n"
        "按 Skill / Harness / 模型分组统计费用。支持日报/周报/月报，\n"
        "单次和日累计预警阈值可配置。\n\n"
        "[dim]命令：[/dim] harnesskit cost report / breakdown",
    ),
    (
        "improve",
        "🔄  Improve",
        "[bold]Improve（改进飞轮）[/bold]\n\n"
        "记录每次 Harness 改进的根因、修复方案和效果变化。\n"
        "让每次失败都变成进化机会。\n\n"
        "[dim]命令：[/dim] harnesskit improve log / history / report",
    ),
    (
        "health",
        "🏥  Health",
        "[bold]Health（健康检查）[/bold]\n\n"
        "扫描 .harness/ 目录健康状态：过期 Skill、低成功率、未使用资产。\n"
        "自动修复可修复问题。\n\n"
        "[dim]命令：[/dim] harnesskit health check / fix",
    ),
    (
        "settings",
        "⚙️  Settings",
        "[bold]Settings（配置）[/bold]\n\n"
        "全局配置文件：.harness/config.yaml\n\n"
        "[dim]配置项：[/dim]\n"
        "  • default_model — 默认模型\n"
        "  • log_level     — 日志级别\n"
        "  • model_prices  — 各模型价格（用于成本计算）",
    ),
]


# ---------------------------------------------------------------------------
# Widgets
# ---------------------------------------------------------------------------


class Sidebar(Vertical):
    """Left navigation sidebar."""

    DEFAULT_CSS = """
    Sidebar {
        width: 24;
        background: $surface;
        border-right: tall $primary;
        padding: 1 0;
    }
    Sidebar Label.sidebar-title {
        color: $primary;
        text-style: bold;
        padding: 0 2 1 2;
        width: 100%;
    }
    Sidebar ListView {
        background: $surface;
        border: none;
        padding: 0;
    }
    Sidebar ListItem {
        padding: 0 2;
    }
    Sidebar ListItem:hover {
        background: $primary 20%;
    }
    Sidebar ListItem.--highlight {
        background: $primary 30%;
        color: $text;
    }
    """

    def compose(self) -> ComposeResult:
        yield Label("HarnessKit", classes="sidebar-title")
        items = [ListItem(Label(label), id=item_id) for item_id, label, _ in NAV_ITEMS]
        yield ListView(*items)


class ContentPanel(Static):
    """Right main content area."""

    DEFAULT_CSS = """
    ContentPanel {
        padding: 2 3;
        background: $background;
    }
    """

    content_text: reactive[str] = reactive("")

    def render(self) -> str:  # type: ignore[override]
        return self.content_text


class HelpOverlay(Container):
    """Help overlay widget shown when '?' is pressed."""

    DEFAULT_CSS = """
    HelpOverlay {
        align: center middle;
        background: $background 80%;
        layer: overlay;
    }
    HelpOverlay > Container {
        width: 50;
        height: auto;
        background: $surface;
        border: double $primary;
        padding: 1 2;
    }
    HelpOverlay Label {
        margin-bottom: 1;
    }
    """

    def compose(self) -> ComposeResult:
        with Container():
            yield Label("[bold yellow]键盘快捷键[/bold yellow]")
            yield Label("")
            yield Label("[cyan]j / ↓[/cyan]    向下移动")
            yield Label("[cyan]k / ↑[/cyan]    向上移动")
            yield Label("[cyan]Enter[/cyan]    进入 / 选择  （Skills → Skill 浏览器 | Prompts → Prompt Diff | Eval → Eval 结果浏览器 | Logs → 实时日志流）")
            yield Label("[cyan]Esc[/cyan]      返回上一屏")
            yield Label("[cyan]?[/cyan]        显示 / 关闭帮助")
            yield Label("[cyan]q[/cyan]        退出 HarnessKit TUI")
            yield Label("")
            yield Label("[bold]Skill 浏览器快捷键[/bold]")
            yield Label("[cyan]r[/cyan]        运行 Skill（显示命令）")
            yield Label("[cyan]d[/cyan]        对比版本（显示命令）")
            yield Label("[cyan]e[/cyan]        编辑 Skill（显示命令）")
            yield Label("")
            yield Label("[bold]Prompt Diff 快捷键[/bold]")
            yield Label("[cyan]j / k[/cyan]    同步滚动 diff 面板")
            yield Label("[cyan]Esc[/cyan]      返回主菜单")
            yield Label("")
            yield Label("[bold]Eval 结果浏览器快捷键[/bold]")
            yield Label("[cyan]Tab[/cyan]      切换 Suites / Cases 面板")
            yield Label("[cyan]j / k[/cyan]    在当前面板上下移动")
            yield Label("[cyan]Esc[/cyan]      返回主菜单")
            yield Label("")
            yield Label("[bold]实时日志流快捷键[/bold]")
            yield Label("[cyan]Space[/cyan]    暂停 / 继续实时刷新")
            yield Label("[cyan]r[/cyan]        立即刷新日志")
            yield Label("[cyan]j / k[/cyan]    滚动日志面板")
            yield Label("[cyan]Esc[/cyan]      返回主菜单")
            yield Label("")
            yield Label("[dim]按任意键关闭[/dim]")


# ---------------------------------------------------------------------------
# Main App
# ---------------------------------------------------------------------------


class HarnessKitApp(App):
    """HarnessKit TUI — interactive terminal interface for managing AI harnesses."""

    TITLE = "HarnessKit"
    SUB_TITLE = "Local AI Harness Engineering Toolkit"

    CSS = """
    Screen {
        layers: base overlay;
    }
    #main-layout {
        height: 1fr;
        layer: base;
    }
    #content-area {
        height: 1fr;
    }
    #content-title {
        background: $primary 15%;
        color: $primary;
        text-style: bold;
        padding: 0 3;
        height: 3;
        content-align: left middle;
    }
    ContentPanel {
        height: 1fr;
        overflow-y: auto;
    }
    """

    BINDINGS = [
        Binding("q", "quit", "退出", priority=True),
        Binding("j", "cursor_down", "向下", show=True),
        Binding("k", "cursor_up", "向上", show=True),
        Binding("question_mark", "toggle_help", "帮助", show=True),
        Binding("enter", "select_item", "选择", show=True),
        Binding("down", "cursor_down", "向下", show=False),
        Binding("up", "cursor_up", "向上", show=False),
    ]

    _help_visible: reactive[bool] = reactive(False)
    _selected_index: reactive[int] = reactive(0)

    def compose(self) -> ComposeResult:
        yield Header()
        with Horizontal(id="main-layout"):
            yield Sidebar()
            with Vertical(id="content-area"):
                yield Label("", id="content-title")
                yield ContentPanel(id="content-panel")
        yield Footer()

    def on_mount(self) -> None:
        """Initialize the TUI with the first nav item selected."""
        self._update_content(0)
        list_view = self.query_one(ListView)
        list_view.index = 0

    def _update_content(self, index: int) -> None:
        """Update the content panel to show information for the nav item at *index*."""
        if not (0 <= index < len(NAV_ITEMS)):
            return
        item_id, label, description = NAV_ITEMS[index]
        title_label = self.query_one("#content-title", Label)
        title_label.update(label)
        panel = self.query_one("#content-panel", ContentPanel)
        panel.content_text = description
        panel.refresh()

    # ------------------------------------------------------------------
    # Actions
    # ------------------------------------------------------------------

    def action_cursor_down(self) -> None:
        list_view = self.query_one(ListView)
        next_idx = min(self._selected_index + 1, len(NAV_ITEMS) - 1)
        list_view.index = next_idx
        self._selected_index = next_idx
        self._update_content(next_idx)

    def action_cursor_up(self) -> None:
        list_view = self.query_one(ListView)
        prev_idx = max(self._selected_index - 1, 0)
        list_view.index = prev_idx
        self._selected_index = prev_idx
        self._update_content(prev_idx)

    def action_select_item(self) -> None:
        """Activate the currently highlighted nav item.

        Pressing Enter on the *Skills* section opens the dedicated
        :class:`SkillBrowserScreen`; pressing Enter on *Prompts* opens the
        :class:`PromptDiffScreen`; all other sections simply refresh
        the description in the content panel.
        """
        idx = self._selected_index
        if 0 <= idx < len(NAV_ITEMS):
            item_id = NAV_ITEMS[idx][0]
            if item_id == "skills":
                self.push_screen(SkillBrowserScreen())
                return
            if item_id == "prompts":
                self.push_screen(PromptDiffScreen())
                return
            if item_id == "eval":
                self.push_screen(EvalBrowserScreen())
                return
            if item_id == "logs":
                self.push_screen(LogsBrowserScreen())
                return
        self._update_content(idx)

    def on_list_view_selected(self, event: ListView.Selected) -> None:
        """Handle list item selection (triggered by Enter in the ListView).

        The ListView consumes the Enter key to fire this event before the
        App-level binding runs.  We use it to navigate into the Skill browser
        or the Prompt Diff screen.
        """
        idx = self._selected_index
        if 0 <= idx < len(NAV_ITEMS):
            item_id = NAV_ITEMS[idx][0]
            if item_id == "skills":
                self.push_screen(SkillBrowserScreen())
            elif item_id == "prompts":
                self.push_screen(PromptDiffScreen())
            elif item_id == "eval":
                self.push_screen(EvalBrowserScreen())
            elif item_id == "logs":
                self.push_screen(LogsBrowserScreen())

    def action_toggle_help(self) -> None:
        self._help_visible = not self._help_visible
        if self._help_visible:
            self.mount(HelpOverlay(id="help-overlay"))
        else:
            overlay = self.query_one("#help-overlay")
            overlay.remove()

    def on_key(self, event) -> None:  # type: ignore[override]
        """Close help overlay on any key when it is visible."""
        if self._help_visible and event.key not in ("question_mark",):
            self._help_visible = False
            try:
                overlay = self.query_one("#help-overlay")
                overlay.remove()
            except Exception:
                pass

    # ------------------------------------------------------------------
    # ListView selection event
    # ------------------------------------------------------------------

    def on_list_view_highlighted(self, event: ListView.Highlighted) -> None:
        """Sync content panel when user navigates list view with mouse or arrow keys."""
        if event.item is not None:
            try:
                idx = list(self.query_one(ListView).children).index(event.item)
                self._selected_index = idx
                self._update_content(idx)
            except ValueError:
                pass


def run_tui() -> None:
    """Entry point — launch the HarnessKit TUI."""
    app = HarnessKitApp()
    app.run()


if __name__ == "__main__":
    run_tui()
