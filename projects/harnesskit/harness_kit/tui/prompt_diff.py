"""Prompt Diff Screen — Phase 7.3.

Side-by-side prompt version comparison with syntax-coloured diff highlighting.
Left pane : old version  (removed lines in red)
Right pane : new version (added lines in green)
Inline diff for changed lines is also computed and highlighted.

Navigation:
  Escape       — return to main app
  j / ↓        — scroll down one line
  k / ↑        — scroll up one line
  p            — select prompt (cycle through available prompts)
  o / n        — select old / new version
"""

from __future__ import annotations

import difflib
from pathlib import Path
from typing import Any

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.reactive import reactive
from textual.screen import Screen
from textual.widgets import Footer, Header, Label, ListItem, ListView, Static


# ---------------------------------------------------------------------------
# Helpers — diff computation
# ---------------------------------------------------------------------------


def _inline_diff(line_a: str, line_b: str) -> tuple[str, str]:
    """Return Rich-markup versions of *line_a* and *line_b* with per-character
    highlighting for the characters that changed.

    Unchanged characters are left as-is; changed characters are wrapped with
    ``[bold red]…[/bold red]`` (old side) or ``[bold green]…[/bold green]``
    (new side).
    """
    matcher = difflib.SequenceMatcher(None, line_a, line_b, autojunk=False)
    old_parts: list[str] = []
    new_parts: list[str] = []
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        old_seg = _escape_markup(line_a[i1:i2])
        new_seg = _escape_markup(line_b[j1:j2])
        if tag == "equal":
            old_parts.append(old_seg)
            new_parts.append(new_seg)
        elif tag == "replace":
            old_parts.append(f"[bold red]{old_seg}[/bold red]")
            new_parts.append(f"[bold green]{new_seg}[/bold green]")
        elif tag == "delete":
            old_parts.append(f"[bold red]{old_seg}[/bold red]")
        elif tag == "insert":
            new_parts.append(f"[bold green]{new_seg}[/bold green]")
    return "".join(old_parts), "".join(new_parts)


def _escape_markup(text: str) -> str:
    """Escape Rich markup special characters in *text*."""
    return text.replace("[", "\\[").replace("]", "\\]")


def build_diff_panes(
    old_content: str,
    new_content: str,
    old_label: str = "old",
    new_label: str = "new",
) -> tuple[str, str]:
    """Build Rich-markup strings for the left (old) and right (new) panes.

    Returns ``(left_markup, right_markup)``.

    Algorithm
    ---------
    1.  Run ``difflib.SequenceMatcher`` on the two lists of lines.
    2.  For *equal* blocks: render lines with dim colour.
    3.  For *replace* blocks: apply :func:`_inline_diff` per corresponding
        line pair; left gets red background, right gets green background.
    4.  For *delete* blocks: left shows the removed line in red; right shows
        a blank placeholder in red.
    5.  For *insert* blocks: left shows a blank placeholder in green; right
        shows the added line in green.
    """
    old_lines = old_content.splitlines()
    new_lines = new_content.splitlines()

    left_lines: list[str] = []
    right_lines: list[str] = []

    # Header
    left_lines.append(f"[bold cyan]─── {_escape_markup(old_label)} ───[/bold cyan]")
    right_lines.append(f"[bold cyan]─── {_escape_markup(new_label)} ───[/bold cyan]")
    left_lines.append("")
    right_lines.append("")

    matcher = difflib.SequenceMatcher(None, old_lines, new_lines, autojunk=False)
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == "equal":
            for line in old_lines[i1:i2]:
                escaped = _escape_markup(line)
                left_lines.append(f"[dim]  {escaped}[/dim]")
                right_lines.append(f"[dim]  {escaped}[/dim]")
        elif tag == "replace":
            old_block = old_lines[i1:i2]
            new_block = new_lines[j1:j2]
            # Pair up as many lines as possible for inline diff
            pairs = max(len(old_block), len(new_block))
            for idx in range(pairs):
                if idx < len(old_block) and idx < len(new_block):
                    lo, ln = _inline_diff(old_block[idx], new_block[idx])
                    left_lines.append(f"[on dark_red]- {lo}[/on dark_red]")
                    right_lines.append(f"[on dark_green]+ {ln}[/on dark_green]")
                elif idx < len(old_block):
                    esc = _escape_markup(old_block[idx])
                    left_lines.append(f"[red]- {esc}[/red]")
                    right_lines.append(f"[dim red]~[/dim red]")
                else:
                    esc = _escape_markup(new_block[idx])
                    left_lines.append(f"[dim green]~[/dim green]")
                    right_lines.append(f"[green]+ {esc}[/green]")
        elif tag == "delete":
            for line in old_lines[i1:i2]:
                esc = _escape_markup(line)
                left_lines.append(f"[red]- {esc}[/red]")
                right_lines.append(f"[dim red]~[/dim red]")
        elif tag == "insert":
            for line in new_lines[j1:j2]:
                esc = _escape_markup(line)
                left_lines.append(f"[dim green]~[/dim green]")
                right_lines.append(f"[green]+ {esc}[/green]")

    if not old_lines and not new_lines:
        left_lines.append("[dim](空)[/dim]")
        right_lines.append("[dim](空)[/dim]")

    return "\n".join(left_lines), "\n".join(right_lines)


