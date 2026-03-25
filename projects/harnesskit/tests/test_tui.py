"""Tests for Phase 7.1 — TUI framework."""

from __future__ import annotations

import pytest


# ---------------------------------------------------------------------------
# Unit tests: TUI module structure
# ---------------------------------------------------------------------------


def test_tui_package_import():
    """HarnessKitApp can be imported from the tui package."""
    from harness_kit.tui import HarnessKitApp
    assert HarnessKitApp is not None


def test_run_tui_callable():
    """run_tui function exists and is callable."""
    from harness_kit.tui.app import run_tui
    assert callable(run_tui)


def test_nav_items_structure():
    """NAV_ITEMS contains tuples with (id, label, description)."""
    from harness_kit.tui.app import NAV_ITEMS
    assert len(NAV_ITEMS) >= 6  # at least 6 navigation sections
    for item in NAV_ITEMS:
        assert len(item) == 3, "Each nav item must be (id, label, description)"
        item_id, label, description = item
        assert isinstance(item_id, str) and item_id
        assert isinstance(label, str) and label
        assert isinstance(description, str) and description


def test_nav_items_required_sections():
    """NAV_ITEMS includes Skills, Harnesses, Eval, and Logs sections."""
    from harness_kit.tui.app import NAV_ITEMS
    ids = {item[0] for item in NAV_ITEMS}
    assert "skills" in ids
    assert "harnesses" in ids
    assert "eval" in ids
    assert "logs" in ids


def test_app_title():
    """HarnessKitApp has correct TITLE."""
    from harness_kit.tui.app import HarnessKitApp
    assert HarnessKitApp.TITLE == "HarnessKit"


def test_app_subtitle():
    """HarnessKitApp has a non-empty SUB_TITLE."""
    from harness_kit.tui.app import HarnessKitApp
    assert HarnessKitApp.SUB_TITLE


def test_app_bindings_include_quit():
    """HarnessKit TUI bindings include quit action bound to 'q'."""
    from harness_kit.tui.app import HarnessKitApp
    binding_keys = {b.key for b in HarnessKitApp.BINDINGS}
    assert "q" in binding_keys


def test_app_bindings_include_vim_nav():
    """HarnessKit TUI bindings include j/k vim-style navigation."""
    from harness_kit.tui.app import HarnessKitApp
    binding_keys = {b.key for b in HarnessKitApp.BINDINGS}
    assert "j" in binding_keys
    assert "k" in binding_keys


def test_app_bindings_include_help():
    """HarnessKit TUI bindings include '?' for help."""
    from harness_kit.tui.app import HarnessKitApp
    binding_keys = {b.key for b in HarnessKitApp.BINDINGS}
    assert "question_mark" in binding_keys


def test_app_bindings_include_arrow_keys():
    """HarnessKit TUI bindings include arrow keys for navigation."""
    from harness_kit.tui.app import HarnessKitApp
    binding_keys = {b.key for b in HarnessKitApp.BINDINGS}
    assert "up" in binding_keys
    assert "down" in binding_keys


def test_app_instantiation():
    """HarnessKitApp can be instantiated without errors."""
    from harness_kit.tui.app import HarnessKitApp
    app = HarnessKitApp()
    assert app is not None


# ---------------------------------------------------------------------------
# Textual pilot tests (async, test UI behaviour without a real terminal)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_tui_composes_without_error():
    """TUI app composes layout without raising exceptions."""
    pytest.importorskip("textual")
    from harness_kit.tui.app import HarnessKitApp

    app = HarnessKitApp()
    async with app.run_test(size=(120, 40)) as pilot:
        # App should be running
        assert app.is_running


@pytest.mark.asyncio
async def test_tui_initial_state():
    """TUI shows first nav item content on startup."""
    pytest.importorskip("textual")
    from harness_kit.tui.app import HarnessKitApp, NAV_ITEMS

    app = HarnessKitApp()
    async with app.run_test(size=(120, 40)) as pilot:
        # Initial selected index should be 0
        assert app._selected_index == 0
        # Content panel should have the first item's description
        from harness_kit.tui.app import ContentPanel
        panel = app.query_one(ContentPanel)
        first_description = NAV_ITEMS[0][2]
        assert panel.content_text == first_description


