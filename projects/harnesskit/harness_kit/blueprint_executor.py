"""
Blueprint node executor — Phase 4.3 (deterministic) + Phase 4.4 (agentic)
                         + Phase 4.5 (variable passing system with filters).

Supports:
  - Shell command execution via subprocess
  - stdout/stderr capture and timeout control
  - on_fail: stop / continue / goto:<step_id>
  - Variable interpolation: {{inputs.x}}, {{steps.y.output}}, {{env.VAR}}
  - Pipe filters: {{steps.x.output | truncate:100}}, {{steps.x.output | json}}
  - Agentic steps: call Skill or Harness via LLM with retries and timeout
  - dry_run mode (renders commands without executing)
"""

from __future__ import annotations

import concurrent.futures
import json
import os
import re
import subprocess
import time
from dataclasses import dataclass, field
from pathlib import Path
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

# ---------------------------------------------------------------------------
# Filter application
# ---------------------------------------------------------------------------

_TRUNCATE_RE = re.compile(r"^truncate:(\d+)$")


def _apply_filter(value: str, filter_expr: str) -> str:
    """Apply a single named filter to *value*.

    Supported filters:
    - ``truncate:N``   — keep first N characters, append ``...`` if truncated
    - ``json``         — JSON-encode the value (strings are double-quoted;
                         valid JSON is re-serialised for consistency)
    - ``upper``        — convert to upper-case
    - ``lower``        — convert to lower-case
    - ``strip``        — strip leading/trailing whitespace

    Unknown filters are silently ignored (value is returned unchanged).
    """
    filter_expr = filter_expr.strip()

    if filter_expr == "json":
        try:
            parsed = json.loads(value)
            return json.dumps(parsed, ensure_ascii=False)
        except (json.JSONDecodeError, ValueError):
            return json.dumps(value, ensure_ascii=False)

    m = _TRUNCATE_RE.match(filter_expr)
    if m:
        n = int(m.group(1))
        if len(value) > n:
            return value[:n] + "..."
        return value

    if filter_expr == "upper":
        return value.upper()

    if filter_expr == "lower":
        return value.lower()

    if filter_expr == "strip":
        return value.strip()

    # Unknown filter — leave unchanged
    return value


def interpolate_variables(template: str, context: dict[str, Any]) -> str:
    """Replace ``{{path.to.value}}`` placeholders with values from *context*.

    Supported path patterns:
    - ``{{inputs.name}}``          — blueprint input variable
    - ``{{steps.id.output}}``      — previous step's stdout
    - ``{{steps.id.stderr}}``      — previous step's stderr
    - ``{{steps.id.exit_code}}``   — previous step's exit code
    - ``{{steps.id.status}}``      — previous step's status string
    - ``{{env.VAR_NAME}}``         — OS environment variable

    Pipe filters (Phase 4.5):
    - ``{{steps.id.output | truncate:100}}``  — truncate to 100 chars
    - ``{{steps.id.output | json}}``          — JSON-encode the value
    - ``{{steps.id.output | upper}}``         — upper-case
    - ``{{steps.id.output | lower}}``         — lower-case
    - ``{{steps.id.output | strip}}``         — strip whitespace
    - Filters can be chained: ``{{x | truncate:10 | json}}``

    Unknown paths are left as-is.
    """

    def _replace(match: re.Match) -> str:
        raw = match.group(1).strip()
        # Split into path and zero or more filter expressions
        parts_pipe = [p.strip() for p in raw.split("|")]
        path = parts_pipe[0]
        filters = parts_pipe[1:]

        path_parts = path.split(".")
        try:
            # env.VAR shortcut
            if path_parts[0] == "env" and len(path_parts) == 2:
                value = os.environ.get(path_parts[1], None)
                if value is None:
                    return match.group(0)  # leave unchanged
            else:
                node: Any = context
                for part in path_parts:
                    if isinstance(node, dict):
                        node = node[part]
                    else:
                        node = getattr(node, part)
                value = str(node) if node is not None else ""
        except (KeyError, AttributeError, TypeError):
            return match.group(0)  # leave unchanged

        for f in filters:
            value = _apply_filter(value, f)

        return value

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
# Agentic step execution
# ---------------------------------------------------------------------------


