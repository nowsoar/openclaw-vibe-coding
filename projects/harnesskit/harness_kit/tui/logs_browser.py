"""Logs Browser Screen — Phase 7.5: 实时日志流 (Real-time Log Stream).

Layout:
  Filter bar  : Skill filter | Since filter | Search/highlight | Pause indicator
  Status bar  : current filter summary and record count
  Log panel   : scrollable Rich-markup log lines, auto-refreshed every 2 s
  Footer      : key bindings
"""

from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path
from typing import Any

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.reactive import reactive
from textual.screen import Screen
from textual.widgets import Footer, Header, Input, Label, Static


# ---------------------------------------------------------------------------
# Scrollable text panel
# ---------------------------------------------------------------------------


class _TextPanel(Static):
    """Scrollable text panel for log display."""

    DEFAULT_CSS = """
    _TextPanel {
        height: 1fr;
        padding: 0 1;
        background: $background;
        overflow-y: auto;
    }
    """

    content_text: reactive[str] = reactive("")

    def render(self) -> str:  # type: ignore[override]
        return self.content_text


# ---------------------------------------------------------------------------
# Pure formatting helpers (no Textual dependency — testable standalone)
# ---------------------------------------------------------------------------


def _escape_markup(text: str) -> str:
    """Escape Rich markup special characters in *text*."""
    return text.replace("[", "\\[").replace("]", "\\]")


def _format_timestamp(ts: str) -> str:
    """Shorten an ISO-8601 timestamp to ``YYYY-MM-DD HH:MM:SS``."""
    try:
        dt = datetime.fromisoformat(ts)
        return dt.strftime("%Y-%m-%d %H:%M:%S")
    except Exception:
        return ts[:19] if len(ts) >= 19 else ts


def _format_status(status: str) -> str:
    """Return a coloured Rich markup indicator for *status*."""
    if status == "success":
        return "[bold green]✓[/bold green]"
    if status == "error":
        return "[bold red]✗[/bold red]"
    return f"[yellow]{_escape_markup(status)}[/yellow]"


def _format_record(rec: dict[str, Any], search: str = "") -> str:
    """Format one log record as a single Rich-markup line.

    When *search* is provided and matches the skill, model, or timestamp, the
    whole line is highlighted with a dark-blue background so it stands out.
    """
    ts_str = _format_timestamp(rec.get("timestamp", ""))
    skill = rec.get("skill", "-")
    model = rec.get("model", "-")
    status = rec.get("status", "?")
    duration = rec.get("duration") or 0.0
    total_tokens = rec.get("total_tokens") or 0
    cost = rec.get("cost")

    status_str = _format_status(status)
    cost_str = f"${cost:.4f}" if cost is not None else "  -   "

    # Truncate long values so columns stay readable
    skill_col = _escape_markup(skill[:20].ljust(20))
    model_col = _escape_markup(model[:18].ljust(18))

    line = (
        f"[dim]{ts_str}[/dim]  "
        f"[cyan]{skill_col}[/cyan]  "
        f"[dim]{model_col}[/dim]  "
        f"{status_str}  "
        f"[dim]{duration:6.2f}s[/dim]  "
        f"[dim]{total_tokens:>6}tok[/dim]  "
        f"[yellow]{cost_str}[/yellow]"
    )

    # Highlight entire row when search term is found in key fields
    if search:
        pattern = re.compile(re.escape(search), re.IGNORECASE)
        searchable = f"{ts_str} {skill} {model} {status}"
        if pattern.search(searchable):
            line = f"[on dark_blue]{line}[/on dark_blue]"

    return line