@pytest.mark.asyncio
async def test_tui_j_key_moves_down():
    """Pressing 'j' moves the selection down."""
    pytest.importorskip("textual")
    from harness_kit.tui.app import HarnessKitApp

    app = HarnessKitApp()
    async with app.run_test(size=(120, 40)) as pilot:
        initial_index = app._selected_index
        await pilot.press("j")
        assert app._selected_index == initial_index + 1


@pytest.mark.asyncio
async def test_tui_k_key_moves_up():
    """Pressing 'k' when not at top moves selection up."""
    pytest.importorskip("textual")
    from harness_kit.tui.app import HarnessKitApp

    app = HarnessKitApp()
    async with app.run_test(size=(120, 40)) as pilot:
        # First go down
        await pilot.press("j")
        await pilot.press("j")
        idx_after_down = app._selected_index
        # Then go up
        await pilot.press("k")
        assert app._selected_index == idx_after_down - 1


@pytest.mark.asyncio
async def test_tui_k_key_clamps_at_top():
    """Pressing 'k' at the top does not go below 0."""
    pytest.importorskip("textual")
    from harness_kit.tui.app import HarnessKitApp

    app = HarnessKitApp()
    async with app.run_test(size=(120, 40)) as pilot:
        # Should already be at 0
        await pilot.press("k")
        assert app._selected_index == 0


@pytest.mark.asyncio
async def test_tui_j_key_clamps_at_bottom():
    """Pressing 'j' past the last item stays at the last item."""
    pytest.importorskip("textual")
    from harness_kit.tui.app import HarnessKitApp, NAV_ITEMS

    app = HarnessKitApp()
    async with app.run_test(size=(120, 40)) as pilot:
        # Press j many times
        for _ in range(len(NAV_ITEMS) + 5):
            await pilot.press("j")
        assert app._selected_index == len(NAV_ITEMS) - 1


@pytest.mark.asyncio
async def test_tui_question_mark_toggles_help():
    """Pressing '?' shows the help overlay."""
    pytest.importorskip("textual")
    from harness_kit.tui.app import HarnessKitApp, HelpOverlay

    app = HarnessKitApp()
    async with app.run_test(size=(120, 40)) as pilot:
        assert not app._help_visible
        await pilot.press("question_mark")
        assert app._help_visible
        # Overlay should be mounted
        overlays = app.query(HelpOverlay)
        assert len(overlays) == 1


@pytest.mark.asyncio
async def test_tui_question_mark_closes_help():
    """Pressing '?' twice hides the help overlay."""
    pytest.importorskip("textual")
    from harness_kit.tui.app import HarnessKitApp, HelpOverlay

    app = HarnessKitApp()
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.press("question_mark")
        assert app._help_visible
        await pilot.press("question_mark")
        assert not app._help_visible
        overlays = app.query(HelpOverlay)
        assert len(overlays) == 0


@pytest.mark.asyncio
async def test_tui_arrow_keys_navigate():
    """Down arrow key navigates to next item."""
    pytest.importorskip("textual")
    from harness_kit.tui.app import HarnessKitApp

    app = HarnessKitApp()
    async with app.run_test(size=(120, 40)) as pilot:
        initial = app._selected_index
        await pilot.press("down")
        assert app._selected_index == initial + 1


# ---------------------------------------------------------------------------
# CLI integration: tui command is registered
# ---------------------------------------------------------------------------


def test_cli_has_tui_command():
    """The main CLI app has a 'tui' command registered."""
    from typer.testing import CliRunner
    from harness_kit.cli import app

    runner = CliRunner()
    result = runner.invoke(app, ["--help"])
    assert "tui" in result.output