# ---------------------------------------------------------------------------
# Diff pane widget
# ---------------------------------------------------------------------------


class _DiffPane(Static):
    """Scrollable pane that displays one side of the diff."""

    DEFAULT_CSS = """
    _DiffPane {
        height: 1fr;
        padding: 1 2;
        background: $background;
        overflow-y: auto;
        overflow-x: auto;
    }
    """

    content_text: reactive[str] = reactive("")

    def render(self) -> str:  # type: ignore[override]
        return self.content_text


# ---------------------------------------------------------------------------
# Version selector widget (left sidebar)
# ---------------------------------------------------------------------------


class _VersionSelector(Vertical):
    """Left sidebar listing prompts and their versions."""

    DEFAULT_CSS = """
    _VersionSelector {
        width: 28;
        border-right: tall $primary;
        padding: 0;
    }
    _VersionSelector Label.section-title {
        color: $primary;
        text-style: bold;
        padding: 0 2 0 2;
        height: 2;
        content-align: left middle;
    }
    _VersionSelector Label.version-label {
        color: $text-muted;
        padding: 0 2 0 2;
        height: 1;
    }
    _VersionSelector ListView {
        background: $surface;
        border: none;
        height: auto;
        max-height: 10;
    }
    _VersionSelector ListItem {
        padding: 0 2;
    }
    _VersionSelector ListItem:hover {
        background: $primary 20%;
    }
    _VersionSelector ListItem.--highlight {
        background: $primary 30%;
        color: $text;
    }
    """


# ---------------------------------------------------------------------------
# Main screen
# ---------------------------------------------------------------------------


