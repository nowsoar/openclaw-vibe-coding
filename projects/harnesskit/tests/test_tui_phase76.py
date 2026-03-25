"""Tests for Phase 7.6 — TUI 优化与完善 (TUI polish & completion).

Covers:
- Enhanced help page (? key, scrollable, includes all shortcuts + theme toggle)
- Theme toggle (t key, dark ↔ light via textual-dark / textual-light themes)
- Responsive layout (on_resize narrows sidebar for small terminals)
- Error handling (exceptions in screen loading shown via notify, no crash)
"""

from __future__ import annotations

import pytest


# ---------------------------------------------------------------------------
# Unit tests — no TUI required
# ---------------------------------------------------------------------------


def test_theme_toggle_binding_exists():
    """BINDINGS includes 't' for theme toggle."""
    from harness_kit.tui.app import HarnessKitApp

    keys = {b.key for b in HarnessKitApp.BINDINGS}
    assert "t" in keys


def test_theme_toggle_action_callable():
    """action_toggle_theme exists and is callable."""
    from harness_kit.tui.app import HarnessKitApp

    app = HarnessKitApp()
    assert callable(getattr(app, "action_toggle_theme", None))


def test_help_overlay_css_has_overflow():
    """HelpOverlay DEFAULT_CSS references overflow-y or max-height for scrolling."""
    from harness_kit.tui.app import HelpOverlay

    css = HelpOverlay.DEFAULT_CSS
    assert "overflow-y" in css or "max-height" in css or "ScrollableContainer" in css


def test_help_overlay_css_has_scrollable_reference():
    """HelpOverlay DEFAULT_CSS targets ScrollableContainer for scroll styling."""
    from harness_kit.tui.app import HelpOverlay

    css = HelpOverlay.DEFAULT_CSS
    # Either max-height is set on the inner container or ScrollableContainer is targeted
    assert "max-height" in css or "overflow" in css


def test_on_resize_method_exists():
    """HarnessKitApp has on_resize method for responsive layout."""
    from harness_kit.tui.app import HarnessKitApp

    app = HarnessKitApp()
    assert callable(getattr(app, "on_resize", None))


def test_app_instantiation_stable():
    """HarnessKitApp instantiates without exceptions after Phase 7.6 changes."""
    from harness_kit.tui.app import HarnessKitApp

    app = HarnessKitApp()
    assert app is not None


def test_all_original_bindings_preserved():
    """Phase 7.6 additions do not remove original bindings (q/j/k/enter/?/arrows)."""
    from harness_kit.tui.app import HarnessKitApp

    keys = {b.key for b in HarnessKitApp.BINDINGS}
    for required_key in ("q", "j", "k", "question_mark", "enter", "up", "down"):
        assert required_key in keys, f"Missing binding: {required_key}"


def test_action_select_item_has_error_handling():
    """action_select_item source contains try/except for error recovery."""
    import inspect

    from harness_kit.tui.app import HarnessKitApp

    source = inspect.getsource(HarnessKitApp.action_select_item)
    assert "try" in source and "except" in source


def test_on_list_view_selected_has_error_handling():
    """on_list_view_selected source contains try/except for error recovery."""
    import inspect

    from harness_kit.tui.app import HarnessKitApp

    source = inspect.getsource(HarnessKitApp.on_list_view_selected)
    assert "try" in source and "except" in source


def test_action_toggle_theme_source_uses_theme_property():
    """action_toggle_theme uses self.theme for textual 8.x compatibility."""
    import inspect

    from harness_kit.tui.app import HarnessKitApp

    source = inspect.getsource(HarnessKitApp.action_toggle_theme)
    assert "self.theme" in source
    assert "textual-dark" in source or "textual-light" in source


def test_on_resize_source_adjusts_sidebar():
    """on_resize adjusts sidebar width based on terminal size."""
    import inspect

    from harness_kit.tui.app import HarnessKitApp

    source = inspect.getsource(HarnessKitApp.on_resize)
    assert "Sidebar" in source or "sidebar" in source
    assert "width" in source


# ---------------------------------------------------------------------------
# Pilot tests — async, use Textual's test framework
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_theme_toggle_changes_theme():
    """Pressing 't' changes the app theme between dark and light."""
    pytest.importorskip("textual")
    from harness_kit.tui.app import HarnessKitApp

    app = HarnessKitApp()
    async with app.run_test(size=(120, 40)) as pilot:
        initial_theme = app.theme
        await pilot.press("t")
        assert app.theme != initial_theme


@pytest.mark.asyncio
async def test_theme_toggle_twice_restores_state():
    """Pressing 't' twice returns to the original theme."""
    pytest.importorskip("textual")
    from harness_kit.tui.app import HarnessKitApp

    app = HarnessKitApp()
    async with app.run_test(size=(120, 40)) as pilot:
        initial_theme = app.theme
        await pilot.press("t")
        await pilot.press("t")
        assert app.theme == initial_theme


@pytest.mark.asyncio
async def test_theme_toggles_between_dark_and_light():
    """Theme toggle switches between textual-dark and textual-light."""
    pytest.importorskip("textual")
    from harness_kit.tui.app import HarnessKitApp

    app = HarnessKitApp()
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.press("t")
        assert app.theme in ("textual-dark", "textual-light")
        await pilot.press("t")
        assert app.theme in ("textual-dark", "textual-light")


