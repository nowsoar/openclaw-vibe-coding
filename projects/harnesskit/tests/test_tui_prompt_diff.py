"""Tests for Phase 7.3 — Prompt Diff TUI screen."""

from __future__ import annotations

import pytest
from pathlib import Path


# ---------------------------------------------------------------------------
# Unit tests — pure helper functions
# ---------------------------------------------------------------------------


def test_escape_markup_replaces_brackets():
    """_escape_markup replaces [ and ] with escaped equivalents."""
    from harness_kit.tui.prompt_diff import _escape_markup
    result = _escape_markup("hello [world] test")
    assert "\\[" in result
    assert "\\]" in result


def test_escape_markup_no_brackets():
    """_escape_markup leaves text without brackets unchanged."""
    from harness_kit.tui.prompt_diff import _escape_markup
    assert _escape_markup("plain text") == "plain text"


def test_inline_diff_equal_lines():
    """_inline_diff returns unchanged text when lines are identical."""
    from harness_kit.tui.prompt_diff import _inline_diff
    old_m, new_m = _inline_diff("hello world", "hello world")
    # No bold/underline markup should be added for equal content
    assert "hello" in old_m
    assert "hello" in new_m
    assert "bold" not in old_m
    assert "bold" not in new_m


def test_inline_diff_changed_segment():
    """_inline_diff highlights changed characters with bold markup."""
    from harness_kit.tui.prompt_diff import _inline_diff
    old_m, new_m = _inline_diff("hello world", "hello Python")
    # Changed part should be bolded
    assert "[bold" in old_m or "[bold" in new_m


def test_inline_diff_returns_tuple():
    """_inline_diff always returns a 2-tuple of strings."""
    from harness_kit.tui.prompt_diff import _inline_diff
    result = _inline_diff("old line", "new line")
    assert isinstance(result, tuple)
    assert len(result) == 2
    assert isinstance(result[0], str)
    assert isinstance(result[1], str)


def test_build_diff_panes_identical_content():
    """build_diff_panes on identical content produces no add/remove markup."""
    from harness_kit.tui.prompt_diff import build_diff_panes
    content = "line one\nline two\nline three"
    left, right = build_diff_panes(content, content, "a@v1", "a@v1")
    # No red deletions or green additions when content is the same
    assert "[red]" not in left
    assert "[green]" not in right


def test_build_diff_panes_deleted_lines():
    """build_diff_panes marks deleted lines in red on the left pane."""
    from harness_kit.tui.prompt_diff import build_diff_panes
    old = "line one\nline two\nline three"
    new = "line one\nline three"
    left, right = build_diff_panes(old, new, "a@v1", "a@v2")
    assert "[red]" in left


def test_build_diff_panes_added_lines():
    """build_diff_panes marks added lines in green on the right pane."""
    from harness_kit.tui.prompt_diff import build_diff_panes
    old = "line one\nline three"
    new = "line one\nline two\nline three"
    left, right = build_diff_panes(old, new, "a@v1", "a@v2")
    assert "[green]" in right


def test_build_diff_panes_returns_tuple():
    """build_diff_panes always returns a 2-tuple of strings."""
    from harness_kit.tui.prompt_diff import build_diff_panes
    result = build_diff_panes("old", "new", "old", "new")
    assert isinstance(result, tuple)
    assert len(result) == 2


def test_build_diff_panes_includes_labels():
    """build_diff_panes includes the provided labels as headers."""
    from harness_kit.tui.prompt_diff import build_diff_panes
    left, right = build_diff_panes("a", "b", "my-prompt@v0.1.0", "my-prompt@v0.2.0")
    assert "my-prompt" in left
    assert "my-prompt" in right
    assert "v0.1.0" in left
    assert "v0.2.0" in right


def test_build_diff_panes_empty_inputs():
    """build_diff_panes handles empty content gracefully."""
    from harness_kit.tui.prompt_diff import build_diff_panes
    left, right = build_diff_panes("", "", "a@v1", "a@v2")
    assert isinstance(left, str)
    assert isinstance(right, str)


