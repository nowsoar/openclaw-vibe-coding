"""
Blueprint deterministic node executor — Phase 4.3.

Supports:
  - Shell command execution via subprocess
  - stdout/stderr capture and timeout control
  - on_fail: stop / continue / goto:<step_id>
  - Variable interpolation: {{inputs.x}}, {{steps.y.output}}, {{env.VAR}}
  - Python callable steps (future extension, type="python")
  - dry_run mode (renders commands without executing)
"""

from __future__ import annotations

import os
import re
import subprocess
import time
from dataclasses import dataclass, field
from typing import Any, Optional


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass
class StepResult:
    """Result of a single blueprint step execution."""

    step_id: str
    step_name: str
    step_type: str
    status: str  # "success" | "failed" | "timeout" | "skipped" | "dry_run"
    output: str = ""
    stderr: str = ""
    exit_code: Optional[int] = None
    duration: float = 0.0
    error: Optional[str] = None


@dataclass
class BlueprintRunResult:
    """Aggregate result of running an entire blueprint."""

    blueprint_name: str
    blueprint_version: str
    status: str  # "success" | "failed" | "stopped" | "dry_run"
    steps: list[StepResult] = field(default_factory=list)
    outputs: dict[str, str] = field(default_factory=dict)
    duration: float = 0.0
    stop_reason: Optional[str] = None


# ---------------------------------------------------------------------------
# Variable interpolation
# ---------------------------------------------------------------------------

_VAR_RE = re.compile(r"\{\{\s*([^}]+?)\s*\}\}")


def interpolate_variables(template: str, context: dict[str, Any]) -> str:
    """Replace ``{{path.to.value}}`` placeholders with values from *context*.

    Supported patterns:
    - ``{{inputs.name}}``          — blueprint input variable
    - ``{{steps.id.output}}``      — previous step's stdout
    - ``{{steps.id.stderr}}``      — previous step's stderr
    - ``{{steps.id.exit_code}}``   — previous step's exit code
    - ``{{steps.id.status}}``      — previous step's status string
    - ``{{env.VAR_NAME}}``         — OS environment variable

    Unknown paths are left as-is.
    """

    def _replace(match: re.Match) -> str:
        path = match.group(1).strip()
        parts = path.split(".")
        try:
            # env.VAR shortcut
            if parts[0] == "env" and len(parts) == 2:
                return os.environ.get(parts[1], match.group(0))

            node: Any = context
            for part in parts:
                if isinstance(node, dict):
                    node = node[part]
                else:
                    node = getattr(node, part)
            return str(node) if node is not None else ""
        except (KeyError, AttributeError, TypeError):
            return match.group(0)  # leave unchanged

    return _VAR_RE.sub(_replace, str(template))


# ---------------------------------------------------------------------------
# Deterministic step execution
# ---------------------------------------------------------------------------


