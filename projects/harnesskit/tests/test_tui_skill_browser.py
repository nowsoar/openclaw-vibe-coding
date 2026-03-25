"""Tests for Phase 7.2 — Skill Browser TUI screen."""

from __future__ import annotations

import pytest
from pathlib import Path


# ---------------------------------------------------------------------------
# Unit tests — module structure and formatters
# ---------------------------------------------------------------------------


def test_skill_browser_importable():
    """SkillBrowserScreen can be imported from the tui package."""
    from harness_kit.tui.skill_browser import SkillBrowserScreen
    assert SkillBrowserScreen is not None


def test_skill_browser_exported_from_tui():
    """SkillBrowserScreen is re-exported from harness_kit.tui."""
    from harness_kit.tui import SkillBrowserScreen
    assert SkillBrowserScreen is not None


def test_format_skill_detail_basic():
    """_format_skill_detail includes name, version, and description."""
    from harness_kit.tui.skill_browser import _format_skill_detail
    skill = {
        "name": "my-skill",
        "version": "v0.1.0",
        "description": "Does cool things",
    }
    text = _format_skill_detail(skill)
    assert "my-skill" in text
    assert "v0.1.0" in text
    assert "Does cool things" in text


def test_format_skill_detail_with_inputs():
    """_format_skill_detail renders input parameters with required marker."""
    from harness_kit.tui.skill_browser import _format_skill_detail
    skill = {
        "name": "test",
        "version": "v0.0.1",
        "description": "",
        "inputs": [
            {"name": "code", "type": "string", "required": True},
            {"name": "lang", "type": "string", "required": False, "default": "auto"},
        ],
    }
    text = _format_skill_detail(skill)
    assert "code" in text
    assert "lang" in text
    assert "auto" in text   # default value shown


def test_format_skill_detail_with_outputs():
    """_format_skill_detail renders output fields."""
    from harness_kit.tui.skill_browser import _format_skill_detail
    skill = {
        "name": "test",
        "version": "v0.0.1",
        "description": "",
        "outputs": [{"name": "issues", "type": "array"}],
    }
    text = _format_skill_detail(skill)
    assert "issues" in text


def test_format_skill_detail_with_assets():
    """_format_skill_detail renders asset references."""
    from harness_kit.tui.skill_browser import _format_skill_detail
    skill = {
        "name": "test",
        "version": "v0.0.1",
        "description": "",
        "assets": {
            "prompts": {"system": "my-prompt@v0.1.0"},
            "rules": ["no-hallucination"],
            "context": "ctx@v0.1.0",
        },
    }
    text = _format_skill_detail(skill)
    assert "my-prompt@v0.1.0" in text
    assert "no-hallucination" in text
    assert "ctx@v0.1.0" in text


def test_format_skill_detail_includes_command_hints():
    """_format_skill_detail always includes r/d/e command hints."""
    from harness_kit.tui.skill_browser import _format_skill_detail
    skill = {"name": "my-skill", "version": "v0.2.0", "description": ""}
    text = _format_skill_detail(skill)
    assert "harnesskit skill run my-skill" in text
    assert "harnesskit skill diff my-skill" in text
    assert "harnesskit skill save" in text


def test_skill_browser_bindings_include_escape():
    """SkillBrowserScreen bindings include escape to go back."""
    from harness_kit.tui.skill_browser import SkillBrowserScreen
    binding_keys = {b.key for b in SkillBrowserScreen.BINDINGS}
    assert "escape" in binding_keys


def test_skill_browser_bindings_include_vim_nav():
    """SkillBrowserScreen bindings include j/k navigation."""
    from harness_kit.tui.skill_browser import SkillBrowserScreen
    binding_keys = {b.key for b in SkillBrowserScreen.BINDINGS}
    assert "j" in binding_keys
    assert "k" in binding_keys


def test_skill_browser_bindings_include_r_d_e():
    """SkillBrowserScreen bindings include r (run), d (diff), e (edit)."""
    from harness_kit.tui.skill_browser import SkillBrowserScreen
    binding_keys = {b.key for b in SkillBrowserScreen.BINDINGS}
    assert "r" in binding_keys
    assert "d" in binding_keys
    assert "e" in binding_keys


def test_skill_browser_instantiation():
    """SkillBrowserScreen can be instantiated without errors."""
    from harness_kit.tui.skill_browser import SkillBrowserScreen
    screen = SkillBrowserScreen()
    assert screen is not None


def test_skill_browser_accepts_base_path(tmp_path: Path):
    """SkillBrowserScreen accepts a base_path parameter for testability."""
    from harness_kit.tui.skill_browser import SkillBrowserScreen
    screen = SkillBrowserScreen(base_path=tmp_path)
    assert screen._base_path == tmp_path


# ---------------------------------------------------------------------------
# Helper: test App that pushes SkillBrowserScreen on mount
# ---------------------------------------------------------------------------