def run_agentic_step(
    step: dict[str, Any],
    context: dict[str, Any],
    base: Optional[Path] = None,
) -> StepResult:
    """Execute an agentic step by calling a Skill or Harness via LLM.

    Reads ``step["skill"]`` or ``step["skill"]`` to identify the target, interpolates
    ``step["inputs"]`` from *context*, calls the LLM, and returns a
    :class:`StepResult` whose ``output`` is the raw LLM response text.

    Retry behaviour is controlled by ``step["max_retries"]`` (default 0) with
    exponential back-off.  Hard timeout is enforced via a thread-pool future.
    """
    from harness_kit import harness as harness_mod
    from harness_kit import skill as skill_mod
    from harness_kit.blueprint import _parse_asset_ref
    from harness_kit.call_logger import log_call
    from harness_kit.config import read_config
    from harness_kit.llm import LLMConfig, build_messages, call_llm

    step_id: str = step["id"]
    step_name: str = step.get("name", step_id)
    timeout: int = int(step.get("timeout", 120))
    max_retries: int = int(step.get("max_retries", 0))

    # Interpolate step inputs from context
    raw_inputs: dict[str, Any] = step.get("inputs") or {}
    vars_: dict[str, str] = {k: interpolate_variables(str(v), context) for k, v in raw_inputs.items()}

    t0 = time.perf_counter()

    try:
        harness_ref: Optional[str] = step.get("harness")
        skill_ref: Optional[str] = step.get("skill")
        model_overrides: dict[str, Any] = {}

        if harness_ref:
            h_name, h_version = _parse_asset_ref(harness_ref)
            harness_data = harness_mod.load_harness(h_name, h_version, base)
            # Extract model overrides from harness model config
            model_cfg: dict[str, Any] = harness_data.get("model") or {}
            model_overrides = {
                k: v
                for k, v in {
                    "model": model_cfg.get("name"),
                    "temperature": model_cfg.get("temperature"),
                    "max_tokens": model_cfg.get("max_tokens"),
                }.items()
                if v is not None
            }
            # Use the first skill defined in the harness
            skills_list: list[str] = harness_data.get("skills") or []
            if not skills_list:
                raise ValueError(f"Harness '{harness_ref}' has no skills defined.")
            s_name, s_version = _parse_asset_ref(str(skills_list[0]))
            skill_label = f"{h_name}:{s_name}"
        elif skill_ref:
            s_name, s_version = _parse_asset_ref(skill_ref)
            skill_label = s_name
        else:
            raise ValueError("Agentic step must have either 'harness' or 'skill' field.")

        skill_data = skill_mod.load_skill(s_name, s_version, base)
        rendered = skill_mod.render_skill_prompt(s_name, s_version, base)

        try:
            global_cfg = read_config(base)
        except Exception:
            global_cfg = {}

        llm_config = LLMConfig.from_harness_config(global_cfg, model_overrides)
        messages = build_messages(skill_data, rendered, vars=vars_)

        # Execute with retries and per-attempt timeout
        last_exc: Optional[Exception] = None
        response = None

        for attempt in range(max_retries + 1):
            try:
                with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
                    future = executor.submit(call_llm, messages, llm_config, False)
                    response = future.result(timeout=timeout)
                break  # success
            except concurrent.futures.TimeoutError:
                last_exc = TimeoutError(f"LLM call timed out after {timeout}s")
                if attempt < max_retries:
                    time.sleep(2**attempt)
            except Exception as exc:  # noqa: BLE001
                last_exc = exc
                # Retry only on transient errors
                err_lower = str(exc).lower()
                is_retryable = any(
                    kw in err_lower
                    for kw in ("rate limit", "timeout", "503", "502", "429", "connection")
                )
                if is_retryable and attempt < max_retries:
                    time.sleep(2**attempt)
                else:
                    break

        duration = time.perf_counter() - t0

        if response is None:
            # All attempts exhausted
            err_msg = str(last_exc) if last_exc else "Unknown error"
            status = "timeout" if isinstance(last_exc, TimeoutError) else "failed"
            log_call(
                skill=skill_label,
                model=llm_config.model,
                input_tokens=0,
                output_tokens=0,
                duration=duration,
                status=status,
                error=err_msg,
                inputs=vars_,
                output=None,
                base=base,
            )
            return StepResult(
                step_id=step_id,
                step_name=step_name,
                step_type="agentic",
                status=status,
                output="",
                stderr=err_msg,
                duration=duration,
                error=err_msg,
            )

        log_call(
            skill=skill_label,
            model=response.model,
            input_tokens=response.input_tokens,
            output_tokens=response.output_tokens,
            duration=duration,
            status="success",
            inputs=vars_,
            output=response.content,
            base=base,
        )
        return StepResult(
            step_id=step_id,
            step_name=step_name,
            step_type="agentic",
            status="success",
            output=response.content,
            duration=duration,
        )

    except Exception as exc:  # noqa: BLE001
        duration = time.perf_counter() - t0
        return StepResult(
            step_id=step_id,
            step_name=step_name,
            step_type="agentic",
            status="failed",
            output="",
            stderr=str(exc),
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
    base: Optional[Path] = None,
) -> BlueprintRunResult:
    """Execute all steps in a blueprint.

    Args:
        blueprint_data: Parsed blueprint YAML dict (must include ``steps``).
        inputs:         Key/value pairs matching the blueprint's ``inputs`` list.
        dry_run:        When *True*, render commands but do not execute them.
        start_step:     Step ID to start execution from (skips earlier steps).
        base:           Base directory for resolving .harness/ assets (defaults to cwd).
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
            result = run_agentic_step(step, context, base)
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