def run_deterministic_step(
    step: dict[str, Any],
    context: dict[str, Any],
) -> StepResult:
    """Execute a deterministic (shell command) step.

    Interpolates ``{{...}}`` variables in the ``run`` field, spawns the
    command in a shell, captures stdout/stderr, enforces *timeout*, and
    returns a :class:`StepResult`.
    """
    step_id = step["id"]
    step_name = step.get("name", step_id)
    timeout: int = int(step.get("timeout", 60))

    raw_cmd: str = step.get("run", "")
    run_cmd = interpolate_variables(raw_cmd, context)

    t0 = time.perf_counter()
    try:
        proc = subprocess.run(
            run_cmd,
            shell=True,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        duration = time.perf_counter() - t0
        status = "success" if proc.returncode == 0 else "failed"
        return StepResult(
            step_id=step_id,
            step_name=step_name,
            step_type="deterministic",
            status=status,
            output=proc.stdout,
            stderr=proc.stderr,
            exit_code=proc.returncode,
            duration=duration,
        )
    except subprocess.TimeoutExpired:
        duration = time.perf_counter() - t0
        return StepResult(
            step_id=step_id,
            step_name=step_name,
            step_type="deterministic",
            status="timeout",
            output="",
            stderr=f"Command timed out after {timeout}s",
            exit_code=None,
            duration=duration,
            error=f"Timeout after {timeout}s",
        )
    except Exception as exc:  # noqa: BLE001
        duration = time.perf_counter() - t0
        return StepResult(
            step_id=step_id,
            step_name=step_name,
            step_type="deterministic",
            status="failed",
            output="",
            stderr=str(exc),
            exit_code=-1,
            duration=duration,
            error=str(exc),
        )


# ---------------------------------------------------------------------------
# Blueprint executor
# ---------------------------------------------------------------------------


def _make_skipped(step: dict[str, Any], reason: str) -> StepResult:
    return StepResult(
        step_id=step["id"],
        step_name=step.get("name", step["id"]),
        step_type=step.get("type", "deterministic"),
        status="skipped",
        output=reason,
    )


def execute_blueprint(
    blueprint_data: dict[str, Any],
    inputs: dict[str, str],
    *,
    dry_run: bool = False,
    start_step: Optional[str] = None,
) -> BlueprintRunResult:
    """Execute all steps in a blueprint.

    Args:
        blueprint_data: Parsed blueprint YAML dict (must include ``steps``).
        inputs:         Key/value pairs matching the blueprint's ``inputs`` list.
        dry_run:        When *True*, render commands but do not execute them.
        start_step:     Step ID to start execution from (skips earlier steps).

    Notes:
        - Agentic steps are logged as ``skipped`` with a note until Phase 4.4.
        - Python function steps (``type: python``) are reserved for a future
          extension; they are skipped with a note in this phase.
    """
    name: str = blueprint_data.get("name", "")
    version: str = blueprint_data.get("version", "")
    steps: list[dict] = blueprint_data.get("steps") or []
    outputs_def: dict[str, str] = blueprint_data.get("outputs") or {}

    # Merge declared input defaults with provided values
    merged_inputs: dict[str, str] = {}
    for inp_def in blueprint_data.get("inputs") or []:
        inp_name = inp_def.get("name", "")
        if inp_name in inputs:
            merged_inputs[inp_name] = inputs[inp_name]
        elif inp_def.get("default") is not None:
            merged_inputs[inp_name] = str(inp_def["default"])
        elif inp_def.get("required", True):
            merged_inputs[inp_name] = inputs.get(inp_name, "")
        else:
            merged_inputs[inp_name] = ""
    # Also include any extra inputs not declared
    merged_inputs.update({k: v for k, v in inputs.items() if k not in merged_inputs})

    # Execution context — updated as steps complete
    context: dict[str, Any] = {
        "inputs": merged_inputs,
        "steps": {},
    }

    # Build step-id → index lookup (for goto resolution)
    step_id_to_idx: dict[str, int] = {s["id"]: i for i, s in enumerate(steps)}

    step_results: list[StepResult] = []

    # Determine starting index
    i = 0
    if start_step is not None:
        if start_step in step_id_to_idx:
            i = step_id_to_idx[start_step]
            # Mark skipped steps before start
            for s in steps[:i]:
                result = _make_skipped(s, f"Skipped: --step {start_step} specified")
                step_results.append(result)
                context["steps"][s["id"]] = {
                    "output": "",
                    "stderr": "",
                    "exit_code": None,
                    "status": "skipped",
                }
        else:
            return BlueprintRunResult(
                blueprint_name=name,
                blueprint_version=version,
                status="stopped",
                duration=0.0,
                stop_reason=f"Unknown --step target: '{start_step}'",
            )

    t0_global = time.perf_counter()
    visited_gotos: dict[str, int] = {}  # guard against infinite goto loops

    while i < len(steps):
        step = steps[i]
        step_id = step["id"]
        step_type = step.get("type", "deterministic")

        # --- Execute step based on type ---
        if dry_run:
            raw_cmd = step.get("run", "")
            rendered = interpolate_variables(raw_cmd, context) if raw_cmd else ""
            if step_type == "deterministic":
                note = f"[dry-run] would execute: {rendered}" if rendered else "[dry-run] (no run command)"
            elif step_type == "agentic":
                harness_ref = step.get("harness") or step.get("skill") or "?"
                note = f"[dry-run] would call agentic: {harness_ref}"
            else:
                note = f"[dry-run] unknown step type: {step_type}"
            result = StepResult(
                step_id=step_id,
                step_name=step.get("name", step_id),
                step_type=step_type,
                status="dry_run",
                output=note,
                duration=0.0,
            )
        elif step_type == "deterministic":
            result = run_deterministic_step(step, context)
        elif step_type == "agentic":
            # Phase 4.4 will implement agentic execution
            result = StepResult(
                step_id=step_id,
                step_name=step.get("name", step_id),
                step_type="agentic",
                status="skipped",
                output="[agentic steps require Phase 4.4 — skipped]",
                duration=0.0,
            )
        else:
            result = StepResult(
                step_id=step_id,
                step_name=step.get("name", step_id),
                step_type=step_type,
                status="skipped",
                output=f"Unknown step type '{step_type}' — skipped",
                duration=0.0,
            )

        step_results.append(result)

        # Update context so subsequent steps can reference this step's output
        context["steps"][step_id] = {
            "output": result.output,
            "stderr": result.stderr,
            "exit_code": result.exit_code,
            "status": result.status,
        }

        # --- on_fail handling (only when a step actually failed/timed out) ---
        if result.status in ("failed", "timeout") and not dry_run:
            on_fail: str = step.get("on_fail", "stop")

            if on_fail == "stop":
                # Mark all remaining steps as skipped, then abort
                for remaining in steps[i + 1 :]:
                    skipped = _make_skipped(remaining, "Skipped: previous step failed (on_fail=stop)")
                    step_results.append(skipped)
                    context["steps"][remaining["id"]] = {
                        "output": "",
                        "stderr": "",
                        "exit_code": None,
                        "status": "skipped",
                    }
                duration = time.perf_counter() - t0_global
                resolved_outputs = _resolve_outputs(outputs_def, context)
                return BlueprintRunResult(
                    blueprint_name=name,
                    blueprint_version=version,
                    status="stopped",
                    steps=step_results,
                    outputs=resolved_outputs,
                    duration=duration,
                    stop_reason=(
                        f"Step '{step_id}' failed"
                        + (f" (exit_code={result.exit_code})" if result.exit_code is not None else "")
                        + (f": {result.error}" if result.error else "")
                    ),
                )

            elif on_fail == "continue":
                i += 1
                continue

            elif on_fail.startswith("goto:"):
                target_id = on_fail[5:]
                # Guard against infinite loops
                loop_key = f"{step_id}->{target_id}"
                visited_gotos[loop_key] = visited_gotos.get(loop_key, 0) + 1
                if visited_gotos[loop_key] > 10:
                    duration = time.perf_counter() - t0_global
                    return BlueprintRunResult(
                        blueprint_name=name,
                        blueprint_version=version,
                        status="stopped",
                        steps=step_results,
                        outputs={},
                        duration=duration,
                        stop_reason=f"Infinite goto loop detected: {step_id} → {target_id}",
                    )
                if target_id in step_id_to_idx:
                    i = step_id_to_idx[target_id]
                    continue
                else:
                    duration = time.perf_counter() - t0_global
                    return BlueprintRunResult(
                        blueprint_name=name,
                        blueprint_version=version,
                        status="stopped",
                        steps=step_results,
                        outputs={},
                        duration=duration,
                        stop_reason=f"Invalid goto target: '{target_id}'",
                    )

        i += 1

    # All steps done — resolve outputs and determine final status
    resolved_outputs = _resolve_outputs(outputs_def, context)
    duration = time.perf_counter() - t0_global

    any_failed = any(
        r.status in ("failed", "timeout")
        for r in step_results
        if r.step_type == "deterministic"
    )
    if dry_run:
        overall = "dry_run"
    elif any_failed:
        overall = "failed"
    else:
        overall = "success"

    return BlueprintRunResult(
        blueprint_name=name,
        blueprint_version=version,
        status=overall,
        steps=step_results,
        outputs=resolved_outputs,
        duration=duration,
    )


def _resolve_outputs(
    outputs_def: dict[str, str],
    context: dict[str, Any],
) -> dict[str, str]:
    """Interpolate all output expressions against the execution context."""
    resolved: dict[str, str] = {}
    for k, v in outputs_def.items():
        resolved[k] = interpolate_variables(str(v), context)
    return resolved