def _format_log_panel(
    records: list[dict[str, Any]],
    search: str = "",
    paused: bool = False,
) -> str:
    """Render all *records* into a Rich markup string for display.

    Parameters
    ----------
    records:
        Log records to display (ordered oldest-first).
    search:
        Keyword to highlight; rows containing this string are blue-tinted.
    paused:
        When ``True``, appends a pause-indicator at the bottom.
    """
    if not records:
        return (
            "[dim]暂无日志记录。\n\n"
            "运行 Skill 后，调用日志将自动出现在这里。\n\n"
            "命令示例：\n"
            "  [cyan]harnesskit skill run <name> --var key=value[/cyan]\n\n"
            "或查看日志文件：\n"
            "  [cyan]harnesskit logs tail[/cyan][/dim]"
        )

    lines: list[str] = []
    header = (
        "[bold]时间                  Skill                  Model               "
        "状态    耗时        Tokens    费用[/bold]"
    )
    lines.append(header)
    lines.append("[dim]" + "─" * 90 + "[/dim]")

    for rec in records:
        lines.append(_format_record(rec, search))

    if paused:
        lines.append("")
        lines.append("[bold yellow]⏸  已暂停 — 按 Space 继续实时刷新[/bold yellow]")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Main screen
# ---------------------------------------------------------------------------


