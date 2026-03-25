"""Skill Browser Screen — Phase 7.2.

Left pane  : searchable / filterable Skill list (ListView + Input).
Right pane : Skill detail — version, description, I/O definition.
Shortcuts  : j/k navigate, Enter view detail, r run hint, d diff hint, e edit hint.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Container, Horizontal, Vertical
from textual.reactive import reactive
from textual.screen import Screen
from textual.widgets import Footer, Header, Input, Label, ListItem, ListView, Static


# ---------------------------------------------------------------------------
# Detail panel widget with a testable reactive string
# ---------------------------------------------------------------------------


class SkillDetailPanel(Static):
    """Right-hand skill detail panel with an inspectable ``content_text`` reactive."""

    DEFAULT_CSS = """
    SkillDetailPanel {
        height: 1fr;
        padding: 2 3;
        background: $background;
        overflow-y: auto;
    }
    """

    content_text: reactive[str] = reactive("")

    def render(self) -> str:  # type: ignore[override]
        return self.content_text


# ---------------------------------------------------------------------------
# Rich-markup formatter for the right detail panel
# ---------------------------------------------------------------------------


def _format_skill_detail(skill: dict[str, Any]) -> str:
    """Return a Rich-markup string describing *skill*."""
    lines: list[str] = []

    name = skill.get("name", "?")
    version = skill.get("version", "?")
    description = skill.get("description", "")
    trigger = skill.get("trigger", "")
    changelog = skill.get("changelog", "")
    created_at = skill.get("created_at", "")

    lines.append(f"[bold cyan]{name}[/bold cyan]   [dim]{version}[/dim]")
    lines.append("")

    if description:
        lines.append(f"[bold]描述：[/bold]{description}")
    if trigger:
        lines.append(f"[bold]触发条件：[/bold]{trigger}")
    if created_at:
        lines.append(f"[bold]创建时间：[/bold][dim]{created_at[:19]}[/dim]")
    if changelog:
        lines.append(f"[bold]变更说明：[/bold]{changelog}")
    lines.append("")

    # ---------- Inputs ----------
    inputs: list[dict[str, Any]] = skill.get("inputs") or []
    if inputs:
        lines.append("[bold]输入参数：[/bold]")
        for inp in inputs:
            req = inp.get("required", True)
            default = inp.get("default")
            req_marker = "[red bold]*[/red bold] " if req else "  "
            def_str = f"  [dim](默认: {default})[/dim]" if default is not None else ""
            lines.append(
                f"  {req_marker}[green]{inp.get('name', '?')}[/green]"
                f" [dim]({inp.get('type', '?')})[/dim]{def_str}"
            )
        lines.append("")

    # ---------- Outputs ----------
    outputs: list[dict[str, Any]] = skill.get("outputs") or []
    if outputs:
        lines.append("[bold]输出：[/bold]")
        for out in outputs:
            lines.append(
                f"  • [yellow]{out.get('name', '?')}[/yellow]"
                f" [dim]({out.get('type', '?')})[/dim]"
            )
        lines.append("")

    # ---------- Assets ----------
    assets: dict[str, Any] = skill.get("assets") or {}
    if assets:
        lines.append("[bold]引用资产：[/bold]")
        prompts = assets.get("prompts")
        if isinstance(prompts, dict):
            for role, ref in prompts.items():
                lines.append(f"  • prompt [{role}]: [cyan]{ref}[/cyan]")
        elif isinstance(prompts, list):
            for ref in prompts:
                lines.append(f"  • prompt: [cyan]{ref}[/cyan]")
        for ref in assets.get("schemas") or []:
            lines.append(f"  • schema: [cyan]{ref}[/cyan]")
        for ref in assets.get("rules") or []:
            lines.append(f"  • rule:   [cyan]{ref}[/cyan]")
        ctx = assets.get("context")
        if ctx:
            lines.append(f"  • context: [cyan]{ctx}[/cyan]")
        lines.append("")

    # ---------- Examples ----------
    examples: list[Any] = skill.get("examples") or []
    if examples:
        lines.append(f"[bold]示例：[/bold]{len(examples)} 个")
        lines.append("")

    # ---------- Quick command hints ----------
    lines.append("[dim]快捷操作：[/dim]")
    lines.append(f"  [cyan]r[/cyan]  运行  →  harnesskit skill run {name}")
    lines.append(f"  [cyan]d[/cyan]  对比  →  harnesskit skill diff {name}@<v_old> {name}@{version}")
    lines.append(f"  [cyan]e[/cyan]  编辑  →  harnesskit skill save --file <{name}.yaml>")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Notification overlay (shown on r / d / e)
# ---------------------------------------------------------------------------


class _ActionNotice(Container):
    """Transient overlay showing a command hint to the user."""

    DEFAULT_CSS = """
    _ActionNotice {
        align: center middle;
        background: $background 80%;
        layer: overlay;
    }
    _ActionNotice > Container {
        width: 60;
        height: auto;
        background: $surface;
        border: double $accent;
        padding: 1 2;
    }
    _ActionNotice Label {
        margin-bottom: 0;
    }
    """

    def __init__(self, title: str, command: str, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self._title = title
        self._command = command

    def compose(self) -> ComposeResult:
        with Container():
            yield Label(f"[bold yellow]{self._title}[/bold yellow]")
            yield Label("")
            yield Label(f"[cyan]{self._command}[/cyan]")
            yield Label("")
            yield Label("[dim]按任意键关闭[/dim]")


# ---------------------------------------------------------------------------
# Main screen
# ---------------------------------------------------------------------------


class SkillBrowserScreen(Screen):
    """Skill browser — Phase 7.2.

    Left pane lists all skills (filterable via a search Input).
    Right pane shows the selected skill's full definition.
    """

    TITLE = "Skill 浏览器"

    DEFAULT_CSS = """
    SkillBrowserScreen {
        layers: base overlay;
    }
    #browser-layout {
        height: 1fr;
        layer: base;
    }
    #skill-sidebar {
        width: 30;
        border-right: tall $primary;
        padding: 0;
    }
    #skill-sidebar Label.sidebar-title {
        color: $primary;
        text-style: bold;
        padding: 0 2 0 2;
        height: 2;
        content-align: left middle;
    }
    #search-input {
        height: 3;
        margin: 0 1 1 1;
    }
    #skill-list {
        height: 1fr;
        background: $surface;
        border: none;
    }
    #skill-list ListItem {
        padding: 0 2;
    }
    #skill-list ListItem:hover {
        background: $primary 20%;
    }
    #skill-list ListItem.--highlight {
        background: $primary 30%;
        color: $text;
    }
    """

    BINDINGS = [
        Binding("escape", "go_back", "返回", priority=True, show=True),
        Binding("j", "cursor_down", "向下", show=True),
        Binding("k", "cursor_up", "向上", show=True),
        Binding("down", "cursor_down", "向下", show=False),
        Binding("up", "cursor_up", "向上", show=False),
        Binding("r", "run_skill", "运行", show=True),
        Binding("d", "diff_skill", "Diff", show=True),
        Binding("e", "edit_skill", "编辑", show=True),
    ]

    _selected_index: reactive[int] = reactive(0)
    _notice_visible: reactive[bool] = reactive(False)

    def __init__(self, base_path: Path | None = None, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self._base_path = base_path
        self._all_skills: list[dict[str, Any]] = []
        self._filtered_skills: list[dict[str, Any]] = []

    # ------------------------------------------------------------------
    # Compose & lifecycle
    # ------------------------------------------------------------------

    def compose(self) -> ComposeResult:
        yield Header()
        with Horizontal(id="browser-layout"):
            with Vertical(id="skill-sidebar"):
                yield Label("⚙  Skills", classes="sidebar-title")
                yield Input(placeholder="搜索 Skill…", id="search-input")
                yield ListView(id="skill-list")
            yield SkillDetailPanel(id="skill-detail")
        yield Footer()

    def on_mount(self) -> None:
        self._load_skills()
        self._rebuild_list()
        # Keep focus on the list so j/k/r/d/e bindings work immediately.
        self.query_one("#skill-list", ListView).focus()

    # ------------------------------------------------------------------
    # Data helpers
    # ------------------------------------------------------------------

    def _load_skills(self) -> None:
        """Load current-version metadata for all skills."""
        try:
            from harness_kit.skill import list_skills  # pylint: disable=import-outside-toplevel
            self._all_skills = list_skills(self._base_path)
        except Exception:  # pylint: disable=broad-except
            self._all_skills = []
        self._filtered_skills = list(self._all_skills)

    def _apply_filter(self, text: str) -> None:
        """Filter the skill list by *text* (case-insensitive name / description match)."""
        q = text.lower().strip()
        if q:
            self._filtered_skills = [
                s for s in self._all_skills
                if q in s.get("name", "").lower() or q in s.get("description", "").lower()
            ]
        else:
            self._filtered_skills = list(self._all_skills)
        self._rebuild_list()

    def _rebuild_list(self) -> None:
        """Re-populate the ListView from *_filtered_skills*."""
        list_view = self.query_one("#skill-list", ListView)
        list_view.clear()

        if not self._filtered_skills:
            self._update_detail_empty()
            return

        for skill in self._filtered_skills:
            name = skill.get("name", "?")
            version = skill.get("version", "?")
            list_view.append(ListItem(Label(f"{name}  [dim]{version}[/dim]")))

        # Reset selection to first item
        self._selected_index = 0
        list_view.index = 0
        self._update_detail(0)

    def _update_detail_empty(self) -> None:
        detail = self.query_one("#skill-detail", SkillDetailPanel)
        detail.content_text = (
            "[dim]暂无 Skill。\n\n"
            "使用以下命令创建第一个 Skill：\n"
            "  [cyan]harnesskit skill save --file my-skill.yaml[/cyan][/dim]"
        )
        detail.refresh()

    def _update_detail(self, index: int) -> None:
        """Render the detail panel for *_filtered_skills[index]*."""
        if not (0 <= index < len(self._filtered_skills)):
            return
        skill = self._filtered_skills[index]
        detail = self.query_one("#skill-detail", SkillDetailPanel)
        detail.content_text = _format_skill_detail(skill)
        detail.refresh()

    # ------------------------------------------------------------------
    # Events
    # ------------------------------------------------------------------

    def on_input_changed(self, event: Input.Changed) -> None:
        if event.input.id == "search-input":
            self._apply_filter(event.value)

    def on_list_view_highlighted(self, event: ListView.Highlighted) -> None:
        if event.item is not None:
            try:
                children = list(self.query_one("#skill-list", ListView).children)
                idx = children.index(event.item)
                self._selected_index = idx
                self._update_detail(idx)
            except (ValueError, TypeError):
                pass

    def on_key(self, event) -> None:  # type: ignore[override]
        """Dismiss any visible notice overlay on any key press."""
        if self._notice_visible and event.key not in ():
            self._notice_visible = False
            try:
                self.query_one("#action-notice").remove()
            except Exception:  # pylint: disable=broad-except
                pass

    # ------------------------------------------------------------------
    # Actions
    # ------------------------------------------------------------------

    def action_go_back(self) -> None:
        """Return to the main navigation screen."""
        self.app.pop_screen()

    def action_cursor_down(self) -> None:
        list_view = self.query_one("#skill-list", ListView)
        next_idx = min(self._selected_index + 1, max(len(self._filtered_skills) - 1, 0))
        list_view.index = next_idx
        self._selected_index = next_idx
        self._update_detail(next_idx)

    def action_cursor_up(self) -> None:
        list_view = self.query_one("#skill-list", ListView)
        prev_idx = max(self._selected_index - 1, 0)
        list_view.index = prev_idx
        self._selected_index = prev_idx
        self._update_detail(prev_idx)

    def _show_notice(self, title: str, command: str) -> None:
        """Mount a transient notice overlay."""
        if self._notice_visible:
            try:
                self.query_one("#action-notice").remove()
            except Exception:  # pylint: disable=broad-except
                pass
        self._notice_visible = True
        self.mount(_ActionNotice(title=title, command=command, id="action-notice"))

    def _current_skill(self) -> dict[str, Any] | None:
        if not self._filtered_skills:
            return None
        idx = self._selected_index
        if 0 <= idx < len(self._filtered_skills):
            return self._filtered_skills[idx]
        return None

    def action_run_skill(self) -> None:
        """Show run-command hint for the selected skill."""
        skill = self._current_skill()
        if skill is None:
            return
        name = skill.get("name", "?")
        self._show_notice("运行 Skill", f"harnesskit skill run {name}")

    def action_diff_skill(self) -> None:
        """Show diff-command hint for the selected skill."""
        skill = self._current_skill()
        if skill is None:
            return
        name = skill.get("name", "?")
        version = skill.get("version", "?")
        self._show_notice("Skill Diff", f"harnesskit skill diff {name}@<v_old> {name}@{version}")

    def action_edit_skill(self) -> None:
        """Show edit-command hint for the selected skill."""
        skill = self._current_skill()
        if skill is None:
            return
        name = skill.get("name", "?")
        self._show_notice("编辑 Skill", f"harnesskit skill save --file <{name}.yaml>")