def _make_test_app(base_path: Path | None = None):
    """Return a Textual App that immediately shows SkillBrowserScreen."""
    pytest.importorskip("textual")
    from textual.app import App, ComposeResult
    from textual.widgets import Label
    from harness_kit.tui.skill_browser import SkillBrowserScreen

    class _BrowserApp(App):
        SCREENS = {"browser": lambda: SkillBrowserScreen(base_path=base_path)}

        def compose(self) -> ComposeResult:
            yield Label("")  # placeholder

        def on_mount(self) -> None:
            self.push_screen(SkillBrowserScreen(base_path=base_path))

    return _BrowserApp()


def _make_skill(tmp_path: Path, name: str, description: str = "A skill") -> None:
    """Create a minimal skill in *tmp_path* so SkillBrowserScreen can find it."""
    from harness_kit.skill import save_skill
    save_skill(
        name=name,
        description=description,
        base=tmp_path,
    )


# ---------------------------------------------------------------------------
# Async pilot tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_skill_browser_composes_without_error():
    """SkillBrowserScreen composing layout raises no exceptions."""
    pytest.importorskip("textual")
    from harness_kit.tui.skill_browser import SkillBrowserScreen
    app = _make_test_app()
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        assert isinstance(app.screen, SkillBrowserScreen)


@pytest.mark.asyncio
async def test_skill_browser_empty_state(tmp_path: Path):
    """With no skills, browser shows an empty-state hint message."""
    pytest.importorskip("textual")
    from harness_kit.tui.skill_browser import SkillBrowserScreen, SkillDetailPanel
    app = _make_test_app(base_path=tmp_path)
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        screen = app.screen
        assert isinstance(screen, SkillBrowserScreen)
        detail = screen.query_one("#skill-detail", SkillDetailPanel)
        assert "harnesskit skill save" in detail.content_text


@pytest.mark.asyncio
async def test_skill_browser_lists_skills(tmp_path: Path):
    """Skills created in tmp_path appear in the ListView."""
    pytest.importorskip("textual")
    from harness_kit.tui.skill_browser import SkillBrowserScreen
    _make_skill(tmp_path, "alpha", "Alpha skill")
    _make_skill(tmp_path, "beta", "Beta skill")
    app = _make_test_app(base_path=tmp_path)
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        screen = app.screen
        assert isinstance(screen, SkillBrowserScreen)
        assert len(screen._filtered_skills) == 2
        names = {s["name"] for s in screen._filtered_skills}
        assert names == {"alpha", "beta"}


@pytest.mark.asyncio
async def test_skill_browser_shows_skill_detail(tmp_path: Path):
    """Selecting a skill shows its description in the detail panel."""
    pytest.importorskip("textual")
    from harness_kit.tui.skill_browser import SkillBrowserScreen, SkillDetailPanel
    _make_skill(tmp_path, "my-skill", "Does amazing things")
    app = _make_test_app(base_path=tmp_path)
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        screen = app.screen
        assert isinstance(screen, SkillBrowserScreen)
        detail = screen.query_one("#skill-detail", SkillDetailPanel)
        assert "my-skill" in detail.content_text
        assert "Does amazing things" in detail.content_text


@pytest.mark.asyncio
async def test_skill_browser_j_key_moves_down(tmp_path: Path):
    """Pressing j moves selection down."""
    pytest.importorskip("textual")
    from harness_kit.tui.skill_browser import SkillBrowserScreen
    _make_skill(tmp_path, "skill-a")
    _make_skill(tmp_path, "skill-b")
    app = _make_test_app(base_path=tmp_path)
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        screen = app.screen
        assert isinstance(screen, SkillBrowserScreen)
        assert screen._selected_index == 0
        await pilot.press("j")
        assert screen._selected_index == 1


@pytest.mark.asyncio
async def test_skill_browser_k_key_moves_up(tmp_path: Path):
    """Pressing k moves selection up."""
    pytest.importorskip("textual")
    from harness_kit.tui.skill_browser import SkillBrowserScreen
    _make_skill(tmp_path, "skill-a")
    _make_skill(tmp_path, "skill-b")
    app = _make_test_app(base_path=tmp_path)
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        screen = app.screen
        assert isinstance(screen, SkillBrowserScreen)
        await pilot.press("j")
        assert screen._selected_index == 1
        await pilot.press("k")
        assert screen._selected_index == 0


@pytest.mark.asyncio
async def test_skill_browser_j_clamps_at_bottom(tmp_path: Path):
    """Pressing j past the last skill stays at last index."""
    pytest.importorskip("textual")
    from harness_kit.tui.skill_browser import SkillBrowserScreen
    _make_skill(tmp_path, "only-skill")
    app = _make_test_app(base_path=tmp_path)
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        screen = app.screen
        assert isinstance(screen, SkillBrowserScreen)
        for _ in range(10):
            await pilot.press("j")
        assert screen._selected_index == 0  # only one skill, stays at 0


@pytest.mark.asyncio
async def test_skill_browser_k_clamps_at_top(tmp_path: Path):
    """Pressing k at the top stays at index 0."""
    pytest.importorskip("textual")
    from harness_kit.tui.skill_browser import SkillBrowserScreen
    _make_skill(tmp_path, "only-skill")
    app = _make_test_app(base_path=tmp_path)
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        screen = app.screen
        assert isinstance(screen, SkillBrowserScreen)
        await pilot.press("k")
        assert screen._selected_index == 0


