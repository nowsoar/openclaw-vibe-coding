"""Tests for Phase 7.5 — Logs Browser TUI screen (实时日志流)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest


# ---------------------------------------------------------------------------
# Unit tests — pure helper functions
# ---------------------------------------------------------------------------


def test_logs_browser_importable():
    """LogsBrowserScreen can be imported from the tui package."""
    from harness_kit.tui.logs_browser import LogsBrowserScreen
    assert LogsBrowserScreen is not None


def test_logs_browser_exported_from_tui():
    """LogsBrowserScreen is re-exported from harness_kit.tui."""
    from harness_kit.tui import LogsBrowserScreen
    assert LogsBrowserScreen is not None


def test_escape_markup_brackets():
    """_escape_markup escapes Rich [ and ] characters."""
    from harness_kit.tui.logs_browser import _escape_markup
    result = _escape_markup("foo [bar] baz")
    assert "[" not in result or result.count("[") == 0 or "\\[" in result


def test_format_timestamp_iso():
    """_format_timestamp shortens an ISO timestamp correctly."""
    from harness_kit.tui.logs_browser import _format_timestamp
    result = _format_timestamp("2026-03-25T10:30:45.123456+00:00")
    assert result == "2026-03-25 10:30:45"


def test_format_timestamp_invalid():
    """_format_timestamp returns the raw string when parsing fails."""
    from harness_kit.tui.logs_browser import _format_timestamp
    result = _format_timestamp("not-a-date")
    assert "not-a-date" in result


def test_format_status_success():
    """_format_status returns green markup for 'success'."""
    from harness_kit.tui.logs_browser import _format_status
    result = _format_status("success")
    assert "green" in result
    assert "✓" in result


def test_format_status_error():
    """_format_status returns red markup for 'error'."""
    from harness_kit.tui.logs_browser import _format_status
    result = _format_status("error")
    assert "red" in result
    assert "✗" in result


def test_format_status_unknown():
    """_format_status returns yellow markup for unknown statuses."""
    from harness_kit.tui.logs_browser import _format_status
    result = _format_status("timeout")
    assert "yellow" in result
    assert "timeout" in result


def test_format_record_basic():
    """_format_record returns a string containing key fields."""
    from harness_kit.tui.logs_browser import _format_record
    rec = {
        "timestamp": "2026-03-25T10:00:00+00:00",
        "skill": "code-reviewer",
        "model": "gpt-4o",
        "status": "success",
        "duration": 2.5,
        "total_tokens": 300,
        "cost": 0.015,
    }
    line = _format_record(rec)
    assert "code-reviewer" in line
    assert "gpt-4o" in line
    assert "2.50" in line
    assert "300" in line
    assert "0.0150" in line


def test_format_record_no_cost():
    """_format_record handles missing cost gracefully."""
    from harness_kit.tui.logs_browser import _format_record
    rec = {
        "timestamp": "2026-03-25T10:00:00+00:00",
        "skill": "my-skill",
        "model": "claude-3",
        "status": "success",
        "duration": 1.0,
        "total_tokens": 100,
    }
    line = _format_record(rec)
    assert "my-skill" in line


def test_format_record_search_highlights_matching():
    """_format_record highlights rows matching the search term."""
    from harness_kit.tui.logs_browser import _format_record
    rec = {
        "timestamp": "2026-03-25T10:00:00+00:00",
        "skill": "translate-skill",
        "model": "gpt-4o",
        "status": "success",
        "duration": 1.0,
        "total_tokens": 50,
        "cost": 0.001,
    }
    line_match = _format_record(rec, search="translate")
    line_no_match = _format_record(rec, search="xyz-not-found")
    assert "dark_blue" in line_match
    assert "dark_blue" not in line_no_match


def test_format_record_search_case_insensitive():
    """Search highlight is case-insensitive."""
    from harness_kit.tui.logs_browser import _format_record
    rec = {
        "timestamp": "2026-03-25T10:00:00+00:00",
        "skill": "CodeReviewSkill",
        "model": "gpt-4o",
        "status": "success",
        "duration": 1.0,
        "total_tokens": 50,
    }
    line = _format_record(rec, search="codereview")
    assert "dark_blue" in line


def test_format_log_panel_empty():
    """_format_log_panel with no records returns the empty-state message."""
    from harness_kit.tui.logs_browser import _format_log_panel
    text = _format_log_panel([])
    assert "暂无日志记录" in text
    assert "harnesskit skill run" in text


def test_format_log_panel_with_records():
    """_format_log_panel with records includes a header and record lines."""
    from harness_kit.tui.logs_browser import _format_log_panel
    records = [
        {
            "timestamp": "2026-03-25T10:00:00+00:00",
            "skill": "alpha",
            "model": "gpt-4o",
            "status": "success",
            "duration": 1.0,
            "total_tokens": 100,
            "cost": 0.01,
        },
        {
            "timestamp": "2026-03-25T10:01:00+00:00",
            "skill": "beta",
            "model": "claude-3",
            "status": "error",
            "duration": 0.5,
            "total_tokens": 50,
            "cost": 0.005,
        },
    ]
    text = _format_log_panel(records)
    assert "alpha" in text
    assert "beta" in text
    assert "Skill" in text  # header row


def test_format_log_panel_paused_indicator():
    """_format_log_panel with paused=True appends the pause indicator."""
    from harness_kit.tui.logs_browser import _format_log_panel
    records = [
        {
            "timestamp": "2026-03-25T10:00:00+00:00",
            "skill": "test-skill",
            "model": "gpt-4o",
            "status": "success",
            "duration": 1.0,
            "total_tokens": 10,
        }
    ]
    text_paused = _format_log_panel(records, paused=True)
    text_live = _format_log_panel(records, paused=False)
    assert "⏸" in text_paused
    assert "⏸" not in text_live


def test_format_log_panel_search_highlight():
    """_format_log_panel passes search term to _format_record."""
    from harness_kit.tui.logs_browser import _format_log_panel
    records = [
        {
            "timestamp": "2026-03-25T10:00:00+00:00",
            "skill": "highlighted-skill",
            "model": "gpt-4o",
            "status": "success",
            "duration": 1.0,
            "total_tokens": 10,
        }
    ]
    text = _format_log_panel(records, search="highlighted")
    assert "dark_blue" in text


def test_logs_browser_bindings_include_escape():
    """LogsBrowserScreen bindings include escape."""
    from harness_kit.tui.logs_browser import LogsBrowserScreen
    binding_keys = {b.key for b in LogsBrowserScreen.BINDINGS}
    assert "escape" in binding_keys


def test_logs_browser_bindings_include_space():
    """LogsBrowserScreen bindings include space for pause/resume."""
    from harness_kit.tui.logs_browser import LogsBrowserScreen
    binding_keys = {b.key for b in LogsBrowserScreen.BINDINGS}
    assert "space" in binding_keys


def test_logs_browser_bindings_include_vim_nav():
    """LogsBrowserScreen bindings include j/k."""
    from harness_kit.tui.logs_browser import LogsBrowserScreen
    binding_keys = {b.key for b in LogsBrowserScreen.BINDINGS}
    assert "j" in binding_keys
    assert "k" in binding_keys


def test_logs_browser_bindings_include_refresh():
    """LogsBrowserScreen bindings include r for manual refresh."""
    from harness_kit.tui.logs_browser import LogsBrowserScreen
    binding_keys = {b.key for b in LogsBrowserScreen.BINDINGS}
    assert "r" in binding_keys


def test_logs_browser_instantiation():
    """LogsBrowserScreen can be instantiated without errors."""
    from harness_kit.tui.logs_browser import LogsBrowserScreen
    screen = LogsBrowserScreen()
    assert screen is not None


def test_logs_browser_accepts_base_path(tmp_path: Path):
    """LogsBrowserScreen accepts a base_path parameter for testability."""
    from harness_kit.tui.logs_browser import LogsBrowserScreen
    screen = LogsBrowserScreen(base_path=tmp_path)
    assert screen._base_path == tmp_path


def test_logs_browser_initial_not_paused():
    """LogsBrowserScreen starts in live (not paused) mode."""
    from harness_kit.tui.logs_browser import LogsBrowserScreen
    screen = LogsBrowserScreen()
    assert screen._paused is False


# ---------------------------------------------------------------------------
# Fixture helpers
# ---------------------------------------------------------------------------


def _write_log_record(tmp_path: Path, **fields: Any) -> None:
    """Append a minimal log record to the calls.jsonl file."""
    log_file = tmp_path / ".harness" / "logs" / "calls.jsonl"
    log_file.parent.mkdir(parents=True, exist_ok=True)
    base_record = {
        "timestamp": "2026-03-25T10:00:00+00:00",
        "type": "llm_call",
        "skill": "test-skill",
        "model": "gpt-4o",
        "input_tokens": 100,
        "output_tokens": 50,
        "total_tokens": 150,
        "cost": 0.01,
        "duration": 1.5,
        "status": "success",
    }
    base_record.update(fields)
    with log_file.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(base_record) + "\n")


def _make_logs_app(base_path: Path | None = None):
    """Return a minimal Textual App that shows LogsBrowserScreen."""
    pytest.importorskip("textual")
    from textual.app import App, ComposeResult
    from textual.widgets import Label
    from harness_kit.tui.logs_browser import LogsBrowserScreen

    class _LogsApp(App):
        def compose(self) -> ComposeResult:
            yield Label("")

        def on_mount(self) -> None:
            self.push_screen(LogsBrowserScreen(base_path=base_path))

    return _LogsApp()


# ---------------------------------------------------------------------------
# Async pilot tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_logs_browser_composes_without_error():
    """LogsBrowserScreen composes without raising exceptions."""
    pytest.importorskip("textual")
    from harness_kit.tui.logs_browser import LogsBrowserScreen
    app = _make_logs_app()
    async with app.run_test(size=(140, 40)) as pilot:
        await pilot.pause()
        assert isinstance(app.screen, LogsBrowserScreen)


@pytest.mark.asyncio
async def test_logs_browser_empty_state(tmp_path: Path):
    """With no log file, the panel shows the empty-state message."""
    pytest.importorskip("textual")
    from harness_kit.tui.logs_browser import LogsBrowserScreen, _TextPanel
    app = _make_logs_app(base_path=tmp_path)
    async with app.run_test(size=(140, 40)) as pilot:
        await pilot.pause()
        screen = app.screen
        assert isinstance(screen, LogsBrowserScreen)
        panel = screen.query_one("#log-panel", _TextPanel)
        assert "暂无日志记录" in panel.content_text


@pytest.mark.asyncio
async def test_logs_browser_shows_records(tmp_path: Path):
    """Log records written to tmp_path appear in the panel."""
    pytest.importorskip("textual")
    from harness_kit.tui.logs_browser import LogsBrowserScreen, _TextPanel
    _write_log_record(tmp_path, skill="my-special-skill", model="gpt-4o")
    app = _make_logs_app(base_path=tmp_path)
    async with app.run_test(size=(140, 40)) as pilot:
        await pilot.pause()
        screen = app.screen
        assert isinstance(screen, LogsBrowserScreen)
        panel = screen.query_one("#log-panel", _TextPanel)
        assert "my-special-skill" in panel.content_text


@pytest.mark.asyncio
async def test_logs_browser_record_count(tmp_path: Path):
    """_records list is populated with the correct number of entries."""
    pytest.importorskip("textual")
    from harness_kit.tui.logs_browser import LogsBrowserScreen
    for i in range(5):
        _write_log_record(tmp_path, skill=f"skill-{i}")
    app = _make_logs_app(base_path=tmp_path)
    async with app.run_test(size=(140, 40)) as pilot:
        await pilot.pause()
        screen = app.screen
        assert isinstance(screen, LogsBrowserScreen)
        assert len(screen._records) == 5


@pytest.mark.asyncio
async def test_logs_browser_pause_toggle(tmp_path: Path):
    """Calling action_toggle_pause toggles the paused state."""
    pytest.importorskip("textual")
    from harness_kit.tui.logs_browser import LogsBrowserScreen
    app = _make_logs_app(base_path=tmp_path)
    async with app.run_test(size=(140, 40)) as pilot:
        await pilot.pause()
        screen = app.screen
        assert isinstance(screen, LogsBrowserScreen)
        assert screen._paused is False
        # Call action directly (Space may be consumed by focused Input widgets)
        screen.action_toggle_pause()
        await pilot.pause()
        assert screen._paused is True
        screen.action_toggle_pause()
        await pilot.pause()
        assert screen._paused is False


@pytest.mark.asyncio
async def test_logs_browser_paused_shows_indicator(tmp_path: Path):
    """When paused, the log panel includes the pause indicator text."""
    pytest.importorskip("textual")
    from harness_kit.tui.logs_browser import LogsBrowserScreen, _TextPanel
    _write_log_record(tmp_path)
    app = _make_logs_app(base_path=tmp_path)
    async with app.run_test(size=(140, 40)) as pilot:
        await pilot.pause()
        screen = app.screen
        assert isinstance(screen, LogsBrowserScreen)
        # Toggle pause via action (Space may be consumed by focused Input widgets)
        screen.action_toggle_pause()
        await pilot.pause()
        panel = screen.query_one("#log-panel", _TextPanel)
        assert "⏸" in panel.content_text


@pytest.mark.asyncio
async def test_logs_browser_r_refreshes(tmp_path: Path):
    """Pressing r triggers a refresh."""
    pytest.importorskip("textual")
    from harness_kit.tui.logs_browser import LogsBrowserScreen, _TextPanel
    app = _make_logs_app(base_path=tmp_path)
    async with app.run_test(size=(140, 40)) as pilot:
        await pilot.pause()
        screen = app.screen
        assert isinstance(screen, LogsBrowserScreen)
        # Write a record after startup
        _write_log_record(tmp_path, skill="late-arrival-skill")
        await pilot.press("r")
        await pilot.pause()
        panel = screen.query_one("#log-panel", _TextPanel)
        assert "late-arrival-skill" in panel.content_text


@pytest.mark.asyncio
async def test_logs_browser_escape_pops_screen():
    """Pressing Escape returns to the previous screen."""
    pytest.importorskip("textual")
    from harness_kit.tui.app import HarnessKitApp, NAV_ITEMS
    from harness_kit.tui.logs_browser import LogsBrowserScreen

    app = HarnessKitApp()
    async with app.run_test(size=(140, 40)) as pilot:
        logs_idx = next(i for i, item in enumerate(NAV_ITEMS) if item[0] == "logs")
        for _ in range(logs_idx):
            await pilot.press("j")
        await pilot.press("enter")
        await pilot.pause()
        assert isinstance(app.screen, LogsBrowserScreen)

        await pilot.press("escape")
        await pilot.pause()
        assert not isinstance(app.screen, LogsBrowserScreen)


@pytest.mark.asyncio
async def test_main_app_enter_on_logs_pushes_browser():
    """Pressing Enter when Logs nav item is selected pushes LogsBrowserScreen."""
    pytest.importorskip("textual")
    from harness_kit.tui.app import HarnessKitApp, NAV_ITEMS
    from harness_kit.tui.logs_browser import LogsBrowserScreen

    app = HarnessKitApp()
    async with app.run_test(size=(140, 40)) as pilot:
        logs_idx = next(i for i, item in enumerate(NAV_ITEMS) if item[0] == "logs")
        for _ in range(logs_idx):
            await pilot.press("j")
        assert app._selected_index == logs_idx
        await pilot.press("enter")
        await pilot.pause()
        assert isinstance(app.screen, LogsBrowserScreen)


@pytest.mark.asyncio
async def test_logs_browser_success_shown_green(tmp_path: Path):
    """Successful call records include green markup in the panel."""
    pytest.importorskip("textual")
    from harness_kit.tui.logs_browser import LogsBrowserScreen, _TextPanel
    _write_log_record(tmp_path, status="success")
    app = _make_logs_app(base_path=tmp_path)
    async with app.run_test(size=(140, 40)) as pilot:
        await pilot.pause()
        screen = app.screen
        assert isinstance(screen, LogsBrowserScreen)
        panel = screen.query_one("#log-panel", _TextPanel)
        assert "green" in panel.content_text


@pytest.mark.asyncio
async def test_logs_browser_error_shown_red(tmp_path: Path):
    """Error call records include red markup in the panel."""
    pytest.importorskip("textual")
    from harness_kit.tui.logs_browser import LogsBrowserScreen, _TextPanel
    _write_log_record(tmp_path, status="error", skill="failing-skill")
    app = _make_logs_app(base_path=tmp_path)
    async with app.run_test(size=(140, 40)) as pilot:
        await pilot.pause()
        screen = app.screen
        assert isinstance(screen, LogsBrowserScreen)
        panel = screen.query_one("#log-panel", _TextPanel)
        assert "red" in panel.content_text


@pytest.mark.asyncio
async def test_logs_browser_multiple_records_all_shown(tmp_path: Path):
    """Multiple records are all displayed in the log panel."""
    pytest.importorskip("textual")
    from harness_kit.tui.logs_browser import LogsBrowserScreen, _TextPanel
    _write_log_record(tmp_path, skill="skill-alpha")
    _write_log_record(tmp_path, skill="skill-beta")
    _write_log_record(tmp_path, skill="skill-gamma")
    app = _make_logs_app(base_path=tmp_path)
    async with app.run_test(size=(140, 40)) as pilot:
        await pilot.pause()
        screen = app.screen
        assert isinstance(screen, LogsBrowserScreen)
        panel = screen.query_one("#log-panel", _TextPanel)
        assert "skill-alpha" in panel.content_text
        assert "skill-beta" in panel.content_text
        assert "skill-gamma" in panel.content_text