def test_build_diff_panes_context_lines_both_sides():
    """build_diff_panes shows unchanged context lines in both panes."""
    from harness_kit.tui.prompt_diff import build_diff_panes
    old = "common line\nchanged line"
    new = "common line\nnew line"
    left, right = build_diff_panes(old, new, "a@v1", "a@v2")
    assert "common" in left
    assert "common" in right


def test_build_diff_panes_inline_diff_applied():
    """build_diff_panes applies inline diff for replaced lines."""
    from harness_kit.tui.prompt_diff import build_diff_panes
    old = "The quick brown fox"
    new = "The quick green fox"
    left, right = build_diff_panes(old, new, "a@v1", "a@v2")
    # Inline diff should highlight "brown" vs "green" with bold markup
    assert "[bold" in left or "[bold" in right


# ---------------------------------------------------------------------------
# Module structure tests
# ---------------------------------------------------------------------------


def test_prompt_diff_importable():
    """PromptDiffScreen can be imported from harness_kit.tui.prompt_diff."""
    from harness_kit.tui.prompt_diff import PromptDiffScreen
    assert PromptDiffScreen is not None


def test_prompt_diff_exported_from_tui():
    """PromptDiffScreen is re-exported from harness_kit.tui."""
    from harness_kit.tui import PromptDiffScreen
    assert PromptDiffScreen is not None


def test_diff_pane_widget_importable():
    """_DiffPane widget is importable."""
    from harness_kit.tui.prompt_diff import _DiffPane
    assert _DiffPane is not None


def test_prompt_diff_instantiation():
    """PromptDiffScreen can be instantiated without errors."""
    from harness_kit.tui.prompt_diff import PromptDiffScreen
    screen = PromptDiffScreen()
    assert screen is not None


def test_prompt_diff_accepts_base_path(tmp_path: Path):
    """PromptDiffScreen accepts a base_path parameter."""
    from harness_kit.tui.prompt_diff import PromptDiffScreen
    screen = PromptDiffScreen(base_path=tmp_path)
    assert screen._base_path == tmp_path


def test_prompt_diff_bindings_include_escape():
    """PromptDiffScreen bindings include escape to go back."""
    from harness_kit.tui.prompt_diff import PromptDiffScreen
    keys = {b.key for b in PromptDiffScreen.BINDINGS}
    assert "escape" in keys


def test_prompt_diff_bindings_include_vim_nav():
    """PromptDiffScreen bindings include j/k for scrolling."""
    from harness_kit.tui.prompt_diff import PromptDiffScreen
    keys = {b.key for b in PromptDiffScreen.BINDINGS}
    assert "j" in keys
    assert "k" in keys


# ---------------------------------------------------------------------------
# Helper — create prompt in tmp_path
# ---------------------------------------------------------------------------


def _make_prompt(tmp_path: Path, name: str, content: str) -> str:
    """Create a prompt version in *tmp_path* and return the version string."""
    from harness_kit.prompt import save_prompt
    version, _ = save_prompt(name=name, content=content, base=tmp_path)
    return version


def _make_test_app(base_path: Path | None = None):
    """Return a Textual App that immediately shows PromptDiffScreen."""
    pytest.importorskip("textual")
    from textual.app import App, ComposeResult
    from textual.widgets import Label
    from harness_kit.tui.prompt_diff import PromptDiffScreen

    class _DiffApp(App):
        def compose(self) -> ComposeResult:
            yield Label("")

        def on_mount(self) -> None:
            self.push_screen(PromptDiffScreen(base_path=base_path))

    return _DiffApp()


# ---------------------------------------------------------------------------
# Async pilot tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_prompt_diff_composes_without_error():
    """PromptDiffScreen composes without raising exceptions."""
    pytest.importorskip("textual")
    from harness_kit.tui.prompt_diff import PromptDiffScreen
    app = _make_test_app()
    async with app.run_test(size=(160, 50)) as pilot:
        await pilot.pause()
        assert isinstance(app.screen, PromptDiffScreen)


