"""Eval Browser Screen — Phase 7.4.

Three-pane layout:
  Left   : test suite list
  Top-right  : case list for the selected suite (green = passed, red = failed)
  Bottom-right: assertion details for the selected case
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.reactive import reactive
from textual.screen import Screen
from textual.widgets import Footer, Header, Label, ListItem, ListView, Static


# ---------------------------------------------------------------------------
# Status colour helpers
# ---------------------------------------------------------------------------


def _status_markup(status: str) -> str:
    """Return a Rich-coloured label for *status*."""
    if status == "passed":
        return "[bold green]✓ passed[/bold green]"
    if status == "failed":
        return "[bold red]✗ failed[/bold red]"
    if status == "error":
        return "[bold red]⚠ error[/bold red]"
    return f"[dim]{status}[/dim]"


# ---------------------------------------------------------------------------
# Scrollable Static panels
# ---------------------------------------------------------------------------


class _TextPanel(Static):
    """Generic scrollable panel with an inspectable ``content_text`` reactive."""

    DEFAULT_CSS = """
    _TextPanel {
        height: 1fr;
        padding: 1 2;
        background: $background;
        overflow-y: auto;
    }
    """

    content_text: reactive[str] = reactive("")

    def render(self) -> str:  # type: ignore[override]
        return self.content_text


# ---------------------------------------------------------------------------
# Format helpers
# ---------------------------------------------------------------------------


def _format_suite_summary(data: dict[str, Any]) -> str:
    """One-line Rich-markup summary of a suite shown in the left list."""
    name = data.get("name", "?")
    cases = data.get("cases") or []
    return f"{name}  [dim]({len(cases)} cases)[/dim]"


def _format_case_list(suite_data: dict[str, Any], results: dict[str, Any] | None) -> list[tuple[str, str]]:
    """Return ``[(case_id, markup_label), ...]`` coloured by result status.

    *results* is the most-recent eval report for this suite, or ``None``.
    """
    cases = suite_data.get("cases") or []
    case_statuses: dict[str, str] = {}
    if results:
        for c in results.get("cases") or []:
            case_statuses[c["id"]] = c.get("status", "unknown")

    items: list[tuple[str, str]] = []
    for case in cases:
        cid = case.get("id", "?")
        cname = case.get("name", cid)
        status = case_statuses.get(cid)
        if status == "passed":
            label = f"[green]✓[/green]  {cname}"
        elif status in ("failed", "error"):
            label = f"[red]✗[/red]  {cname}"
        else:
            label = f"[dim]•[/dim]  {cname}"
        items.append((cid, label))
    return items


def _format_assertion_detail(case_result: dict[str, Any] | None, case_def: dict[str, Any] | None) -> str:
    """Render full assertion detail for a case."""
    lines: list[str] = []

    if case_def:
        cid = case_def.get("id", "?")
        cname = case_def.get("name", cid)
        lines.append(f"[bold cyan]{cname}[/bold cyan]  [dim]id: {cid}[/dim]")
        lines.append("")

    if case_result is None:
        lines.append("[dim]尚无运行结果。\n\n"
                     "使用以下命令运行评估：\n"
                     "  [cyan]harnesskit eval run <target> --suite <suite-name>[/cyan][/dim]")
        if case_def:
            assertions = case_def.get("assertions") or []
            if assertions:
                lines.append("")
                lines.append(f"[bold]定义的断言（{len(assertions)} 个）：[/bold]")
                for a in assertions:
                    atype = a.get("type", "?")
                    path = a.get("path", "")
                    value = a.get("value", a.get("pattern", a.get("schema", "")))
                    lines.append(f"  [dim]• {atype}[/dim]  {path}  [dim]{value}[/dim]")
        return "\n".join(lines)

    status = case_result.get("status", "?")
    lines.append(f"状态：{_status_markup(status)}")

    duration = case_result.get("duration")
    if duration is not None:
        lines.append(f"耗时：[dim]{duration:.3f}s[/dim]")

    in_tok = case_result.get("input_tokens", 0)
    out_tok = case_result.get("output_tokens", 0)
    if in_tok or out_tok:
        lines.append(f"Tokens：[dim]in {in_tok} / out {out_tok}[/dim]")

    preview = case_result.get("output_preview", "")
    if preview:
        lines.append("")
        lines.append("[bold]输出预览：[/bold]")
        lines.append(f"[dim]{preview[:300]}[/dim]")

    assertions = case_result.get("assertions") or []
    if assertions:
        a_summary = case_result.get("assertion_summary") or {}
        total_a = a_summary.get("total", len(assertions))
        passed_a = a_summary.get("passed", 0)
        lines.append("")
        lines.append(f"[bold]断言（{passed_a}/{total_a} 通过）：[/bold]")
        for a in assertions:
            ok = a.get("passed", False)
            atype = a.get("type", "?")
            path = a.get("path") or ""
            msg = a.get("message", "")
            if ok:
                marker = "[green]✓[/green]"
            else:
                marker = "[red]✗[/red]"
            lines.append(f"  {marker}  [dim]{atype}[/dim]  {path}")
            if msg:
                lines.append(f"       [dim]{msg}[/dim]")

    error = case_result.get("error")
    if error:
        lines.append("")
        lines.append(f"[bold red]错误：[/bold red][dim]{error}[/dim]")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Main screen
# ---------------------------------------------------------------------------


class EvalBrowserScreen(Screen):
    """Eval result browser — Phase 7.4.

    Left pane   : all test suites.
    Right-top   : cases for the selected suite, coloured by pass/fail.
    Right-bottom: assertion detail for the selected case.
    """

    TITLE = "Eval 结果浏览"

    DEFAULT_CSS = """
    EvalBrowserScreen {
        layers: base;
    }
    #eval-layout {
        height: 1fr;
        layer: base;
    }
    #suite-sidebar {
        width: 30;
        border-right: tall $primary;
        padding: 0;
    }
    #suite-sidebar Label.sidebar-title {
        color: $primary;
        text-style: bold;
        padding: 0 2 0 2;
        height: 2;
        content-align: left middle;
    }
    #suite-list {
        height: 1fr;
        background: $surface;
        border: none;
    }
    #suite-list ListItem {
        padding: 0 2;
    }
    #suite-list ListItem:hover {
        background: $primary 20%;
    }
    #suite-list ListItem.--highlight {
        background: $primary 30%;
        color: $text;
    }
    #right-area {
        height: 1fr;
    }
    #case-panel-wrap {
        height: 1fr;
        border-bottom: tall $primary;
    }
    #case-panel-title {
        background: $primary 10%;
        color: $primary;
        text-style: bold;
        padding: 0 2;
        height: 2;
        content-align: left middle;
    }
    #case-list {
        height: 1fr;
        background: $surface;
        border: none;
    }
    #case-list ListItem {
        padding: 0 2;
    }
    #case-list ListItem:hover {
        background: $primary 20%;
    }
    #case-list ListItem.--highlight {
        background: $primary 30%;
        color: $text;
    }
    #assertion-panel-wrap {
        height: 1fr;
    }
    #assertion-panel-title {
        background: $primary 10%;
        color: $primary;
        text-style: bold;
        padding: 0 2;
        height: 2;
        content-align: left middle;
    }
    """

    BINDINGS = [
        Binding("escape", "go_back", "返回", priority=True, show=True),
        Binding("j", "cursor_down", "向下", show=True),
        Binding("k", "cursor_up", "向上", show=True),
        Binding("down", "cursor_down", "向下", show=False),
        Binding("up", "cursor_up", "向上", show=False),
        Binding("tab", "focus_next_pane", "切换面板", show=True),
    ]

    # Which pane has focus: "suites" | "cases"
    _active_pane: reactive[str] = reactive("suites")
    _suite_index: reactive[int] = reactive(0)
    _case_index: reactive[int] = reactive(0)

    def __init__(self, base_path: Path | None = None, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self._base_path = base_path
        self._suites: list[dict[str, Any]] = []
        # suite_name -> most-recent result report (or None)
        self._results: dict[str, dict[str, Any]] = {}

    # ------------------------------------------------------------------
    # Compose & lifecycle
    # ------------------------------------------------------------------

    def compose(self) -> ComposeResult:
        yield Header()
        with Horizontal(id="eval-layout"):
            with Vertical(id="suite-sidebar"):
                yield Label("🧪  Test Suites", classes="sidebar-title")
                yield ListView(id="suite-list")
            with Vertical(id="right-area"):
                with Vertical(id="case-panel-wrap"):
                    yield Label("Cases", id="case-panel-title")
                    yield ListView(id="case-list")
                with Vertical(id="assertion-panel-wrap"):
                    yield Label("断言详情", id="assertion-panel-title")
                    yield _TextPanel(id="assertion-panel")
        yield Footer()

    def on_mount(self) -> None:
        self._load_data()
        self._rebuild_suite_list()
        self.query_one("#suite-list", ListView).focus()

    # ------------------------------------------------------------------
    # Data helpers
    # ------------------------------------------------------------------

    def _load_data(self) -> None:
        """Load suites and most-recent result for each suite."""
        try:
            from harness_kit.eval import list_suites, load_suite, load_results  # noqa: PLC0415
            names = list_suites(self._base_path)
            self._suites = []
            for name in names:
                try:
                    self._suites.append(load_suite(name, self._base_path))
                except Exception:  # pylint: disable=broad-except
                    pass
            # Build a map: suite_name -> most recent result
            all_results = load_results(self._base_path)
            for r in reversed(all_results):  # most-recent first
                sname = r.get("suite", "")
                if sname and sname not in self._results:
                    self._results[sname] = r
        except Exception:  # pylint: disable=broad-except
            self._suites = []
            self._results = {}

    def _current_suite(self) -> dict[str, Any] | None:
        if not self._suites:
            return None
        idx = self._suite_index
        if 0 <= idx < len(self._suites):
            return self._suites[idx]
        return None

    def _current_result(self) -> dict[str, Any] | None:
        suite = self._current_suite()
        if suite is None:
            return None
        return self._results.get(suite.get("name", ""))

    def _current_case_def(self) -> dict[str, Any] | None:
        suite = self._current_suite()
        if suite is None:
            return None
        cases = suite.get("cases") or []
        idx = self._case_index
        if 0 <= idx < len(cases):
            return cases[idx]
        return None

    def _current_case_result(self) -> dict[str, Any] | None:
        result = self._current_result()
        if result is None:
            return None
        case_def = self._current_case_def()
        if case_def is None:
            return None
        cid = case_def.get("id", "")
        for c in result.get("cases") or []:
            if c.get("id") == cid:
                return c
        return None

    # ------------------------------------------------------------------
    # Rebuild helpers
    # ------------------------------------------------------------------

    def _rebuild_suite_list(self) -> None:
        lv = self.query_one("#suite-list", ListView)
        lv.clear()
        if not self._suites:
            lv.append(ListItem(Label("[dim]暂无测试套件[/dim]")))
            self._update_case_list()
            self._update_assertion_panel()
            return
        for suite in self._suites:
            lv.append(ListItem(Label(_format_suite_summary(suite))))
        self._suite_index = 0
        lv.index = 0
        self._update_case_list()

    def _update_case_list(self) -> None:
        suite = self._current_suite()
        result = self._current_result()

        # Update panel title
        title = self.query_one("#case-panel-title", Label)
        if suite:
            sname = suite.get("name", "?")
            summary = result.get("summary") if result else None
            if summary:
                p = summary.get("passed", 0)
                t = summary.get("total", 0)
                title.update(f"Cases — {sname}  [dim]({p}/{t} passed)[/dim]")
            else:
                title.update(f"Cases — {sname}")
        else:
            title.update("Cases")

        lv = self.query_one("#case-list", ListView)
        lv.clear()
        if suite is None:
            lv.append(ListItem(Label("[dim]请先选择测试套件[/dim]")))
            self._update_assertion_panel()
            return

        items = _format_case_list(suite, result)
        if not items:
            lv.append(ListItem(Label("[dim]该套件暂无 cases[/dim]")))
        else:
            for _cid, label in items:
                lv.append(ListItem(Label(label)))

        self._case_index = 0
        lv.index = 0
        self._update_assertion_panel()

    def _update_assertion_panel(self) -> None:
        case_def = self._current_case_def()
        case_result = self._current_case_result()
        text = _format_assertion_detail(case_result, case_def)
        panel = self.query_one("#assertion-panel", _TextPanel)
        panel.content_text = text
        panel.refresh()

    # ------------------------------------------------------------------
    # Events
    # ------------------------------------------------------------------

    def on_list_view_highlighted(self, event: ListView.Highlighted) -> None:
        if event.item is None:
            return
        lv_id = event.list_view.id
        try:
            children = list(event.list_view.children)
            idx = children.index(event.item)
        except (ValueError, TypeError):
            return

        if lv_id == "suite-list":
            self._suite_index = idx
            self._update_case_list()
        elif lv_id == "case-list":
            self._case_index = idx
            self._update_assertion_panel()

    # ------------------------------------------------------------------
    # Actions
    # ------------------------------------------------------------------

    def action_go_back(self) -> None:
        self.app.pop_screen()

    def action_focus_next_pane(self) -> None:
        if self._active_pane == "suites":
            self._active_pane = "cases"
            self.query_one("#case-list", ListView).focus()
        else:
            self._active_pane = "suites"
            self.query_one("#suite-list", ListView).focus()

    def action_cursor_down(self) -> None:
        if self._active_pane == "suites":
            lv = self.query_one("#suite-list", ListView)
            next_idx = min(self._suite_index + 1, max(len(self._suites) - 1, 0))
            lv.index = next_idx
            self._suite_index = next_idx
            self._update_case_list()
        else:
            suite = self._current_suite()
            max_idx = max(len(suite.get("cases") or []) - 1, 0) if suite else 0
            lv = self.query_one("#case-list", ListView)
            next_idx = min(self._case_index + 1, max_idx)
            lv.index = next_idx
            self._case_index = next_idx
            self._update_assertion_panel()

    def action_cursor_up(self) -> None:
        if self._active_pane == "suites":
            lv = self.query_one("#suite-list", ListView)
            prev_idx = max(self._suite_index - 1, 0)
            lv.index = prev_idx
            self._suite_index = prev_idx
            self._update_case_list()
        else:
            lv = self.query_one("#case-list", ListView)
            prev_idx = max(self._case_index - 1, 0)
            lv.index = prev_idx
            self._case_index = prev_idx
            self._update_assertion_panel()