class PromptDiffScreen(Screen):
    """Prompt Diff viewer — Phase 7.3.

    Shows two prompt versions side-by-side with coloured diff highlighting.
    Left pane = old version (red for removed lines).
    Right pane = new version (green for added lines).
    Inline character-level diff is applied to changed lines.
    """

    TITLE = "Prompt Diff 可视化"

    DEFAULT_CSS = """
    PromptDiffScreen {
        layers: base;
    }
    #diff-layout {
        height: 1fr;
        layer: base;
    }
    #selector-panel {
        width: 28;
        border-right: tall $primary;
        padding: 0;
    }
    #selector-panel Label.section-title {
        color: $primary;
        text-style: bold;
        padding: 0 2 0 2;
        height: 2;
        content-align: left middle;
    }
    #selector-panel Label.version-label {
        color: $text-muted;
        padding: 0 1 0 2;
        height: 1;
    }
    #prompt-list {
        height: auto;
        max-height: 8;
        background: $surface;
        border: none;
    }
    #prompt-list ListItem {
        padding: 0 2;
    }
    #prompt-list ListItem:hover {
        background: $primary 20%;
    }
    #prompt-list ListItem.--highlight {
        background: $primary 30%;
        color: $text;
    }
    #old-version-list {
        height: auto;
        max-height: 6;
        background: $surface;
        border: none;
    }
    #new-version-list {
        height: auto;
        max-height: 6;
        background: $surface;
        border: none;
    }
    #old-version-list ListItem, #new-version-list ListItem {
        padding: 0 2;
    }
    #old-version-list ListItem:hover, #new-version-list ListItem:hover {
        background: $primary 20%;
    }
    #old-version-list ListItem.--highlight, #new-version-list ListItem.--highlight {
        background: $primary 30%;
        color: $text;
    }
    #diff-area {
        height: 1fr;
    }
    #left-pane {
        width: 1fr;
        border-right: tall $primary 30%;
    }
    #right-pane {
        width: 1fr;
    }
    #status-bar {
        height: 1;
        background: $surface;
        padding: 0 2;
        color: $text-muted;
        content-align: left middle;
    }
    """

    BINDINGS = [
        Binding("escape", "go_back", "返回", priority=True, show=True),
        Binding("j", "scroll_down", "向下", show=True),
        Binding("k", "scroll_up", "向上", show=True),
        Binding("down", "scroll_down", "向下", show=False),
        Binding("up", "scroll_up", "向上", show=False),
    ]

    _prompt_index: reactive[int] = reactive(0)
    _old_version_index: reactive[int] = reactive(0)
    _new_version_index: reactive[int] = reactive(0)

    def __init__(self, base_path: Path | None = None, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self._base_path = base_path
        self._prompts: list[dict[str, Any]] = []       # current-version metadata
        self._versions: list[str] = []                  # versions for selected prompt
        self._old_ver: str | None = None
        self._new_ver: str | None = None

    # ------------------------------------------------------------------
    # Compose & lifecycle
    # ------------------------------------------------------------------

    def compose(self) -> ComposeResult:
        yield Header()
        with Horizontal(id="diff-layout"):
            with Vertical(id="selector-panel"):
                yield Label("📝  Prompt", classes="section-title")
                yield ListView(id="prompt-list")
                yield Label("旧版本 (左)", classes="version-label")
                yield ListView(id="old-version-list")
                yield Label("新版本 (右)", classes="version-label")
                yield ListView(id="new-version-list")
            with Vertical(id="diff-area"):
                yield Label("", id="status-bar")
                with Horizontal(id="diff-panes"):
                    yield _DiffPane(id="left-pane")
                    yield _DiffPane(id="right-pane")
        yield Footer()

    def on_mount(self) -> None:
        self._load_prompts()
        self._rebuild_prompt_list()
        self.query_one("#prompt-list", ListView).focus()

    # ------------------------------------------------------------------
    # Data helpers
    # ------------------------------------------------------------------

    def _load_prompts(self) -> None:
        try:
            from harness_kit.prompt import list_prompts  # pylint: disable=import-outside-toplevel
            self._prompts = list_prompts(self._base_path)
        except Exception:  # pylint: disable=broad-except
            self._prompts = []

    def _load_versions(self, name: str) -> list[str]:
        try:
            from harness_kit.prompt import list_versions  # pylint: disable=import-outside-toplevel
            return list_versions(name, self._base_path)
        except Exception:  # pylint: disable=broad-except
            return []

    def _load_prompt_content(self, name: str, version: str) -> str:
        try:
            from harness_kit.prompt import load_prompt  # pylint: disable=import-outside-toplevel
            data = load_prompt(name, version, self._base_path)
            return data.get("content", "")
        except Exception:  # pylint: disable=broad-except
            return ""

    # ------------------------------------------------------------------
    # List rebuild helpers
    # ------------------------------------------------------------------

    def _rebuild_prompt_list(self) -> None:
        lv = self.query_one("#prompt-list", ListView)
        lv.clear()
        if not self._prompts:
            self._show_empty()
            return
        for p in self._prompts:
            name = p.get("name", "?")
            version = p.get("version", "?")
            lv.append(ListItem(Label(f"{name}  [dim]{version}[/dim]")))
        lv.index = 0
        self._prompt_index = 0
        self._select_prompt(0)

    def _select_prompt(self, index: int) -> None:
        if not (0 <= index < len(self._prompts)):
            return
        self._prompt_index = index
        name = self._prompts[index].get("name", "?")
        self._versions = self._load_versions(name)
        self._rebuild_version_lists()

    def _rebuild_version_lists(self) -> None:
        old_lv = self.query_one("#old-version-list", ListView)
        new_lv = self.query_one("#new-version-list", ListView)
        old_lv.clear()
        new_lv.clear()

        if not self._versions:
            self._update_diff_panes("", "", "—", "—")
            return

        for v in self._versions:
            old_lv.append(ListItem(Label(v)))
            new_lv.append(ListItem(Label(v)))

        # default: old = first version, new = last version
        old_idx = 0
        new_idx = len(self._versions) - 1
        self._old_version_index = old_idx
        self._new_version_index = new_idx
        old_lv.index = old_idx
        new_lv.index = new_idx

        self._old_ver = self._versions[old_idx]
        self._new_ver = self._versions[new_idx]
        self._refresh_diff()

    # ------------------------------------------------------------------
    # Diff rendering
    # ------------------------------------------------------------------

    def _refresh_diff(self) -> None:
        if not self._prompts or not self._versions:
            self._show_empty()
            return
        if self._old_ver is None or self._new_ver is None:
            return
        name = self._prompts[self._prompt_index].get("name", "?")
        old_content = self._load_prompt_content(name, self._old_ver)
        new_content = self._load_prompt_content(name, self._new_ver)
        old_label = f"{name}@{self._old_ver}"
        new_label = f"{name}@{self._new_ver}"
        self._update_diff_panes(old_content, new_content, old_label, new_label)

    def _update_diff_panes(
        self,
        old_content: str,
        new_content: str,
        old_label: str,
        new_label: str,
    ) -> None:
        left_markup, right_markup = build_diff_panes(old_content, new_content, old_label, new_label)
        left_pane = self.query_one("#left-pane", _DiffPane)
        right_pane = self.query_one("#right-pane", _DiffPane)
        left_pane.content_text = left_markup
        right_pane.content_text = right_markup
        left_pane.refresh()
        right_pane.refresh()

        # Update status bar
        status = self.query_one("#status-bar", Label)
        if old_label == "—":
            status.update("[dim]暂无 Prompt — 使用 harnesskit prompt save 创建[/dim]")
        else:
            status.update(
                f"[dim]对比：[/dim][cyan]{old_label}[/cyan]"
                f"[dim] ← → [/dim][cyan]{new_label}[/cyan]"
                f"[dim]   j/k 滚动  Esc 返回[/dim]"
            )

    def _show_empty(self) -> None:
        empty = (
            "[dim]暂无 Prompt。\n\n"
            "使用以下命令创建 Prompt：\n"
            "  [cyan]harnesskit prompt save my-prompt --content '...'[/cyan][/dim]"
        )
        left_pane = self.query_one("#left-pane", _DiffPane)
        right_pane = self.query_one("#right-pane", _DiffPane)
        left_pane.content_text = empty
        right_pane.content_text = ""
        left_pane.refresh()
        right_pane.refresh()
        status = self.query_one("#status-bar", Label)
        status.update("[dim]暂无 Prompt[/dim]")

    # ------------------------------------------------------------------
    # Events
    # ------------------------------------------------------------------

    def on_list_view_highlighted(self, event: ListView.Highlighted) -> None:
        if event.item is None:
            return
        lv = event.list_view
        try:
            idx = list(lv.children).index(event.item)
        except (ValueError, TypeError):
            return

        if lv.id == "prompt-list":
            self._prompt_index = idx
            self._select_prompt(idx)
        elif lv.id == "old-version-list":
            self._old_version_index = idx
            if 0 <= idx < len(self._versions):
                self._old_ver = self._versions[idx]
                self._refresh_diff()
        elif lv.id == "new-version-list":
            self._new_version_index = idx
            if 0 <= idx < len(self._versions):
                self._new_ver = self._versions[idx]
                self._refresh_diff()

    # ------------------------------------------------------------------
    # Actions
    # ------------------------------------------------------------------

    def action_go_back(self) -> None:
        self.app.pop_screen()

    def action_scroll_down(self) -> None:
        left_pane = self.query_one("#left-pane", _DiffPane)
        right_pane = self.query_one("#right-pane", _DiffPane)
        left_pane.scroll_down(animate=False)
        right_pane.scroll_down(animate=False)

    def action_scroll_up(self) -> None:
        left_pane = self.query_one("#left-pane", _DiffPane)
        right_pane = self.query_one("#right-pane", _DiffPane)
        left_pane.scroll_up(animate=False)
        right_pane.scroll_up(animate=False)