@pytest.mark.asyncio
async def test_prompt_diff_empty_state(tmp_path: Path):
    """With no prompts, screen shows an empty-state message."""
    pytest.importorskip("textual")
    from harness_kit.tui.prompt_diff import PromptDiffScreen, _DiffPane
    app = _make_test_app(base_path=tmp_path)
    async with app.run_test(size=(160, 50)) as pilot:
        await pilot.pause()
        screen = app.screen
        assert isinstance(screen, PromptDiffScreen)
        left_pane = screen.query_one("#left-pane", _DiffPane)
        assert "harnesskit prompt save" in left_pane.content_text


@pytest.mark.asyncio
async def test_prompt_diff_loads_prompt(tmp_path: Path):
    """PromptDiffScreen loads prompts and shows them in the list."""
    pytest.importorskip("textual")
    from harness_kit.tui.prompt_diff import PromptDiffScreen
    _make_prompt(tmp_path, "my-prompt", "Hello world")
    app = _make_test_app(base_path=tmp_path)
    async with app.run_test(size=(160, 50)) as pilot:
        await pilot.pause()
        screen = app.screen
        assert isinstance(screen, PromptDiffScreen)
        assert len(screen._prompts) == 1
        assert screen._prompts[0]["name"] == "my-prompt"


@pytest.mark.asyncio
async def test_prompt_diff_single_version(tmp_path: Path):
    """With one version, old and new are both set to the same version."""
    pytest.importorskip("textual")
    from harness_kit.tui.prompt_diff import PromptDiffScreen
    _make_prompt(tmp_path, "single", "only version")
    app = _make_test_app(base_path=tmp_path)
    async with app.run_test(size=(160, 50)) as pilot:
        await pilot.pause()
        screen = app.screen
        assert isinstance(screen, PromptDiffScreen)
        assert screen._old_ver is not None
        assert screen._new_ver is not None
        assert screen._old_ver == screen._new_ver == "v0.0.1"


@pytest.mark.asyncio
async def test_prompt_diff_two_versions_shown(tmp_path: Path):
    """With two versions, old defaults to v1 and new defaults to v2."""
    pytest.importorskip("textual")
    from harness_kit.tui.prompt_diff import PromptDiffScreen
    _make_prompt(tmp_path, "evolving", "version one content")
    _make_prompt(tmp_path, "evolving", "version two content")
    app = _make_test_app(base_path=tmp_path)
    async with app.run_test(size=(160, 50)) as pilot:
        await pilot.pause()
        screen = app.screen
        assert isinstance(screen, PromptDiffScreen)
        assert screen._old_ver == "v0.0.1"
        assert screen._new_ver == "v0.0.2"


@pytest.mark.asyncio
async def test_prompt_diff_panes_populated(tmp_path: Path):
    """After loading, diff panes contain content from the prompt."""
    pytest.importorskip("textual")
    from harness_kit.tui.prompt_diff import PromptDiffScreen, _DiffPane
    _make_prompt(tmp_path, "test-prompt", "old content here")
    _make_prompt(tmp_path, "test-prompt", "new content here")
    app = _make_test_app(base_path=tmp_path)
    async with app.run_test(size=(160, 50)) as pilot:
        await pilot.pause()
        screen = app.screen
        assert isinstance(screen, PromptDiffScreen)
        left_pane = screen.query_one("#left-pane", _DiffPane)
        right_pane = screen.query_one("#right-pane", _DiffPane)
        # Panes should have some diff content
        assert len(left_pane.content_text) > 0
        assert len(right_pane.content_text) > 0


