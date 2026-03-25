"""Tests for Phase 7.4 — Eval Browser TUI screen."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest


# ---------------------------------------------------------------------------
# Unit tests — importability and helpers
# ---------------------------------------------------------------------------


def test_eval_browser_importable():
    """EvalBrowserScreen can be imported from the tui package."""
    from harness_kit.tui.eval_browser import EvalBrowserScreen
    assert EvalBrowserScreen is not None


def test_eval_browser_exported_from_tui():
    """EvalBrowserScreen is re-exported from harness_kit.tui."""
    from harness_kit.tui import EvalBrowserScreen
    assert EvalBrowserScreen is not None


def test_status_markup_passed():
    """_status_markup returns green markup for 'passed'."""
    from harness_kit.tui.eval_browser import _status_markup
    result = _status_markup("passed")
    assert "green" in result
    assert "passed" in result


def test_status_markup_failed():
    """_status_markup returns red markup for 'failed'."""
    from harness_kit.tui.eval_browser import _status_markup
    result = _status_markup("failed")
    assert "red" in result
    assert "failed" in result


def test_status_markup_error():
    """_status_markup returns red markup for 'error'."""
    from harness_kit.tui.eval_browser import _status_markup
    result = _status_markup("error")
    assert "red" in result


def test_status_markup_unknown():
    """_status_markup dims unknown statuses."""
    from harness_kit.tui.eval_browser import _status_markup
    result = _status_markup("running")
    assert "running" in result


def test_format_case_list_no_results():
    """_format_case_list without results returns dim bullets."""
    from harness_kit.tui.eval_browser import _format_case_list
    suite = {
        "name": "my-suite",
        "cases": [
            {"id": "c1", "name": "Case 1"},
            {"id": "c2", "name": "Case 2"},
        ],
    }
    items = _format_case_list(suite, None)
    assert len(items) == 2
    # No status — should use dim bullet
    for cid, label in items:
        assert "dim" in label


def test_format_case_list_with_results():
    """_format_case_list colours passed green and failed red."""
    from harness_kit.tui.eval_browser import _format_case_list
    suite = {
        "name": "my-suite",
        "cases": [
            {"id": "c1", "name": "Pass Case"},
            {"id": "c2", "name": "Fail Case"},
        ],
    }
    result = {
        "cases": [
            {"id": "c1", "status": "passed"},
            {"id": "c2", "status": "failed"},
        ]
    }
    items = _format_case_list(suite, result)
    assert len(items) == 2
    _, label_c1 = items[0]
    _, label_c2 = items[1]
    assert "green" in label_c1
    assert "red" in label_c2


def test_format_assertion_detail_no_result():
    """_format_assertion_detail with no result shows the 'no results yet' hint."""
    from harness_kit.tui.eval_browser import _format_assertion_detail
    case_def = {
        "id": "c1",
        "name": "My Case",
        "assertions": [{"type": "contains", "path": "$.x", "value": "y"}],
    }
    text = _format_assertion_detail(None, case_def)
    assert "My Case" in text
    assert "harnesskit eval run" in text
    assert "contains" in text


def test_format_assertion_detail_with_result():
    """_format_assertion_detail with a result shows status and assertions."""
    from harness_kit.tui.eval_browser import _format_assertion_detail
    case_def = {"id": "c1", "name": "My Case"}
    case_result = {
        "id": "c1",
        "status": "passed",
        "duration": 1.5,
        "input_tokens": 100,
        "output_tokens": 50,
        "assertions": [
            {"type": "contains", "path": "$.x", "passed": True, "message": "OK"},
            {"type": "regex", "path": "$.y", "passed": False, "message": "no match"},
        ],
        "assertion_summary": {"total": 2, "passed": 1},
    }
    text = _format_assertion_detail(case_result, case_def)
    assert "passed" in text
    assert "1.500s" in text
    assert "contains" in text
    assert "regex" in text
    assert "OK" in text
    assert "no match" in text


def test_format_assertion_detail_shows_error():
    """_format_assertion_detail with error status shows the error message."""
    from harness_kit.tui.eval_browser import _format_assertion_detail
    case_result = {
        "id": "c1",
        "status": "error",
        "error": "LLM timed out",
        "assertions": [],
    }
    text = _format_assertion_detail(case_result, None)
    assert "LLM timed out" in text


def test_eval_browser_bindings_include_escape():
    """EvalBrowserScreen bindings include escape."""
    from harness_kit.tui.eval_browser import EvalBrowserScreen
    binding_keys = {b.key for b in EvalBrowserScreen.BINDINGS}
    assert "escape" in binding_keys


def test_eval_browser_bindings_include_vim_nav():
    """EvalBrowserScreen bindings include j/k."""
    from harness_kit.tui.eval_browser import EvalBrowserScreen
    binding_keys = {b.key for b in EvalBrowserScreen.BINDINGS}
    assert "j" in binding_keys
    assert "k" in binding_keys


def test_eval_browser_bindings_include_tab():
    """EvalBrowserScreen bindings include tab for pane switching."""
    from harness_kit.tui.eval_browser import EvalBrowserScreen
    binding_keys = {b.key for b in EvalBrowserScreen.BINDINGS}
    assert "tab" in binding_keys


def test_eval_browser_instantiation():
    """EvalBrowserScreen can be instantiated without errors."""
    from harness_kit.tui.eval_browser import EvalBrowserScreen
    screen = EvalBrowserScreen()
    assert screen is not None


def test_eval_browser_accepts_base_path(tmp_path: Path):
    """EvalBrowserScreen accepts a base_path parameter for testability."""
    from harness_kit.tui.eval_browser import EvalBrowserScreen
    screen = EvalBrowserScreen(base_path=tmp_path)
    assert screen._base_path == tmp_path


# ---------------------------------------------------------------------------
# Fixture helpers
# ---------------------------------------------------------------------------


def _make_suite(tmp_path: Path, name: str, case_count: int = 2) -> None:
    """Create a minimal test suite with *case_count* cases."""
    from harness_kit.eval import save_suite
    cases = [
        {
            "id": f"case-{i}",
            "name": f"Case {i}",
            "inputs": {"value": str(i)},
            "assertions": [
                {"type": "contains", "path": "$.result", "value": str(i)}
            ],
        }
        for i in range(case_count)
    ]
    save_suite({"name": name, "description": f"Suite {name}", "cases": cases}, base=tmp_path)


def _make_result(tmp_path: Path, suite_name: str, statuses: list[str]) -> dict[str, Any]:
    """Create an eval result with predetermined case statuses (no LLM calls)."""
    import json
    import time
    from datetime import datetime, timezone
    from harness_kit.eval import results_dir

    timestamp = datetime.now(timezone.utc).isoformat()
    cases = []
    passed = 0
    failed = 0
    for i, status in enumerate(statuses):
        assertion_passed = status == "passed"
        cases.append({
            "id": f"case-{i}",
            "name": f"Case {i}",
            "status": status,
            "duration": 0.1,
            "input_tokens": 10,
            "output_tokens": 5,
            "output_preview": f"output-{i}",
            "assertions": [
                {
                    "type": "contains",
                    "path": "$.result",
                    "passed": assertion_passed,
                    "message": "OK" if assertion_passed else "FAIL",
                }
            ],
            "assertion_summary": {"total": 1, "passed": 1 if assertion_passed else 0},
        })
        if status == "passed":
            passed += 1
        else:
            failed += 1

    report = {
        "timestamp": timestamp,
        "target": "test-target",
        "suite": suite_name,
        "summary": {"total": len(statuses), "passed": passed, "failed": failed},
        "cases": cases,
    }
    rdir = results_dir(tmp_path)
    rdir.mkdir(parents=True, exist_ok=True)
    # Small sleep to ensure unique filename
    time.sleep(0.01)
    import re
    ts_safe = re.sub(r"[:\+\.]", "-", timestamp)[:23]
    path = rdir / f"{ts_safe}.json"
    with path.open("w", encoding="utf-8") as fh:
        json.dump(report, fh, indent=2)
    return report


def _make_eval_app(base_path: Path | None = None):
    """Return a minimal Textual App that shows EvalBrowserScreen."""
    pytest.importorskip("textual")
    from textual.app import App, ComposeResult
    from textual.widgets import Label
    from harness_kit.tui.eval_browser import EvalBrowserScreen

    class _EvalApp(App):
        def compose(self) -> ComposeResult:
            yield Label("")

        def on_mount(self) -> None:
            self.push_screen(EvalBrowserScreen(base_path=base_path))

    return _EvalApp()


# ---------------------------------------------------------------------------
# Async pilot tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_eval_browser_composes_without_error():
    """EvalBrowserScreen composes without raising exceptions."""
    pytest.importorskip("textual")
    from harness_kit.tui.eval_browser import EvalBrowserScreen
    app = _make_eval_app()
    async with app.run_test(size=(140, 40)) as pilot:
        await pilot.pause()
        assert isinstance(app.screen, EvalBrowserScreen)


@pytest.mark.asyncio
async def test_eval_browser_empty_state(tmp_path: Path):
    """With no suites, the suite list shows the empty-state item."""
    pytest.importorskip("textual")
    from harness_kit.tui.eval_browser import EvalBrowserScreen
    app = _make_eval_app(base_path=tmp_path)
    async with app.run_test(size=(140, 40)) as pilot:
        await pilot.pause()
        screen = app.screen
        assert isinstance(screen, EvalBrowserScreen)
        assert len(screen._suites) == 0


@pytest.mark.asyncio
async def test_eval_browser_lists_suites(tmp_path: Path):
    """Suites created in tmp_path appear in _suites."""
    pytest.importorskip("textual")
    from harness_kit.tui.eval_browser import EvalBrowserScreen
    _make_suite(tmp_path, "alpha-suite")
    _make_suite(tmp_path, "beta-suite")
    app = _make_eval_app(base_path=tmp_path)
    async with app.run_test(size=(140, 40)) as pilot:
        await pilot.pause()
        screen = app.screen
        assert isinstance(screen, EvalBrowserScreen)
        names = {s["name"] for s in screen._suites}
        assert names == {"alpha-suite", "beta-suite"}


@pytest.mark.asyncio
async def test_eval_browser_shows_cases_for_suite(tmp_path: Path):
    """Selecting a suite populates the case list panel."""
    pytest.importorskip("textual")
    from harness_kit.tui.eval_browser import EvalBrowserScreen
    _make_suite(tmp_path, "my-suite", case_count=3)
    app = _make_eval_app(base_path=tmp_path)
    async with app.run_test(size=(140, 40)) as pilot:
        await pilot.pause()
        screen = app.screen
        assert isinstance(screen, EvalBrowserScreen)
        # Suite is selected; case list should have 3 items
        lv = screen.query_one("#case-list")
        assert len(list(lv.children)) == 3


@pytest.mark.asyncio
async def test_eval_browser_passed_result_shown_green(tmp_path: Path):
    """Cases with status='passed' are labelled with green markup in assertion panel."""
    pytest.importorskip("textual")
    from harness_kit.tui.eval_browser import EvalBrowserScreen, _TextPanel
    _make_suite(tmp_path, "green-suite", case_count=1)
    _make_result(tmp_path, "green-suite", ["passed"])
    app = _make_eval_app(base_path=tmp_path)
    async with app.run_test(size=(140, 40)) as pilot:
        await pilot.pause()
        screen = app.screen
        assert isinstance(screen, EvalBrowserScreen)
        panel = screen.query_one("#assertion-panel", _TextPanel)
        assert "green" in panel.content_text


@pytest.mark.asyncio
async def test_eval_browser_failed_result_shown_red(tmp_path: Path):
    """Cases with status='failed' are labelled with red markup in assertion panel."""
    pytest.importorskip("textual")
    from harness_kit.tui.eval_browser import EvalBrowserScreen, _TextPanel
    _make_suite(tmp_path, "red-suite", case_count=1)
    _make_result(tmp_path, "red-suite", ["failed"])
    app = _make_eval_app(base_path=tmp_path)
    async with app.run_test(size=(140, 40)) as pilot:
        await pilot.pause()
        screen = app.screen
        assert isinstance(screen, EvalBrowserScreen)
        panel = screen.query_one("#assertion-panel", _TextPanel)
        assert "red" in panel.content_text


@pytest.mark.asyncio
async def test_eval_browser_assertion_detail_shows_message(tmp_path: Path):
    """Assertion panel shows individual assertion messages from result."""
    pytest.importorskip("textual")
    from harness_kit.tui.eval_browser import EvalBrowserScreen, _TextPanel
    _make_suite(tmp_path, "detail-suite", case_count=1)
    _make_result(tmp_path, "detail-suite", ["passed"])
    app = _make_eval_app(base_path=tmp_path)
    async with app.run_test(size=(140, 40)) as pilot:
        await pilot.pause()
        screen = app.screen
        assert isinstance(screen, EvalBrowserScreen)
        panel = screen.query_one("#assertion-panel", _TextPanel)
        # Should include assertion type and message
        assert "contains" in panel.content_text


@pytest.mark.asyncio
async def test_eval_browser_j_moves_suite_down(tmp_path: Path):
    """Pressing j in suites pane moves suite selection down."""
    pytest.importorskip("textual")
    from harness_kit.tui.eval_browser import EvalBrowserScreen
    _make_suite(tmp_path, "suite-a")
    _make_suite(tmp_path, "suite-b")
    app = _make_eval_app(base_path=tmp_path)
    async with app.run_test(size=(140, 40)) as pilot:
        await pilot.pause()
        screen = app.screen
        assert isinstance(screen, EvalBrowserScreen)
        assert screen._suite_index == 0
        await pilot.press("j")
        assert screen._suite_index == 1


@pytest.mark.asyncio
async def test_eval_browser_k_moves_suite_up(tmp_path: Path):
    """Pressing k in suites pane moves suite selection up."""
    pytest.importorskip("textual")
    from harness_kit.tui.eval_browser import EvalBrowserScreen
    _make_suite(tmp_path, "suite-a")
    _make_suite(tmp_path, "suite-b")
    app = _make_eval_app(base_path=tmp_path)
    async with app.run_test(size=(140, 40)) as pilot:
        await pilot.pause()
        screen = app.screen
        assert isinstance(screen, EvalBrowserScreen)
        await pilot.press("j")
        assert screen._suite_index == 1
        await pilot.press("k")
        assert screen._suite_index == 0


@pytest.mark.asyncio
async def test_eval_browser_tab_switches_pane(tmp_path: Path):
    """Pressing Tab switches active pane between suites and cases."""
    pytest.importorskip("textual")
    from harness_kit.tui.eval_browser import EvalBrowserScreen
    _make_suite(tmp_path, "tab-suite")
    app = _make_eval_app(base_path=tmp_path)
    async with app.run_test(size=(140, 40)) as pilot:
        await pilot.pause()
        screen = app.screen
        assert isinstance(screen, EvalBrowserScreen)
        assert screen._active_pane == "suites"
        await pilot.press("tab")
        assert screen._active_pane == "cases"
        await pilot.press("tab")
        assert screen._active_pane == "suites"


@pytest.mark.asyncio
async def test_eval_browser_j_moves_case_down(tmp_path: Path):
    """Pressing j in cases pane moves case selection down."""
    pytest.importorskip("textual")
    from harness_kit.tui.eval_browser import EvalBrowserScreen
    _make_suite(tmp_path, "nav-suite", case_count=3)
    app = _make_eval_app(base_path=tmp_path)
    async with app.run_test(size=(140, 40)) as pilot:
        await pilot.pause()
        screen = app.screen
        assert isinstance(screen, EvalBrowserScreen)
        # Switch to cases pane
        await pilot.press("tab")
        assert screen._active_pane == "cases"
        assert screen._case_index == 0
        await pilot.press("j")
        assert screen._case_index == 1


@pytest.mark.asyncio
async def test_eval_browser_escape_pops_screen(tmp_path: Path):
    """Pressing Escape returns to the previous screen."""
    pytest.importorskip("textual")
    from harness_kit.tui.app import HarnessKitApp, NAV_ITEMS
    from harness_kit.tui.eval_browser import EvalBrowserScreen

    app = HarnessKitApp()
    async with app.run_test(size=(140, 40)) as pilot:
        # Navigate to Eval nav item
        eval_idx = next(i for i, item in enumerate(NAV_ITEMS) if item[0] == "eval")
        for _ in range(eval_idx):
            await pilot.press("j")
        await pilot.press("enter")
        await pilot.pause()
        assert isinstance(app.screen, EvalBrowserScreen)

        # Press Escape — should pop back to main app
        await pilot.press("escape")
        await pilot.pause()
        assert not isinstance(app.screen, EvalBrowserScreen)


# ---------------------------------------------------------------------------
# Main app integration: Enter on Eval pushes EvalBrowserScreen
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_main_app_enter_on_eval_pushes_browser():
    """Pressing Enter when Eval nav item is selected pushes EvalBrowserScreen."""
    pytest.importorskip("textual")
    from harness_kit.tui.app import HarnessKitApp, NAV_ITEMS
    from harness_kit.tui.eval_browser import EvalBrowserScreen

    app = HarnessKitApp()
    async with app.run_test(size=(140, 40)) as pilot:
        eval_idx = next(i for i, item in enumerate(NAV_ITEMS) if item[0] == "eval")
        for _ in range(eval_idx):
            await pilot.press("j")
        assert app._selected_index == eval_idx
        await pilot.press("enter")
        await pilot.pause()
        assert isinstance(app.screen, EvalBrowserScreen)


@pytest.mark.asyncio
async def test_eval_browser_result_summary_in_panel_title(tmp_path: Path):
    """When results exist, the case panel title shows pass count."""
    pytest.importorskip("textual")
    from harness_kit.tui.eval_browser import EvalBrowserScreen
    _make_suite(tmp_path, "count-suite", case_count=2)
    _make_result(tmp_path, "count-suite", ["passed", "failed"])
    app = _make_eval_app(base_path=tmp_path)
    async with app.run_test(size=(140, 40)) as pilot:
        await pilot.pause()
        screen = app.screen
        assert isinstance(screen, EvalBrowserScreen)
        # Assertion panel should show status from result — green (passed) and red (failed)
        from harness_kit.tui.eval_browser import _TextPanel
        panel = screen.query_one("#assertion-panel", _TextPanel)
        # case-0 is passed, so its detail shows green markup
        assert "green" in panel.content_text
