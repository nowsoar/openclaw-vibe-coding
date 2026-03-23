"""Rule constraint asset management — data model, storage (YAML), and checker."""

from __future__ import annotations

import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml

from harness_kit.config import harness_dir


# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------


def rules_dir(base: Path | None = None) -> Path:
    return harness_dir(base) / "rules"


def _rule_file(name: str, base: Path | None = None) -> Path:
    return rules_dir(base) / f"{name}.yaml"


# ---------------------------------------------------------------------------
# CRUD
# ---------------------------------------------------------------------------


def save_rule(
    name: str,
    rule_type: str,
    check_type: str,
    pattern: str,
    description: str = "",
    fix_hint: str = "",
    base: Path | None = None,
) -> bool:
    """Save (or overwrite) a rule. Returns True if newly created, False if updated.

    Parameters
    ----------
    rule_type:  'hard' or 'soft'
    check_type: 'regex' or 'length'
    pattern:    regex pattern string (for regex type) or max-length integer string (for length)
    """
    if rule_type not in ("hard", "soft"):
        raise ValueError(f"rule_type must be 'hard' or 'soft', got: {rule_type!r}")
    if check_type not in ("regex", "length"):
        raise ValueError(f"check_type must be 'regex' or 'length', got: {check_type!r}")

    rd = rules_dir(base)
    rd.mkdir(parents=True, exist_ok=True)

    rf = _rule_file(name, base)
    is_new = not rf.exists()

    data: dict[str, Any] = {
        "name": name,
        "type": rule_type,
        "description": description,
        "created_at": datetime.now(tz=timezone.utc).isoformat(),
        "check": {
            "type": check_type,
            "pattern": pattern,
        },
        "fix_hint": fix_hint,
    }

    with rf.open("w", encoding="utf-8") as f:
        yaml.dump(data, f, allow_unicode=True, default_flow_style=False, sort_keys=False)

    return is_new


def load_rule(name: str, base: Path | None = None) -> dict[str, Any]:
    """Load a rule by name. Raises FileNotFoundError if not found."""
    rf = _rule_file(name, base)
    if not rf.exists():
        raise FileNotFoundError(f"Rule '{name}' not found.")
    with rf.open("r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def list_rules(base: Path | None = None) -> list[dict[str, Any]]:
    """Return metadata for every rule, sorted by name."""
    rd = rules_dir(base)
    if not rd.exists():
        return []
    result = []
    for f in sorted(rd.glob("*.yaml")):
        try:
            result.append(yaml.safe_load(f.read_text(encoding="utf-8")))
        except Exception:
            pass
    return result


def delete_rule(name: str, base: Path | None = None) -> None:
    """Delete a rule. Raises FileNotFoundError if not found."""
    rf = _rule_file(name, base)
    if not rf.exists():
        raise FileNotFoundError(f"Rule '{name}' not found.")
    rf.unlink()


# ---------------------------------------------------------------------------
# Rule Checker
# ---------------------------------------------------------------------------


class CheckResult:
    """Result from running a rule check against input text."""

    def __init__(
        self,
        triggered: bool,
        rule_name: str,
        rule_type: str,
        matches: list[str],
        fix_hint: str,
    ) -> None:
        self.triggered = triggered
        self.rule_name = rule_name
        self.rule_type = rule_type
        self.matches = matches
        self.fix_hint = fix_hint

    def __repr__(self) -> str:
        return (
            f"CheckResult(triggered={self.triggered}, rule={self.rule_name!r}, "
            f"matches={self.matches!r})"
        )


def check_rule(rule: dict[str, Any], input_text: str) -> CheckResult:
    """Run a single rule against input_text. Returns a CheckResult.

    Supports check types:
      - regex  : triggers when the pattern matches anywhere in the input
      - length : triggers when len(input_text) > int(pattern)
    """
    name = rule.get("name", "")
    rule_type = rule.get("type", "hard")
    fix_hint = rule.get("fix_hint", "")
    check = rule.get("check") or {}
    check_type = check.get("type", "regex")
    pattern = check.get("pattern", "")

    if check_type == "regex":
        try:
            compiled = re.compile(pattern)
        except re.error as exc:
            raise ValueError(f"Invalid regex pattern in rule '{name}': {exc}") from exc
        found = compiled.findall(input_text)
        triggered = bool(found)
        matches = [str(m) for m in found]
    elif check_type == "length":
        try:
            max_len = int(pattern)
        except (ValueError, TypeError):
            raise ValueError(
                f"Rule '{name}' has check.type=length but pattern is not an integer: {pattern!r}"
            )
        exceeded = len(input_text) > max_len
        triggered = exceeded
        matches = [str(len(input_text))] if exceeded else []
    else:
        raise ValueError(f"Unsupported check type: {check_type!r}")

    return CheckResult(
        triggered=triggered,
        rule_name=name,
        rule_type=rule_type,
        matches=matches,
        fix_hint=fix_hint,
    )


def check_rule_by_name(
    name: str,
    input_text: str,
    base: Path | None = None,
) -> CheckResult:
    """Load a rule by name and run it against input_text."""
    rule = load_rule(name, base)
    return check_rule(rule, input_text)