@pytest.mark.asyncio
async def test_prompt_diff_panes_show_label(tmp_path: Path):
    """Diff panes include the prompt name in their header."""
    pytest.importorskip("textual")
    from harness_kit.tui.prompt_diff import PromptDiffScreen, _DiffPane
    _make_prompt(tmp_path, "awesome-prompt", "content v1")
    _make_prompt(tmp_path, "awesome-prompt", "content v2")
    app = _make_test_app(base_path=tmp_path)
    async with app.run_test(size=(160, 50)) as pilot:
        await pilot.pause()
        screen = app.screen
        assert isinstance(screen, PromptDiffScreen)
        left_pane = screen.query_one("#left-pane", _DiffPane)
        right_pane = screen.query_one("#right-pane", _DiffPane)
        assert "awesome-prompt" in left_pane.content_text
        assert "awesome-prompt" in right_pane.content_text


@pytest.mark.asyncio
async def test_prompt_diff_escape_goes_back():
    """Pressing Escape returns to the main app screen."""
    pytest.importorskip("textual")
    from harness_kit.tui.prompt_diff import PromptDiffScreen
    app = _make_test_app()
    async with app.run_test(size=(160, 50)) as pilot:
        await pilot.pause()
        assert isinstance(app.screen, PromptDiffScreen)
        await pilot.press("escape")
        await pilot.pause()
        assert not isinstance(app.screen, PromptDiffScreen)


@pytest.mark.asyncio
async def test_prompt_diff_j_k_scroll(tmp_path: Path):
    """Pressing j and k does not crash the screen (scroll actions)."""
    pytest.importorskip("textual")
    from harness_kit.tui.prompt_diff import PromptDiffScreen
    _make_prompt(tmp_path, "scroll-test", "\n".join(f"line {i}" for i in range(50)))
    _make_prompt(tmp_path, "scroll-test", "\n".join(f"line {i} updated" for i in range(50)))
    app = _make_test_app(base_path=tmp_path)
    async with app.run_test(size=(160, 50)) as pilot:
        await pilot.pause()
        screen = app.screen
        assert isinstance(screen, PromptDiffScreen)
        # Pressing j/k should not raise errors
        for _ in range(5):
            await pilot.press("j")
        for _ in range(3):
            await pilot.press("k")


# ---------------------------------------------------------------------------
# Main app integration: Enter on Prompts pushes PromptDiffScreen
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_main_app_enter_on_prompts_pushes_diff_screen():
    """Pressing Enter on the Prompts nav item opens PromptDiffScreen."""
    pytest.importorskip("textual")
    from harness_kit.tui.app import HarnessKitApp, NAV_ITEMS
    from harness_kit.tui.prompt_diff import PromptDiffScreen

    app = HarnessKitApp()
    async with app.run_test(size=(120, 40)) as pilot:
        # Find the index of the "prompts" nav item
        prompts_idx = next(i for i, item in enumerate(NAV_ITEMS) if item[0] == "prompts")
        # Navigate to Prompts
        for _ in range(prompts_idx):
            await pilot.press("j")
        assert app._selected_index == prompts_idx

        # Press Enter — should push PromptDiffScreen
        await pilot.press("enter")
        await pilot.pause()
        assert isinstance(app.screen, PromptDiffScreen)


@pytest.mark.asyncio
async def test_main_app_nav_includes_prompts():
    """NAV_ITEMS includes a 'prompts' entry for the Prompt Diff feature."""
    from harness_kit.tui.app import NAV_ITEMS
    item_ids = [item[0] for item in NAV_ITEMS]
    assert "prompts" in item_ids


def test_nav_items_prompts_label():
    """The 'prompts' NAV_ITEM has a recognisable label."""
    from harness_kit.tui.app import NAV_ITEMS
    prompts_item = next(item for item in NAV_ITEMS if item[0] == "prompts")
    assert "Prompt" in prompts_item[1]


def test_nav_items_prompts_description():
    """The 'prompts' NAV_ITEM description mentions diff functionality."""
    from harness_kit.tui.app import NAV_ITEMS
    prompts_item = next(item for item in NAV_ITEMS if item[0] == "prompts")
    desc = prompts_item[2]
    assert "diff" in desc.lower() or "Diff" in desc or "对比" in desc