class LogsBrowserScreen(Screen):
    """Real-time log stream browser — Phase 7.5.

    Displays the last N LLM call log entries with automatic refresh every
    2 seconds.  Supports:

    * Filtering by Skill name (partial, case-insensitive).
    * Filtering by time window (e.g. ``1d``, ``2h``, ``30m``).
    * Keyword search with full-row highlight.
    * Pause / resume live refresh (``Space``).
    * Manual refresh (``r``).
    * Vim-style scroll with ``j`` / ``k``.
    """

    TITLE = "实时日志流"

    DEFAULT_CSS = """
    LogsBrowserScreen {
        layers: base;
    }
    #logs-layout {
        height: 1fr;
        layer: base;
    }
    #filter-bar {
        height: 3;
        background: $surface;
        border-bottom: tall $primary;
        padding: 0 1;
        align: left middle;
    }
    #filter-bar Label.filter-label {
        height: 1;
        content-align: left middle;
        padding: 0 1;
        color: $text-muted;
    }
    #skill-filter {
        width: 18;
        border: tall $primary 30%;
        background: $background;
        padding: 0 1;
    }
    #since-filter {
        width: 12;
        border: tall $primary 30%;
        background: $background;
        padding: 0 1;
    }
    #search-input {
        width: 20;
        border: tall $primary 30%;
        background: $background;
        padding: 0 1;
    }
    #pause-indicator {
        width: 14;
        text-style: bold;
        padding: 0 2;
        content-align: center middle;
    }
    #status-bar {
        height: 2;
        background: $primary 10%;
        color: $primary;
        text-style: bold;
        padding: 0 2;
        content-align: left middle;
    }
    #log-panel {
        height: 1fr;
        overflow-y: auto;
    }
    """

    BINDINGS = [
        Binding("escape", "go_back", "返回", priority=True, show=True),
        Binding("space", "toggle_pause", "暂停/继续", show=True, priority=True),
        Binding("r", "refresh_now", "刷新", show=True, priority=True),
        Binding("j", "scroll_down", "向下", show=True),
        Binding("k", "scroll_up", "向上", show=True),
        Binding("down", "scroll_down", "向下", show=False),
        Binding("up", "scroll_up", "向上", show=False),
    ]

    _paused: reactive[bool] = reactive(False)

    def __init__(self, base_path: Path | None = None, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self._base_path = base_path
        self._records: list[dict[str, Any]] = []

    # ------------------------------------------------------------------
    # Compose & lifecycle
    # ------------------------------------------------------------------

    def compose(self) -> ComposeResult:
        yield Header()
        with Vertical(id="logs-layout"):
            with Horizontal(id="filter-bar"):
                yield Label("Skill:", classes="filter-label")
                yield Input(placeholder="所有 Skill", id="skill-filter")
                yield Label("Since:", classes="filter-label")
                yield Input(placeholder="1d / 2h / 30m", id="since-filter")
                yield Label("搜索:", classes="filter-label")
                yield Input(placeholder="关键词高亮", id="search-input")
                yield Label("", id="pause-indicator")
            yield Label("📜  实时日志流", id="status-bar")
            yield _TextPanel(id="log-panel")
        yield Footer()

    def on_mount(self) -> None:
        self._load_logs()
        self._update_panel()
        self._update_pause_indicator()
        # Auto-refresh every 2 seconds
        self.set_interval(2.0, self._auto_refresh)

    # ------------------------------------------------------------------
    # Filter accessors
    # ------------------------------------------------------------------

    def _skill_filter(self) -> str | None:
        """Return the current skill filter text, or None if empty."""
        try:
            val = self.query_one("#skill-filter", Input).value.strip()
            return val or None
        except Exception:  # pylint: disable=broad-except
            return None

    def _since_filter(self) -> str | None:
        """Return the current since filter text, or None if empty."""
        try:
            val = self.query_one("#since-filter", Input).value.strip()
            return val or None
        except Exception:  # pylint: disable=broad-except
            return None

    def _search_text(self) -> str:
        """Return the current search/highlight keyword."""
        try:
            return self.query_one("#search-input", Input).value.strip()
        except Exception:  # pylint: disable=broad-except
            return ""

    # ------------------------------------------------------------------
    # Data loading
    # ------------------------------------------------------------------

    def _load_logs(self) -> None:
        """Read logs from disk using current filter state."""
        try:
            from harness_kit.call_logger import tail_logs  # noqa: PLC0415

            since = self._since_filter()
            records = tail_logs(n=200, since=since, base=self._base_path)

            # Apply partial, case-insensitive skill filter client-side
            skill = self._skill_filter()
            if skill:
                records = [
                    r for r in records
                    if skill.lower() in r.get("skill", "").lower()
                ]
            self._records = records
        except Exception:  # pylint: disable=broad-except
            self._records = []

    # ------------------------------------------------------------------
    # Panel update
    # ------------------------------------------------------------------

    def _update_panel(self) -> None:
        """Refresh the log panel and status bar."""
        search = self._search_text()
        text = _format_log_panel(self._records, search=search, paused=self._paused)
        try:
            panel = self.query_one("#log-panel", _TextPanel)
            panel.content_text = text
            panel.refresh()
        except Exception:  # pylint: disable=broad-except
            pass
        self._update_status_bar()

    def _update_status_bar(self) -> None:
        try:
            skill = self._skill_filter() or "全部"
            since = self._since_filter() or "全部时间"
            count = len(self._records)
            mode = "[bold yellow]⏸ 暂停[/bold yellow]" if self._paused else "[bold green]▶ 实时[/bold green]"
            status = self.query_one("#status-bar", Label)
            status.update(
                f"📜  实时日志流  |  Skill: {skill}  |  时间: {since}  |  "
                f"共 {count} 条记录  |  {mode}"
            )
        except Exception:  # pylint: disable=broad-except
            pass

    def _update_pause_indicator(self) -> None:
        try:
            indicator = self.query_one("#pause-indicator", Label)
            if self._paused:
                indicator.update("[bold yellow]⏸ 已暂停[/bold yellow]")
            else:
                indicator.update("[bold green]▶ 实时[/bold green]")
        except Exception:  # pylint: disable=broad-except
            pass

    # ------------------------------------------------------------------
    # Auto-refresh
    # ------------------------------------------------------------------

    def _auto_refresh(self) -> None:
        """Called by the timer every 2 s.  No-ops when paused."""
        if not self._paused:
            self._load_logs()
            self._update_panel()

    # ------------------------------------------------------------------
    # Input events
    # ------------------------------------------------------------------

    def on_input_changed(self, event: Input.Changed) -> None:
        """Re-apply filters when any input field changes."""
        if event.input.id in ("skill-filter", "since-filter"):
            self._load_logs()
        self._update_panel()

    # ------------------------------------------------------------------
    # Actions
    # ------------------------------------------------------------------

    def action_go_back(self) -> None:
        self.app.pop_screen()

    def action_toggle_pause(self) -> None:
        """Toggle live-refresh pause state."""
        self._paused = not self._paused
        self._update_pause_indicator()
        if not self._paused:
            # Resume: immediately pull latest logs
            self._load_logs()
        self._update_panel()

    def action_refresh_now(self) -> None:
        """Force an immediate reload regardless of pause state."""
        self._load_logs()
        self._update_panel()

    def action_scroll_down(self) -> None:
        try:
            self.query_one("#log-panel", _TextPanel).scroll_down()
        except Exception:  # pylint: disable=broad-except
            pass

    def action_scroll_up(self) -> None:
        try:
            self.query_one("#log-panel", _TextPanel).scroll_up()
        except Exception:  # pylint: disable=broad-except
            pass