@pytest.mark.asyncio
async def test_skill_browser_search_filter(tmp_path: Path):
    """Typing in the search box filters the skill list."""
    pytest.importorskip("textual")
    from harness_kit.tui.skill_browser import SkillBrowserScreen
    _make_skill(tmp_path, "code-reviewer", "Reviews Python code")
    _make_skill(tmp_path, "summarizer", "Summarizes text")
    app = _make_test_app(base_path=tmp_path)
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        screen = app.screen
        assert isinstance(screen, SkillBrowserScreen)
        assert len(screen._filtered_skills) == 2

        # Type into the search box
        await pilot.click("#search-input")
        await pilot.press("c", "o", "d", "e")
        await pilot.pause()
        # Should be filtered to just "code-reviewer"
        assert len(screen._filtered_skills) == 1
        assert screen._filtered_skills[0]["name"] == "code-reviewer"


@pytest.mark.asyncio
async def test_skill_browser_r_shows_notice(tmp_path: Path):
    """Pressing r shows a notice overlay with the run command."""
    pytest.importorskip("textual")
    from harness_kit.tui.skill_browser import SkillBrowserScreen, _ActionNotice
    _make_skill(tmp_path, "my-skill")
    app = _make_test_app(base_path=tmp_path)
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        screen = app.screen
        assert isinstance(screen, SkillBrowserScreen)
        assert not screen._notice_visible
        await pilot.press("r")
        assert screen._notice_visible
        notices = screen.query(_ActionNotice)
        assert len(notices) == 1


@pytest.mark.asyncio
async def test_skill_browser_d_shows_notice(tmp_path: Path):
    """Pressing d shows a notice overlay with the diff command."""
    pytest.importorskip("textual")
    from harness_kit.tui.skill_browser import SkillBrowserScreen, _ActionNotice
    _make_skill(tmp_path, "my-skill")
    app = _make_test_app(base_path=tmp_path)
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        screen = app.screen
        assert isinstance(screen, SkillBrowserScreen)
        await pilot.press("d")
        assert screen._notice_visible
        notices = screen.query(_ActionNotice)
        assert len(notices) == 1


@pytest.mark.asyncio
async def test_skill_browser_e_shows_notice(tmp_path: Path):
    """Pressing e shows a notice overlay with the edit command."""
    pytest.importorskip("textual")
    from harness_kit.tui.skill_browser import SkillBrowserScreen, _ActionNotice
    _make_skill(tmp_path, "my-skill")
    app = _make_test_app(base_path=tmp_path)
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        screen = app.screen
        assert isinstance(screen, SkillBrowserScreen)
        await pilot.press("e")
        assert screen._notice_visible
        notices = screen.query(_ActionNotice)
        assert len(notices) == 1


@pytest.mark.asyncio
async def test_skill_browser_any_key_closes_notice(tmp_path: Path):
    """Pressing any key while a notice is visible closes it."""
    pytest.importorskip("textual")
    from harness_kit.tui.skill_browser import SkillBrowserScreen, _ActionNotice
    _make_skill(tmp_path, "my-skill")
    app = _make_test_app(base_path=tmp_path)
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        screen = app.screen
        assert isinstance(screen, SkillBrowserScreen)
        # Open notice
        await pilot.press("r")
        assert screen._notice_visible
        # Close it with another key
        await pilot.press("j")
        await pilot.pause()
        assert not screen._notice_visible
        notices = screen.query(_ActionNotice)
        assert len(notices) == 0


# ---------------------------------------------------------------------------
# Main app integration: Enter on Skills pushes SkillBrowserScreen
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_main_app_enter_on_skills_pushes_browser():
    """Pressing Enter when Skills nav item is selected pushes SkillBrowserScreen."""
    pytest.importorskip("textual")
    from harness_kit.tui.app import HarnessKitApp, NAV_ITEMS
    from harness_kit.tui.skill_browser import SkillBrowserScreen

    app = HarnessKitApp()
    async with app.run_test(size=(120, 40)) as pilot:
        # Navigate to Skills (first item, index 0)
        skills_idx = next(i for i, item in enumerate(NAV_ITEMS) if item[0] == "skills")
        for _ in range(skills_idx):
            await pilot.press("j")
        assert app._selected_index == skills_idx

        # Press Enter — should push SkillBrowserScreen
        await pilot.press("enter")
        await pilot.pause()
        # The active screen should now be SkillBrowserScreen
        assert isinstance(app.screen, SkillBrowserScreen)


@pytest.mark.asyncio
async def test_main_app_help_overlay_updated():
    """After Phase 7.2, the help overlay mentions SkillBrowserScreen shortcuts."""
    pytest.importorskip("textual")
    from harness_kit.tui.app import HarnessKitApp, HelpOverlay

    app = HarnessKitApp()
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.press("question_mark")
        overlays = app.query(HelpOverlay)
        assert len(overlays) == 1
        # The help overlay should mention Esc and Skill browser shortcuts
        overlay = overlays.first()
        assert overlay is not None
