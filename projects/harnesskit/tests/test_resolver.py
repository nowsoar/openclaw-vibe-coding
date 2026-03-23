"""Tests for Phase 1.6: asset reference resolution."""

from __future__ import annotations

from pathlib import Path

import pytest
from typer.testing import CliRunner

from harness_kit.cli import app
from harness_kit.config import init_harness
from harness_kit import prompt as pm
from harness_kit import schema as sm
from harness_kit import context as cm
from harness_kit import rule as rm
from harness_kit import resolver as res
from harness_kit.resolver import (
    AssetRef,
    DoctorReport,
    parse_ref,
    set_tag,
    get_tag_version,
    list_tags,
    resolve_ref,
    check_ref_exists,
    build_dependency_graph,
    detect_circular_refs,
    run_doctor,
)

runner = CliRunner()


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def workspace(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Initialised .harness workspace in tmp_path."""
    monkeypatch.chdir(tmp_path)
    init_harness(tmp_path)
    return tmp_path


@pytest.fixture()
def populated_workspace(workspace: Path) -> Path:
    """Workspace with one prompt, one schema, one context, one rule."""
    pm.save_prompt("code-reviewer", "You are a reviewer.", base=workspace)
    sm.save_schema(
        "read-file",
        parameters={"type": "object", "properties": {"path": {"type": "string"}}},
        base=workspace,
    )
    cm.save_context(
        "review-ctx",
        template="Review: {{ code }}",
        slots=[{"name": "code", "required": True}],
        base=workspace,
    )
    rm.save_rule(
        "no-hallucination",
        rule_type="hard",
        check_type="regex",
        pattern="(I think|maybe)",
        description="No guessing",
        base=workspace,
    )
    return workspace


# ---------------------------------------------------------------------------
# Unit tests — parse_ref
# ---------------------------------------------------------------------------


class TestParseRef:
    def test_bare_name_is_current(self) -> None:
        ref = parse_ref("code-reviewer")
        assert ref.name == "code-reviewer"
        assert ref.version is None
        assert ref.tag is None
        assert ref.ref_kind == "current"
        assert ref.raw == "code-reviewer"

    def test_semver_is_exact(self) -> None:
        ref = parse_ref("code-reviewer@v0.1.0")
        assert ref.name == "code-reviewer"
        assert ref.version == "v0.1.0"
        assert ref.tag is None
        assert ref.ref_kind == "exact"

    def test_non_semver_qualifier_is_tag(self) -> None:
        ref = parse_ref("code-reviewer@production")
        assert ref.name == "code-reviewer"
        assert ref.version is None
        assert ref.tag == "production"
        assert ref.ref_kind == "tag"

    def test_at_without_qualifier_is_tag(self) -> None:
        ref = parse_ref("my-prompt@staging")
        assert ref.ref_kind == "tag"
        assert ref.tag == "staging"

    def test_raw_field_preserved(self) -> None:
        raw = "my-schema@v2.3.4"
        assert parse_ref(raw).raw == raw

    def test_semver_pattern_v0_0_1(self) -> None:
        ref = parse_ref("x@v0.0.1")
        assert ref.ref_kind == "exact"
        assert ref.version == "v0.0.1"

    def test_large_semver(self) -> None:
        ref = parse_ref("x@v10.20.300")
        assert ref.ref_kind == "exact"

    def test_AssetRef_is_dataclass(self) -> None:
        ref = parse_ref("foo")
        assert isinstance(ref, AssetRef)


# ---------------------------------------------------------------------------
# Unit tests — tag helpers
# ---------------------------------------------------------------------------


class TestTagHelpers:
    def test_set_and_get_tag(self, populated_workspace: Path) -> None:
        set_tag("prompt", "code-reviewer", "production", "v0.0.1", base=populated_workspace)
        assert get_tag_version("prompt", "code-reviewer", "production", populated_workspace) == "v0.0.1"

    def test_get_tag_returns_none_when_missing(self, populated_workspace: Path) -> None:
        assert get_tag_version("prompt", "code-reviewer", "nonexistent", populated_workspace) is None

    def test_list_tags_empty_before_any_tag(self, populated_workspace: Path) -> None:
        assert list_tags("prompt", "code-reviewer", populated_workspace) == {}

    def test_list_tags_after_set(self, populated_workspace: Path) -> None:
        set_tag("prompt", "code-reviewer", "stable", "v0.0.1", populated_workspace)
        set_tag("prompt", "code-reviewer", "latest", "v0.0.1", populated_workspace)
        tags = list_tags("prompt", "code-reviewer", populated_workspace)
        assert tags == {"stable": "v0.0.1", "latest": "v0.0.1"}

    def test_overwrite_tag(self, populated_workspace: Path) -> None:
        set_tag("prompt", "code-reviewer", "prod", "v0.0.1", populated_workspace)
        # save a second version first
        pm.save_prompt("code-reviewer", "v2 content", base=populated_workspace)
        set_tag("prompt", "code-reviewer", "prod", "v0.0.2", populated_workspace)
        assert get_tag_version("prompt", "code-reviewer", "prod", populated_workspace) == "v0.0.2"

    def test_set_tag_on_rule_raises(self, populated_workspace: Path) -> None:
        with pytest.raises(ValueError, match="versioned"):
            set_tag("rule", "no-hallucination", "latest", "v0.0.1", populated_workspace)

    def test_tags_stored_under_tags_dir(self, populated_workspace: Path) -> None:
        set_tag("prompt", "code-reviewer", "alpha", "v0.0.1", populated_workspace)
        tags_file = (
            populated_workspace / ".harness" / "prompts" / "code-reviewer" / "_tags" / "alpha"
        )
        assert tags_file.exists()
        assert tags_file.read_text().strip() == "v0.0.1"


# ---------------------------------------------------------------------------
# Unit tests — resolve_ref / check_ref_exists
# ---------------------------------------------------------------------------


class TestResolveRef:
    def test_resolve_current_prompt(self, populated_workspace: Path) -> None:
        assert resolve_ref("code-reviewer", "prompt", populated_workspace) == "v0.0.1"

    def test_resolve_exact_prompt(self, populated_workspace: Path) -> None:
        assert resolve_ref("code-reviewer@v0.0.1", "prompt", populated_workspace) == "v0.0.1"

    def test_resolve_tag_prompt(self, populated_workspace: Path) -> None:
        set_tag("prompt", "code-reviewer", "stable", "v0.0.1", populated_workspace)
        assert resolve_ref("code-reviewer@stable", "prompt", populated_workspace) == "v0.0.1"

    def test_resolve_missing_returns_none(self, populated_workspace: Path) -> None:
        assert resolve_ref("nonexistent", "prompt", populated_workspace) is None

    def test_resolve_wrong_version_returns_none(self, populated_workspace: Path) -> None:
        assert resolve_ref("code-reviewer@v9.9.9", "prompt", populated_workspace) is None

    def test_resolve_broken_tag_returns_none(self, populated_workspace: Path) -> None:
        set_tag("prompt", "code-reviewer", "bad", "v9.9.9", populated_workspace)
        assert resolve_ref("code-reviewer@bad", "prompt", populated_workspace) is None

    def test_resolve_rule_exists(self, populated_workspace: Path) -> None:
        assert resolve_ref("no-hallucination", "rule", populated_workspace) == "current"

    def test_resolve_rule_missing(self, populated_workspace: Path) -> None:
        assert resolve_ref("ghost-rule", "rule", populated_workspace) is None

    def test_resolve_schema(self, populated_workspace: Path) -> None:
        assert resolve_ref("read-file", "schema", populated_workspace) == "v0.0.1"

    def test_resolve_context(self, populated_workspace: Path) -> None:
        assert resolve_ref("review-ctx", "context", populated_workspace) == "v0.0.1"

    def test_check_ref_exists_true(self, populated_workspace: Path) -> None:
        assert check_ref_exists("prompt", "code-reviewer", populated_workspace)

    def test_check_ref_exists_false(self, populated_workspace: Path) -> None:
        assert not check_ref_exists("prompt", "ghost", populated_workspace)

    def test_resolve_accepts_assetref(self, populated_workspace: Path) -> None:
        ref = parse_ref("code-reviewer@v0.0.1")
        assert resolve_ref(ref, "prompt", populated_workspace) == "v0.0.1"


# ---------------------------------------------------------------------------
# Unit tests — dependency graph and circular references
# ---------------------------------------------------------------------------


class TestDependencyGraph:
    def test_build_empty_graph(self) -> None:
        graph = build_dependency_graph([])
        assert graph == {}

    def test_build_graph_with_refs(self) -> None:
        nodes = [
            {"id": "prompt:a", "refs": ["schema:b"]},
            {"id": "schema:b", "refs": []},
        ]
        graph = build_dependency_graph(nodes)
        assert graph["prompt:a"] == ["schema:b"]
        assert graph["schema:b"] == []

    def test_build_graph_missing_refs_key(self) -> None:
        nodes = [{"id": "rule:x"}]
        graph = build_dependency_graph(nodes)
        assert graph["rule:x"] == []


class TestDetectCircularRefs:
    def test_no_cycles_empty(self) -> None:
        assert detect_circular_refs({}) == []

    def test_no_cycles_linear_chain(self) -> None:
        graph = {"a": ["b"], "b": ["c"], "c": []}
        assert detect_circular_refs(graph) == []

    def test_self_cycle(self) -> None:
        graph = {"a": ["a"]}
        cycles = detect_circular_refs(graph)
        assert len(cycles) >= 1
        assert "a" in cycles[0]

    def test_simple_cycle(self) -> None:
        graph = {"a": ["b"], "b": ["a"]}
        cycles = detect_circular_refs(graph)
        assert len(cycles) >= 1

    def test_triangle_cycle(self) -> None:
        graph = {"a": ["b"], "b": ["c"], "c": ["a"]}
        cycles = detect_circular_refs(graph)
        assert len(cycles) >= 1

    def test_no_cycle_fan_out(self) -> None:
        graph = {"root": ["x", "y"], "x": [], "y": []}
        assert detect_circular_refs(graph) == []

    def test_disconnected_with_one_cycle(self) -> None:
        graph = {"a": ["b"], "b": ["a"], "c": ["d"], "d": []}
        cycles = detect_circular_refs(graph)
        assert len(cycles) >= 1


# ---------------------------------------------------------------------------
# Unit tests — run_doctor
# ---------------------------------------------------------------------------


class TestRunDoctor:
    def test_empty_workspace_is_healthy(self, workspace: Path) -> None:
        report = run_doctor(workspace)
        assert isinstance(report, DoctorReport)
        assert report.assets == []
        assert report.cycles == []
        assert report.is_healthy

    def test_healthy_populated_workspace(self, populated_workspace: Path) -> None:
        report = run_doctor(populated_workspace)
        assert report.is_healthy
        assert len(report.assets) == 4  # 1 prompt + 1 schema + 1 context + 1 rule

    def test_all_assets_appear_as_unused(self, populated_workspace: Path) -> None:
        # No skills/harnesses exist → all primitives should be unreferenced
        report = run_doctor(populated_workspace)
        assert len(report.unused_assets) == 4

    def test_broken_current_pointer_detected(self, workspace: Path) -> None:
        # Create prompt dir with a corrupted _current file
        pm.save_prompt("broken", "content", base=workspace)
        current_file = workspace / ".harness" / "prompts" / "broken" / "_current"
        current_file.write_text("v9.9.9")

        report = run_doctor(workspace)
        broken = [a for a in report.assets if a.broken]
        assert len(broken) == 1
        assert "v9.9.9" in broken[0].issue  # type: ignore[operator]

    def test_broken_tag_detected(self, populated_workspace: Path) -> None:
        set_tag("prompt", "code-reviewer", "bad-tag", "v9.9.9", populated_workspace)
        report = run_doctor(populated_workspace)
        prompt_health = next(a for a in report.assets if a.name == "code-reviewer")
        assert "bad-tag" in prompt_health.broken_tags
        assert report.broken_count >= 1

    def test_valid_tag_not_in_broken_tags(self, populated_workspace: Path) -> None:
        set_tag("prompt", "code-reviewer", "stable", "v0.0.1", populated_workspace)
        report = run_doctor(populated_workspace)
        prompt_health = next(a for a in report.assets if a.name == "code-reviewer")
        assert prompt_health.broken_tags == []
        assert "stable" in prompt_health.tags

    def test_missing_current_file_detected(self, workspace: Path) -> None:
        pm.save_prompt("orphan", "hi", base=workspace)
        current_file = workspace / ".harness" / "prompts" / "orphan" / "_current"
        current_file.unlink()

        report = run_doctor(workspace)
        broken = [a for a in report.assets if a.broken]
        assert any("_current" in (b.issue or "") for b in broken)

    def test_no_cycles_in_phase1(self, populated_workspace: Path) -> None:
        report = run_doctor(populated_workspace)
        assert report.cycles == []

    def test_doctor_report_broken_count(self, populated_workspace: Path) -> None:
        # Healthy workspace has broken_count == 0
        report = run_doctor(populated_workspace)
        assert report.broken_count == 0

    def test_rule_with_invalid_yaml(self, workspace: Path) -> None:
        rm.save_rule("valid-rule", rule_type="soft", check_type="regex", pattern="x", base=workspace)
        # Corrupt the rule file
        rule_file = workspace / ".harness" / "rules" / "valid-rule.yaml"
        rule_file.write_text(": !!invalid: [broken")

        report = run_doctor(workspace)
        broken = [a for a in report.assets if a.broken and a.name == "valid-rule"]
        assert len(broken) == 1

    def test_unused_asset_names_correct(self, populated_workspace: Path) -> None:
        report = run_doctor(populated_workspace)
        unused_names = {name for _, name in report.unused_assets}
        assert "code-reviewer" in unused_names
        assert "read-file" in unused_names
        assert "review-ctx" in unused_names
        assert "no-hallucination" in unused_names


# ---------------------------------------------------------------------------
# CLI tests — doctor command
# ---------------------------------------------------------------------------


class TestDoctorCLI:
    def test_doctor_empty_workspace(self, workspace: Path) -> None:
        result = runner.invoke(app, ["doctor"])
        assert result.exit_code == 0
        assert "Doctor" in result.output

    def test_doctor_healthy_workspace(self, populated_workspace: Path) -> None:
        result = runner.invoke(app, ["doctor"])
        assert result.exit_code == 0
        assert "circular" in result.output.lower()

    def test_doctor_detects_broken_current(self, workspace: Path) -> None:
        pm.save_prompt("broken", "content", base=workspace)
        current_file = workspace / ".harness" / "prompts" / "broken" / "_current"
        current_file.write_text("v99.0.0")

        result = runner.invoke(app, ["doctor"])
        assert result.exit_code == 1
        assert "v99.0.0" in result.output

    def test_doctor_shows_unreferenced_assets(self, populated_workspace: Path) -> None:
        result = runner.invoke(app, ["doctor"])
        assert "unreferenced" in result.output.lower()

    def test_doctor_shows_valid_tags(self, populated_workspace: Path) -> None:
        set_tag("prompt", "code-reviewer", "stable", "v0.0.1", populated_workspace)
        result = runner.invoke(app, ["doctor"])
        assert "stable" in result.output

    def test_doctor_fails_on_broken_tag(self, populated_workspace: Path) -> None:
        set_tag("prompt", "code-reviewer", "broken-tag", "v9.9.9", populated_workspace)
        result = runner.invoke(app, ["doctor"])
        assert result.exit_code == 1
        assert "broken-tag" in result.output

    def test_doctor_summary_line(self, populated_workspace: Path) -> None:
        result = runner.invoke(app, ["doctor"])
        assert "Summary" in result.output
        assert "broken" in result.output.lower()

    def test_doctor_requires_init(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.chdir(tmp_path)
        result = runner.invoke(app, ["doctor"])
        assert result.exit_code == 1
        assert "init" in result.output.lower() or "initialized" in result.output.lower()