@pytest.mark.asyncio
async def test_help_overlay_shows_on_question_mark():
    """Pressing '?' shows the HelpOverlay (Phase 7.1 regression check)."""
    pytest.importorskip("textual")
    from harness_kit.tui.app import HarnessKitApp, HelpOverlay

    app = HarnessKitApp()
    async with app.run_test(size=(120, 40)) as pilot:
        assert not app._help_visible
        await pilot.press("question_mark")
        assert app._help_visible
        assert len(app.query(HelpOverlay)) == 1


@pytest.mark.asyncio
async def test_help_overlay_closes_on_any_key():
    """Pressing any non-? key closes the HelpOverlay."""
    pytest.importorskip("textual")
    from harness_kit.tui.app import HarnessKitApp, HelpOverlay

    app = HarnessKitApp()
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.press("question_mark")
        assert app._help_visible
        await pilot.press("escape")
        assert not app._help_visible
        assert len(app.query(HelpOverlay)) == 0


@pytest.mark.asyncio
async def test_help_overlay_is_scrollable_at_runtime():
    """HelpOverlay mounts without error and contains a scrollable container."""
    pytest.importorskip("textual")
    from textual.containers import ScrollableContainer

    from harness_kit.tui.app import HarnessKitApp, HelpOverlay

    app = HarnessKitApp()
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.press("question_mark")
        # Query for ScrollableContainer inside the overlay
        overlay = app.query_one(HelpOverlay)
        scrollables = overlay.query(ScrollableContainer)
        assert len(scrollables) >= 1


@pytest.mark.asyncio
async def test_help_overlay_content_mentions_theme():
    """HelpOverlay content visible in TUI mentions the 't' theme-toggle key."""
    pytest.importorskip("textual")
    from harness_kit.tui.app import HarnessKitApp, HelpOverlay
    from textual.widgets import Label

    app = HarnessKitApp()
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.press("question_mark")
        overlay = app.query_one(HelpOverlay)
        labels = overlay.query(Label)
        # In textual 8.x, Static/Label stores content as .content (Text/str)
        all_text = " ".join(str(label.content) for label in labels)
        # 't' key for theme toggle must appear in help content
        assert "t" in all_text
        assert "主题" in all_text or "theme" in all_text.lower() or "Theme" in all_text


@pytest.mark.asyncio
async def test_responsive_narrow_terminal():
    """On a narrow terminal (<80 cols), sidebar width is ≤ 20 after resize event."""
    pytest.importorskip("textual")
    from textual.events import Resize
    from textual.geometry import Size

    from harness_kit.tui.app import HarnessKitApp, Sidebar

    app = HarnessKitApp()
    async with app.run_test(size=(70, 30)) as pilot:
        resize_event = Resize(Size(70, 30), Size(70, 30))
        app.on_resize(resize_event)
        sidebar = app.query_one(Sidebar)
        width_val = sidebar.styles.width
        # styles.width is a Scalar — compare its value
        if hasattr(width_val, "value"):
            assert width_val.value <= 20
        else:
            assert float(str(width_val).rstrip("wvh%")) <= 20


@pytest.mark.asyncio
async def test_responsive_wide_terminal():
    """On a wide terminal (≥100 cols), sidebar width is 24 after resize event."""
    pytest.importorskip("textual")
    from textual.events import Resize
    from textual.geometry import Size

    from harness_kit.tui.app import HarnessKitApp, Sidebar

    app = HarnessKitApp()
    async with app.run_test(size=(120, 40)) as pilot:
        resize_event = Resize(Size(120, 40), Size(120, 40))
        app.on_resize(resize_event)
        sidebar = app.query_one(Sidebar)
        width_val = sidebar.styles.width
        if hasattr(width_val, "value"):
            assert width_val.value == 24
        else:
            assert float(str(width_val).rstrip("wvh%")) == 24


@pytest.mark.asyncio
async def test_app_does_not_crash_on_nav():
    """Navigating all nav items with j/k does not crash the app."""
    pytest.importorskip("textual")
    from harness_kit.tui.app import HarnessKitApp, NAV_ITEMS

    app = HarnessKitApp()
    async with app.run_test(size=(120, 40)) as pilot:
        for _ in range(len(NAV_ITEMS) + 2):
            await pilot.press("j")
        for _ in range(len(NAV_ITEMS) + 2):
            await pilot.press("k")
        assert app.is_running


@pytest.mark.asyncio
async def test_theme_toggle_does_not_affect_nav():
    """Toggling theme does not change selected index or break navigation."""
    pytest.importorskip("textual")
    from harness_kit.tui.app import HarnessKitApp

    app = HarnessKitApp()
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.press("j")
        idx_before = app._selected_index
        await pilot.press("t")
        assert app._selected_index == idx_before


@pytest.mark.asyncio
async def test_help_and_theme_combo():
    """Opening help then pressing 't' (closes help + toggles theme) works correctly."""
    pytest.importorskip("textual")
    from harness_kit.tui.app import HarnessKitApp, HelpOverlay

    app = HarnessKitApp()
    async with app.run_test(size=(120, 40)) as pilot:
        initial_theme = app.theme
        await pilot.press("question_mark")
        assert app._help_visible
        # 't' is not '?', so it also closes the help overlay
        await pilot.press("t")
        # Help should be closed
        assert not app._help_visible
        # Theme should have changed
        assert app.theme != initial_theme
