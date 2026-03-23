"""Tests for Phase 1.5: rule constraint management."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml
from typer.testing import CliRunner

from harness_kit.cli import app
from harness_kit.config import init_harness
from harness_kit import rule as rm
from harness_kit.rule import CheckResult, check_rule, check_rule_by_name

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


# ---------------------------------------------------------------------------
# Unit tests — save_rule / load_rule
# ---------------------------------------------------------------------------


class TestSaveRule:
    def test_creates_yaml_file(self, workspace: Path) -> None:
        rm.save_rule(
            "no-hallucination",
            rule_type="hard",
            check_type="regex",
            pattern="(根据我所知|我猜测)",
            description="禁止推测性表述",
            fix_hint="只陈述确认的事实",
            base=workspace,
        )
        rf = workspace / ".harness" / "rules" / "no-hallucination.yaml"
        assert rf.exists()

    def test_yaml_contents(self, workspace: Path) -> None:
        rm.save_rule(
            "no-hallucination",
            rule_type="hard",
            check_type="regex",
            pattern="(根据我所知|我猜测)",
            description="禁止推测性表述",
            fix_hint="只陈述确认的事实",
            base=workspace,
        )
        data = yaml.safe_load(
            (workspace / ".harness" / "rules" / "no-hallucination.yaml").read_text()
        )
        assert data["name"] == "no-hallucination"
        assert data["type"] == "hard"
        assert data["check"]["type"] == "regex"
        assert data["check"]["pattern"] == "(根据我所知|我猜测)"
        assert data["fix_hint"] == "只陈述确认的事实"

    def test_returns_true_for_new_rule(self, workspace: Path) -> None:
        is_new = rm.save_rule(
            "test-rule", rule_type="soft", check_type="regex", pattern="x", base=workspace
        )
        assert is_new is True

    def test_returns_false_on_overwrite(self, workspace: Path) -> None:
        rm.save_rule("test-rule", rule_type="soft", check_type="regex", pattern="x", base=workspace)
        is_new = rm.save_rule(
            "test-rule", rule_type="hard", check_type="regex", pattern="y", base=workspace
        )
        assert is_new is False

    def test_invalid_rule_type_raises(self, workspace: Path) -> None:
        with pytest.raises(ValueError, match="rule_type"):
            rm.save_rule("r", rule_type="invalid", check_type="regex", pattern="x", base=workspace)

    def test_invalid_check_type_raises(self, workspace: Path) -> None:
        with pytest.raises(ValueError, match="check_type"):
            rm.save_rule("r", rule_type="hard", check_type="unknown", pattern="x", base=workspace)

    def test_soft_type_stored(self, workspace: Path) -> None:
        rm.save_rule("soft-rule", rule_type="soft", check_type="regex", pattern="foo", base=workspace)
        data = rm.load_rule("soft-rule", base=workspace)
        assert data["type"] == "soft"


# ---------------------------------------------------------------------------
# Unit tests — load_rule
# ---------------------------------------------------------------------------


class TestLoadRule:
    def test_load_existing_rule(self, workspace: Path) -> None:
        rm.save_rule("r1", rule_type="hard", check_type="regex", pattern="bad", base=workspace)
        data = rm.load_rule("r1", base=workspace)
        assert data["name"] == "r1"

    def test_load_missing_raises(self, workspace: Path) -> None:
        with pytest.raises(FileNotFoundError, match="r-missing"):
            rm.load_rule("r-missing", base=workspace)


# ---------------------------------------------------------------------------
# Unit tests — list_rules
# ---------------------------------------------------------------------------


class TestListRules:
    def test_empty_list(self, workspace: Path) -> None:
        assert rm.list_rules(base=workspace) == []

    def test_lists_all_rules(self, workspace: Path) -> None:
        rm.save_rule("a", rule_type="hard", check_type="regex", pattern="x", base=workspace)
        rm.save_rule("b", rule_type="soft", check_type="regex", pattern="y", base=workspace)
        rules = rm.list_rules(base=workspace)
        names = [r["name"] for r in rules]
        assert "a" in names
        assert "b" in names

    def test_sorted_by_name(self, workspace: Path) -> None:
        rm.save_rule("zebra", rule_type="hard", check_type="regex", pattern="z", base=workspace)
        rm.save_rule("apple", rule_type="hard", check_type="regex", pattern="a", base=workspace)
        names = [r["name"] for r in rm.list_rules(base=workspace)]
        assert names == sorted(names)


# ---------------------------------------------------------------------------
# Unit tests — delete_rule
# ---------------------------------------------------------------------------


class TestDeleteRule:
    def test_delete_existing_rule(self, workspace: Path) -> None:
        rm.save_rule("del-me", rule_type="hard", check_type="regex", pattern="x", base=workspace)
        rm.delete_rule("del-me", base=workspace)
        assert rm.list_rules(base=workspace) == []

    def test_delete_missing_raises(self, workspace: Path) -> None:
        with pytest.raises(FileNotFoundError):
            rm.delete_rule("nope", base=workspace)


# ---------------------------------------------------------------------------
# Unit tests — Rule Checker (check_rule)
# ---------------------------------------------------------------------------


class TestCheckRule:
    def _make_rule(self, pattern: str, rule_type: str = "hard", fix_hint: str = "") -> dict:
        return {
            "name": "test-rule",
            "type": rule_type,
            "check": {"type": "regex", "pattern": pattern},
            "fix_hint": fix_hint,
        }

    def test_regex_not_triggered(self) -> None:
        rule = self._make_rule(r"(bad|evil)")
        result = check_rule(rule, "This is fine.")
        assert result.triggered is False
        assert result.matches == []

    def test_regex_triggered_single_match(self) -> None:
        rule = self._make_rule(r"(bad|evil)")
        result = check_rule(rule, "This is bad content.")
        assert result.triggered is True
        assert "bad" in result.matches

    def test_regex_triggered_multiple_matches(self) -> None:
        rule = self._make_rule(r"根据我所知|我猜测")
        result = check_rule(rule, "根据我所知这是对的，我猜测如此")
        assert result.triggered is True
        assert len(result.matches) == 2

    def test_fix_hint_returned(self) -> None:
        rule = self._make_rule(r"bad", fix_hint="Remove bad words")
        result = check_rule(rule, "This is bad.")
        assert result.fix_hint == "Remove bad words"

    def test_rule_type_preserved(self) -> None:
        rule = self._make_rule(r"x", rule_type="soft")
        result = check_rule(rule, "x")
        assert result.rule_type == "soft"

    def test_hard_type_preserved(self) -> None:
        rule = self._make_rule(r"x", rule_type="hard")
        result = check_rule(rule, "x")
        assert result.rule_type == "hard"

    def test_invalid_regex_raises(self) -> None:
        rule = self._make_rule(r"(unclosed")
        with pytest.raises(ValueError, match="Invalid regex"):
            check_rule(rule, "test")

    def test_length_check_not_exceeded(self) -> None:
        rule = {
            "name": "len-rule",
            "type": "hard",
            "check": {"type": "length", "pattern": "100"},
            "fix_hint": "",
        }
        result = check_rule(rule, "short")
        assert result.triggered is False

    def test_length_check_exceeded(self) -> None:
        rule = {
            "name": "len-rule",
            "type": "hard",
            "check": {"type": "length", "pattern": "5"},
            "fix_hint": "Shorten the text",
        }
        result = check_rule(rule, "this is longer than five chars")
        assert result.triggered is True
        assert result.fix_hint == "Shorten the text"

    def test_check_rule_by_name(self, workspace: Path) -> None:
        rm.save_rule(
            "no-bad",
            rule_type="hard",
            check_type="regex",
            pattern="bad",
            fix_hint="Remove it",
            base=workspace,
        )
        result = check_rule_by_name("no-bad", "this is bad", base=workspace)
        assert result.triggered is True
        assert result.fix_hint == "Remove it"


# ---------------------------------------------------------------------------
# CLI tests — rule add
# ---------------------------------------------------------------------------


class TestCLIRuleAdd:
    def test_add_rule(self, workspace: Path) -> None:
        res = runner.invoke(
            app,
            ["rule", "add", "no-bad", "--type", "hard", "--pattern", "bad"],
        )
        assert res.exit_code == 0
        assert "Created" in res.output
        assert "no-bad" in res.output

    def test_update_rule(self, workspace: Path) -> None:
        runner.invoke(app, ["rule", "add", "r1", "--type", "hard", "--pattern", "x"])
        res = runner.invoke(app, ["rule", "add", "r1", "--type", "soft", "--pattern", "y"])
        assert res.exit_code == 0
        assert "Updated" in res.output

    def test_invalid_type_fails(self, workspace: Path) -> None:
        res = runner.invoke(
            app,
            ["rule", "add", "r1", "--type", "bad-type", "--pattern", "x"],
        )
        assert res.exit_code != 0

    def test_requires_init(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.chdir(tmp_path)
        res = runner.invoke(app, ["rule", "add", "r1", "--type", "hard", "--pattern", "x"])
        assert res.exit_code != 0


# ---------------------------------------------------------------------------
# CLI tests — rule list
# ---------------------------------------------------------------------------


class TestCLIRuleList:
    def test_empty(self, workspace: Path) -> None:
        res = runner.invoke(app, ["rule", "list"])
        assert res.exit_code == 0
        assert "No rules" in res.output

    def test_shows_rules(self, workspace: Path) -> None:
        runner.invoke(app, ["rule", "add", "rule-a", "--type", "hard", "--pattern", "x"])
        res = runner.invoke(app, ["rule", "list"])
        assert res.exit_code == 0
        assert "rule-a" in res.output


# ---------------------------------------------------------------------------
# CLI tests — rule show
# ---------------------------------------------------------------------------


class TestCLIRuleShow:
    def test_show_existing(self, workspace: Path) -> None:
        runner.invoke(
            app,
            ["rule", "add", "r1", "--type", "hard", "--pattern", "bad", "--fix-hint", "Fix it"],
        )
        res = runner.invoke(app, ["rule", "show", "r1"])
        assert res.exit_code == 0
        assert "r1" in res.output
        assert "hard" in res.output
        assert "bad" in res.output
        assert "Fix it" in res.output

    def test_show_missing(self, workspace: Path) -> None:
        res = runner.invoke(app, ["rule", "show", "nope"])
        assert res.exit_code != 0


# ---------------------------------------------------------------------------
# CLI tests — rule test
# ---------------------------------------------------------------------------


class TestCLIRuleTest:
    def test_not_triggered(self, workspace: Path) -> None:
        runner.invoke(app, ["rule", "add", "no-bad", "--type", "hard", "--pattern", "bad"])
        res = runner.invoke(app, ["rule", "test", "no-bad", "--input", "this is fine"])
        assert res.exit_code == 0
        assert "PASSED" in res.output

    def test_triggered(self, workspace: Path) -> None:
        runner.invoke(app, ["rule", "add", "no-bad", "--type", "hard", "--pattern", "bad"])
        res = runner.invoke(app, ["rule", "test", "no-bad", "--input", "this is bad"])
        assert res.exit_code == 0
        assert "TRIGGERED" in res.output

    def test_shows_fix_hint(self, workspace: Path) -> None:
        runner.invoke(
            app,
            [
                "rule", "add", "no-bad", "--type", "hard",
                "--pattern", "bad", "--fix-hint", "Remove bad words",
            ],
        )
        res = runner.invoke(app, ["rule", "test", "no-bad", "--input", "bad content"])
        assert "Remove bad words" in res.output

    def test_missing_rule(self, workspace: Path) -> None:
        res = runner.invoke(app, ["rule", "test", "nope", "--input", "hello"])
        assert res.exit_code != 0

    def test_hard_vs_soft_type_shown(self, workspace: Path) -> None:
        runner.invoke(app, ["rule", "add", "soft-r", "--type", "soft", "--pattern", "x"])
        res = runner.invoke(app, ["rule", "test", "soft-r", "--input", "x is here"])
        assert "soft" in res.output


# ---------------------------------------------------------------------------
# CLI tests — rule delete
# ---------------------------------------------------------------------------


class TestCLIRuleDelete:
    def test_delete_with_yes(self, workspace: Path) -> None:
        runner.invoke(app, ["rule", "add", "del-me", "--type", "hard", "--pattern", "x"])
        res = runner.invoke(app, ["rule", "delete", "del-me", "--yes"])
        assert res.exit_code == 0
        assert "Deleted" in res.output
        # Confirm it's gone
        res2 = runner.invoke(app, ["rule", "show", "del-me"])
        assert res2.exit_code != 0

    def test_delete_missing(self, workspace: Path) -> None:
        res = runner.invoke(app, ["rule", "delete", "nope", "--yes"])
        assert res.exit_code != 0
