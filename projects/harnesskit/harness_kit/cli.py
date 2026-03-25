"""HarnessKit CLI entry point."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Optional

import typer
import yaml
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn, TimeElapsedColumn
from rich.table import Table
from rich.text import Text

from harness_kit.config import (
    SUBDIRS,
    harness_dir,
    init_harness,
    is_initialized,
    read_config,
)
from harness_kit import prompt as _prompt_mod
from harness_kit import schema as _schema_mod
from harness_kit import context as _context_mod
from harness_kit import rule as _rule_mod
from harness_kit import resolver as _resolver_mod
from harness_kit import skill as _skill_mod
from harness_kit import harness as _harness_mod
from harness_kit import call_logger as _call_logger_mod
from harness_kit import memory as _memory_mod
from harness_kit import agent as _agent_mod
from harness_kit import blueprint as _blueprint_mod
from harness_kit import eval as _eval_mod
from harness_kit import cost_tracker as _cost_tracker_mod
from harness_kit import stats as _stats_mod
from harness_kit.llm import LLMConfig, build_messages, call_llm

app = typer.Typer(
    name="harnesskit",
    help="Local AI Harness engineering toolkit.",
    add_completion=False,
    no_args_is_help=True,
)
console = Console()

# ---------------------------------------------------------------------------
# prompt sub-app
# ---------------------------------------------------------------------------

prompt_app = typer.Typer(help="Manage prompt assets.", no_args_is_help=True)
app.add_typer(prompt_app, name="prompt")

# ---------------------------------------------------------------------------
# schema sub-app
# ---------------------------------------------------------------------------

schema_app = typer.Typer(help="Manage schema assets.", no_args_is_help=True)
app.add_typer(schema_app, name="schema")

# ---------------------------------------------------------------------------
# context sub-app
# ---------------------------------------------------------------------------

context_app = typer.Typer(help="Manage context template assets.", no_args_is_help=True)
app.add_typer(context_app, name="context")

# ---------------------------------------------------------------------------
# rule sub-app
# ---------------------------------------------------------------------------

rule_app = typer.Typer(help="Manage rule constraints.", no_args_is_help=True)
app.add_typer(rule_app, name="rule")

# ---------------------------------------------------------------------------
# skill sub-app
# ---------------------------------------------------------------------------

skill_app = typer.Typer(help="Manage skill assets.", no_args_is_help=True)
app.add_typer(skill_app, name="skill")

# ---------------------------------------------------------------------------
# logs sub-app
# ---------------------------------------------------------------------------

logs_app = typer.Typer(help="View LLM call logs.", no_args_is_help=True)
app.add_typer(logs_app, name="logs")

# ---------------------------------------------------------------------------
# harness sub-app
# ---------------------------------------------------------------------------

harness_app = typer.Typer(help="Manage harness configurations.", no_args_is_help=True)
app.add_typer(harness_app, name="harness")

# ---------------------------------------------------------------------------
# memory sub-app
# ---------------------------------------------------------------------------

memory_app = typer.Typer(help="Manage harness conversation memory.", no_args_is_help=True)
app.add_typer(memory_app, name="memory")

# ---------------------------------------------------------------------------
# agent sub-app
# ---------------------------------------------------------------------------

agent_app = typer.Typer(help="Manage AI agents (interactive conversation).", no_args_is_help=True)
app.add_typer(agent_app, name="agent")

# ---------------------------------------------------------------------------
# blueprint sub-app
# ---------------------------------------------------------------------------

blueprint_app = typer.Typer(help="Manage blueprint workflows.", no_args_is_help=True)
app.add_typer(blueprint_app, name="blueprint")

# ---------------------------------------------------------------------------
# eval sub-app
# ---------------------------------------------------------------------------

eval_app = typer.Typer(help="Eval engine — manage test suites.", no_args_is_help=True)
app.add_typer(eval_app, name="eval")

# ---------------------------------------------------------------------------
# cost sub-app
# ---------------------------------------------------------------------------

cost_app = typer.Typer(help="Track and report LLM call costs.", no_args_is_help=True)
app.add_typer(cost_app, name="cost")

# ---------------------------------------------------------------------------
# stats sub-app
# ---------------------------------------------------------------------------

stats_app = typer.Typer(help="Statistics dashboard for skills and harnesses.", no_args_is_help=True)
app.add_typer(stats_app, name="stats")


def _require_init() -> None:
    if not is_initialized():
        console.print("[red]✗ Not initialized.[/red] Run [bold]harnesskit init[/bold] first.")
        raise typer.Exit(1)


def _parse_name_version(ref: str) -> tuple[str, str | None]:
    """Split 'name@v1.2.3' → ('name', 'v1.2.3'). Without @ returns (ref, None)."""
    if "@" in ref:
        name, ver = ref.rsplit("@", 1)
        return name, ver
    return ref, None


# ---------------------------------------------------------------------------
# prompt save
# ---------------------------------------------------------------------------


@prompt_app.command("save")
def prompt_save(
    name: str = typer.Argument(..., help="Prompt name (identifier)."),
    file: Optional[Path] = typer.Option(None, "--file", "-f", help="Read content from file."),
    content: Optional[str] = typer.Option(None, "--content", "-c", help="Content string."),
    description: str = typer.Option("", "--description", "-d", help="Short description."),
    tags: str = typer.Option("", "--tags", "-t", help="Comma-separated tags."),
    changelog: str = typer.Option("", "--changelog", help="Changelog note for this version."),
) -> None:
    """Save a prompt from --file / --content / stdin. Auto-increments patch version."""
    _require_init()

    # Resolve content
    if file is not None:
        prompt_content = file.read_text(encoding="utf-8")
    elif content is not None:
        prompt_content = content
    elif not sys.stdin.isatty():
        prompt_content = sys.stdin.read()
        if not prompt_content.strip():
            console.print("[red]✗ Stdin is empty. Provide content via --file, --content, or stdin.[/red]")
            raise typer.Exit(1)
    else:
        console.print("[red]✗ Provide content via --file, --content, or stdin.[/red]")
        raise typer.Exit(1)

    tag_list = [t.strip() for t in tags.split(",") if t.strip()] if tags else []

    version, is_new = _prompt_mod.save_prompt(
        name=name,
        content=prompt_content,
        description=description,
        tags=tag_list,
        changelog=changelog,
    )

    action = "Created" if is_new else "Updated"
    console.print(f"[green]✓ {action}[/green] prompt [bold]{name}[/bold] → [cyan]{version}[/cyan]")


# ---------------------------------------------------------------------------
# prompt show
# ---------------------------------------------------------------------------


@prompt_app.command("show")
def prompt_show(
    ref: str = typer.Argument(..., help="Prompt name or name@version."),
) -> None:
    """Show a prompt. Use name@v0.1.0 for a specific version."""
    _require_init()
    name, version = _parse_name_version(ref)

    try:
        data = _prompt_mod.load_prompt(name, version)
    except FileNotFoundError as e:
        console.print(f"[red]✗ {e}[/red]")
        raise typer.Exit(1)

    console.print(f"\n[bold cyan]{data['name']}[/bold cyan]  [dim]{data['version']}[/dim]")
    if data.get("description"):
        console.print(f"[italic]{data['description']}[/italic]")
    if data.get("tags"):
        console.print(f"[dim]tags:[/dim] {', '.join(data['tags'])}")
    if data.get("variables"):
        console.print("[dim]variables:[/dim]")
        for var in data["variables"]:
            req = " [red](required)[/red]" if var.get("required") else ""
            default = f"  [dim]default: {var['default']}[/dim]" if "default" in var else ""
            console.print(f"  • {var['name']}{req}{default}")
    console.print(f"\n[bold]Content:[/bold]\n{data.get('content', '')}")
    if data.get("changelog"):
        console.print(f"\n[dim]changelog: {data['changelog']}[/dim]")
    console.print(f"[dim]created_at: {data.get('created_at', '')}[/dim]")


# ---------------------------------------------------------------------------
# prompt list
# ---------------------------------------------------------------------------


@prompt_app.command("list")
def prompt_list() -> None:
    """List all prompts (rich table)."""
    _require_init()

    prompts = _prompt_mod.list_prompts()
    if not prompts:
        console.print("[dim]No prompts saved yet.[/dim]")
        return

    table = Table(title="Prompts", show_lines=False, header_style="bold cyan")
    table.add_column("Name", style="bold")
    table.add_column("Version", style="cyan")
    table.add_column("Description")
    table.add_column("Tags", style="dim")
    table.add_column("Updated", style="dim")

    for p in prompts:
        tags_str = ", ".join(p.get("tags") or [])
        created = (p.get("created_at") or "")[:19].replace("T", " ")
        table.add_row(
            p.get("name", ""),
            p.get("version", ""),
            p.get("description", ""),
            tags_str,
            created,
        )

    console.print(table)


# ---------------------------------------------------------------------------
# prompt history
# ---------------------------------------------------------------------------


@prompt_app.command("history")
def prompt_history(
    name: str = typer.Argument(..., help="Prompt name."),
) -> None:
    """Show version history timeline for a prompt."""
    _require_init()

    versions = _prompt_mod.list_versions(name)
    if not versions:
        console.print(f"[red]✗ Prompt '{name}' not found.[/red]")
        raise typer.Exit(1)

    current = _prompt_mod.get_current_version(name)
    console.print(f"\n[bold]History: [cyan]{name}[/cyan][/bold]\n")
    for i, ver in enumerate(versions):
        is_last = i == len(versions) - 1
        connector = "└─" if is_last else "├─"
        marker = " [green]← current[/green]" if ver == current else ""
        try:
            data = _prompt_mod.load_prompt(name, ver)
            ts = (data.get("created_at") or "")[:19].replace("T", " ")
            cl = f"  [dim]{data.get('changelog', '')}[/dim]" if data.get("changelog") else ""
        except Exception:
            ts = ""
            cl = ""
        console.print(f"  {connector} [cyan]{ver}[/cyan]{marker}  [dim]{ts}[/dim]{cl}")


# ---------------------------------------------------------------------------
# prompt diff
# ---------------------------------------------------------------------------


@prompt_app.command("diff")
def prompt_diff(
    ref_a: str = typer.Argument(..., help="First ref, e.g. name@v0.0.1"),
    ref_b: str = typer.Argument(..., help="Second ref, e.g. name@v0.0.2"),
) -> None:
    """Show coloured diff between two prompt versions."""
    _require_init()

    name_a, ver_a = _parse_name_version(ref_a)
    name_b, ver_b = _parse_name_version(ref_b)

    try:
        lines = _prompt_mod.diff_prompts(name_a, ver_a, name_b, ver_b)
    except FileNotFoundError as e:
        console.print(f"[red]✗ {e}[/red]")
        raise typer.Exit(1)

    if not lines:
        console.print("[dim]No differences.[/dim]")
        return

    for line in lines:
        line = line.rstrip("\n")
        if line.startswith("+++") or line.startswith("---"):
            console.print(Text(line, style="bold"))
        elif line.startswith("@@"):
            console.print(Text(line, style="cyan"))
        elif line.startswith("+"):
            console.print(Text(line, style="green"))
        elif line.startswith("-"):
            console.print(Text(line, style="red"))
        else:
            console.print(line)


# ---------------------------------------------------------------------------
# prompt delete
# ---------------------------------------------------------------------------


@prompt_app.command("delete")
def prompt_delete(
    ref: str = typer.Argument(..., help="Prompt name or name@version to delete."),
    yes: bool = typer.Option(False, "--yes", "-y", help="Skip confirmation."),
) -> None:
    """Delete a prompt or a specific version."""
    _require_init()
    name, version = _parse_name_version(ref)

    target = f"[bold]{name}[/bold]" if version is None else f"[bold]{name}[/bold]@[cyan]{version}[/cyan]"
    if not yes:
        typer.confirm(f"Delete {target}?", abort=True)

    try:
        _prompt_mod.delete_prompt(name, version)
    except FileNotFoundError as e:
        console.print(f"[red]✗ {e}[/red]")
        raise typer.Exit(1)

    console.print(f"[green]✓ Deleted[/green] {target}")


# ---------------------------------------------------------------------------
# schema save
# ---------------------------------------------------------------------------


@schema_app.command("save")
def schema_save(
    name: str = typer.Argument(..., help="Schema name (identifier)."),
    file: Optional[Path] = typer.Option(None, "--file", "-f", help="Read JSON from file."),
    description: str = typer.Option("", "--description", "-d", help="Short description."),
    tags: str = typer.Option("", "--tags", "-t", help="Comma-separated tags."),
    changelog: str = typer.Option("", "--changelog", help="Changelog note for this version."),
) -> None:
    """Save a schema from --file / stdin. The JSON must contain a 'parameters' object."""
    import json as _json

    _require_init()

    if file is not None:
        raw = file.read_text(encoding="utf-8")
    elif not sys.stdin.isatty():
        raw = sys.stdin.read()
        if not raw.strip():
            console.print("[red]✗ Stdin is empty. Provide JSON via --file or stdin.[/red]")
            raise typer.Exit(1)
    else:
        console.print("[red]✗ Provide JSON via --file or stdin.[/red]")
        raise typer.Exit(1)

    try:
        payload = _json.loads(raw)
    except _json.JSONDecodeError as e:
        console.print(f"[red]✗ Invalid JSON: {e}[/red]")
        raise typer.Exit(1)

    # Accept either a bare parameters object or a full schema document
    if "parameters" in payload:
        parameters = payload["parameters"]
        description = description or payload.get("description", "")
        if not tags:
            tags = ",".join(payload.get("tags", []))
    else:
        # Treat the entire payload as the parameters object
        parameters = payload

    tag_list = [t.strip() for t in tags.split(",") if t.strip()] if tags else []

    version, is_new = _schema_mod.save_schema(
        name=name,
        parameters=parameters,
        description=description,
        tags=tag_list,
        changelog=changelog,
    )

    action = "Created" if is_new else "Updated"
    console.print(f"[green]✓ {action}[/green] schema [bold]{name}[/bold] → [cyan]{version}[/cyan]")


# ---------------------------------------------------------------------------
# schema show
# ---------------------------------------------------------------------------


@schema_app.command("show")
def schema_show(
    ref: str = typer.Argument(..., help="Schema name or name@version."),
) -> None:
    """Show a schema. Use name@v0.1.0 for a specific version."""
    import json as _json

    _require_init()
    name, version = _parse_name_version(ref)

    try:
        data = _schema_mod.load_schema(name, version)
    except FileNotFoundError as e:
        console.print(f"[red]✗ {e}[/red]")
        raise typer.Exit(1)

    console.print(f"\n[bold cyan]{data['name']}[/bold cyan]  [dim]{data['version']}[/dim]")
    if data.get("description"):
        console.print(f"[italic]{data['description']}[/italic]")
    if data.get("tags"):
        console.print(f"[dim]tags:[/dim] {', '.join(data['tags'])}")
    console.print(f"\n[bold]Parameters:[/bold]")
    console.print(_json.dumps(data.get("parameters", {}), ensure_ascii=False, indent=2))
    if data.get("changelog"):
        console.print(f"\n[dim]changelog: {data['changelog']}[/dim]")
    console.print(f"[dim]created_at: {data.get('created_at', '')}[/dim]")


# ---------------------------------------------------------------------------
# schema list
# ---------------------------------------------------------------------------


@schema_app.command("list")
def schema_list() -> None:
    """List all schemas (rich table)."""
    _require_init()

    schemas = _schema_mod.list_schemas()
    if not schemas:
        console.print("[dim]No schemas saved yet.[/dim]")
        return

    table = Table(title="Schemas", show_lines=False, header_style="bold cyan")
    table.add_column("Name", style="bold")
    table.add_column("Version", style="cyan")
    table.add_column("Description")
    table.add_column("Tags", style="dim")
    table.add_column("Updated", style="dim")

    for s in schemas:
        tags_str = ", ".join(s.get("tags") or [])
        created = (s.get("created_at") or "")[:19].replace("T", " ")
        table.add_row(
            s.get("name", ""),
            s.get("version", ""),
            s.get("description", ""),
            tags_str,
            created,
        )

    console.print(table)


# ---------------------------------------------------------------------------
# schema validate
# ---------------------------------------------------------------------------


@schema_app.command("validate")
def schema_validate(
    name: str = typer.Argument(..., help="Schema name to validate."),
) -> None:
    """Validate a schema's parameters field against JSON Schema specification."""
    _require_init()

    try:
        errors = _schema_mod.validate_schema(name)
    except FileNotFoundError as e:
        console.print(f"[red]✗ {e}[/red]")
        raise typer.Exit(1)

    if not errors:
        console.print(f"[green]✓ Schema [bold]{name}[/bold] is valid.[/green]")
    else:
        console.print(f"[red]✗ Schema [bold]{name}[/bold] has {len(errors)} error(s):[/red]")
        for err in errors:
            console.print(f"  [red]•[/red] {err}")
        raise typer.Exit(1)


# ---------------------------------------------------------------------------
# schema delete
# ---------------------------------------------------------------------------


@schema_app.command("delete")
def schema_delete(
    ref: str = typer.Argument(..., help="Schema name or name@version to delete."),
    yes: bool = typer.Option(False, "--yes", "-y", help="Skip confirmation."),
) -> None:
    """Delete a schema or a specific version."""
    _require_init()
    name, version = _parse_name_version(ref)

    target = f"[bold]{name}[/bold]" if version is None else f"[bold]{name}[/bold]@[cyan]{version}[/cyan]"
    if not yes:
        typer.confirm(f"Delete {target}?", abort=True)

    try:
        _schema_mod.delete_schema(name, version)
    except FileNotFoundError as e:
        console.print(f"[red]✗ {e}[/red]")
        raise typer.Exit(1)

    console.print(f"[green]✓ Deleted[/green] {target}")


# ---------------------------------------------------------------------------
# context save
# ---------------------------------------------------------------------------


@context_app.command("save")
def context_save(
    name: str = typer.Argument(..., help="Context name (identifier)."),
    file: Optional[Path] = typer.Option(None, "--file", "-f", help="Read YAML from file."),
    description: str = typer.Option("", "--description", "-d", help="Short description."),
    tags: str = typer.Option("", "--tags", "-t", help="Comma-separated tags."),
    changelog: str = typer.Option("", "--changelog", help="Changelog note for this version."),
) -> None:
    """Save a context template from --file / stdin (YAML with slots + template)."""
    _require_init()

    if file is not None:
        raw = file.read_text(encoding="utf-8")
    elif not sys.stdin.isatty():
        raw = sys.stdin.read()
        if not raw.strip():
            console.print("[red]✗ Stdin is empty. Provide YAML via --file or stdin.[/red]")
            raise typer.Exit(1)
    else:
        console.print("[red]✗ Provide YAML via --file or stdin.[/red]")
        raise typer.Exit(1)

    try:
        payload = yaml.safe_load(raw)
    except Exception as e:
        console.print(f"[red]✗ Invalid YAML: {e}[/red]")
        raise typer.Exit(1)

    if not isinstance(payload, dict):
        console.print("[red]✗ YAML must be a mapping object.[/red]")
        raise typer.Exit(1)

    template = payload.get("template", "")
    slots = payload.get("slots", [])
    description = description or payload.get("description", "")
    if not tags:
        tags = ",".join(payload.get("tags") or [])

    tag_list = [t.strip() for t in tags.split(",") if t.strip()] if tags else []

    version, is_new = _context_mod.save_context(
        name=name,
        template=template,
        slots=slots,
        description=description,
        tags=tag_list,
        changelog=changelog,
    )

    action = "Created" if is_new else "Updated"
    console.print(f"[green]✓ {action}[/green] context [bold]{name}[/bold] → [cyan]{version}[/cyan]")


# ---------------------------------------------------------------------------
# context render
# ---------------------------------------------------------------------------


@context_app.command("render")
def context_render(
    ref: str = typer.Argument(..., help="Context name or name@version."),
    var: list[str] = typer.Option([], "--var", help="Variable as key=value. Repeatable."),
) -> None:
    """Render a context template with --var key=value substitutions."""
    _require_init()
    name, version = _parse_name_version(ref)

    variables: dict[str, object] = {}
    for v in var:
        if "=" not in v:
            console.print(f"[red]✗ Invalid --var format: '{v}'. Use key=value.[/red]")
            raise typer.Exit(1)
        k, _, val = v.partition("=")
        variables[k.strip()] = val

    try:
        rendered = _context_mod.render_context(name, variables, version)
    except FileNotFoundError as e:
        console.print(f"[red]✗ {e}[/red]")
        raise typer.Exit(1)
    except ValueError as e:
        console.print(f"[red]✗ {e}[/red]")
        raise typer.Exit(1)

    console.print(rendered)


# ---------------------------------------------------------------------------
# context show
# ---------------------------------------------------------------------------


@context_app.command("show")
def context_show(
    ref: str = typer.Argument(..., help="Context name or name@version."),
) -> None:
    """Show a context template. Use name@v0.1.0 for a specific version."""
    _require_init()
    name, version = _parse_name_version(ref)

    try:
        data = _context_mod.load_context(name, version)
    except FileNotFoundError as e:
        console.print(f"[red]✗ {e}[/red]")
        raise typer.Exit(1)

    console.print(f"\n[bold cyan]{data['name']}[/bold cyan]  [dim]{data['version']}[/dim]")
    if data.get("description"):
        console.print(f"[italic]{data['description']}[/italic]")
    if data.get("tags"):
        console.print(f"[dim]tags:[/dim] {', '.join(data['tags'])}")
    if data.get("slots"):
        console.print("[dim]slots:[/dim]")
        for slot in data["slots"]:
            req = " [red](required)[/red]" if slot.get("required") else ""
            default = f"  [dim]default: {slot['default']}[/dim]" if "default" in slot else ""
            console.print(f"  • {slot['name']}{req}{default}")
    console.print(f"\n[bold]Template:[/bold]\n{data.get('template', '')}")
    if data.get("changelog"):
        console.print(f"\n[dim]changelog: {data['changelog']}[/dim]")
    console.print(f"[dim]created_at: {data.get('created_at', '')}[/dim]")


# ---------------------------------------------------------------------------
# context list
# ---------------------------------------------------------------------------


@context_app.command("list")
def context_list() -> None:
    """List all context templates (rich table)."""
    _require_init()

    contexts = _context_mod.list_contexts()
    if not contexts:
        console.print("[dim]No contexts saved yet.[/dim]")
        return

    table = Table(title="Contexts", show_lines=False, header_style="bold cyan")
    table.add_column("Name", style="bold")
    table.add_column("Version", style="cyan")
    table.add_column("Description")
    table.add_column("Slots", style="dim")
    table.add_column("Updated", style="dim")

    for c in contexts:
        slot_names = ", ".join(s["name"] for s in (c.get("slots") or []))
        created = (c.get("created_at") or "")[:19].replace("T", " ")
        table.add_row(
            c.get("name", ""),
            c.get("version", ""),
            c.get("description", ""),
            slot_names,
            created,
        )

    console.print(table)


# ---------------------------------------------------------------------------
# context delete
# ---------------------------------------------------------------------------


@context_app.command("delete")
def context_delete(
    ref: str = typer.Argument(..., help="Context name or name@version to delete."),
    yes: bool = typer.Option(False, "--yes", "-y", help="Skip confirmation."),
) -> None:
    """Delete a context or a specific version."""
    _require_init()
    name, version = _parse_name_version(ref)

    target = f"[bold]{name}[/bold]" if version is None else f"[bold]{name}[/bold]@[cyan]{version}[/cyan]"
    if not yes:
        typer.confirm(f"Delete {target}?", abort=True)

    try:
        _context_mod.delete_context(name, version)
    except FileNotFoundError as e:
        console.print(f"[red]✗ {e}[/red]")
        raise typer.Exit(1)

    console.print(f"[green]✓ Deleted[/green] {target}")


# ---------------------------------------------------------------------------
# rule add
# ---------------------------------------------------------------------------


@rule_app.command("add")
def rule_add(
    name: str = typer.Argument(..., help="Rule name (identifier)."),
    rule_type: str = typer.Option("hard", "--type", "-t", help="Rule type: hard or soft."),
    check_type: str = typer.Option("regex", "--check-type", help="Check type: regex or length."),
    pattern: str = typer.Option(..., "--pattern", "-p", help="Regex pattern or max length integer."),
    description: str = typer.Option("", "--description", "-d", help="Short description."),
    fix_hint: str = typer.Option("", "--fix-hint", help="Hint shown when rule triggers."),
) -> None:
    """Add or update a rule constraint."""
    _require_init()

    try:
        is_new = _rule_mod.save_rule(
            name,
            rule_type=rule_type,
            check_type=check_type,
            pattern=pattern,
            description=description,
            fix_hint=fix_hint,
        )
    except ValueError as e:
        console.print(f"[red]✗ {e}[/red]")
        raise typer.Exit(1)

    verb = "Created" if is_new else "Updated"
    console.print(f"[green]✓ {verb} rule[/green] [bold]{name}[/bold] (type=[cyan]{rule_type}[/cyan])")


# ---------------------------------------------------------------------------
# rule list
# ---------------------------------------------------------------------------


@rule_app.command("list")
def rule_list() -> None:
    """List all rules (rich table)."""
    _require_init()

    rules = _rule_mod.list_rules()
    if not rules:
        console.print("[dim]No rules saved yet.[/dim]")
        return

    table = Table(title="Rules", show_lines=False, header_style="bold cyan")
    table.add_column("Name", style="bold")
    table.add_column("Type", style="cyan")
    table.add_column("Check", style="dim")
    table.add_column("Pattern", style="dim")
    table.add_column("Description")

    for r in rules:
        check = r.get("check") or {}
        table.add_row(
            r.get("name", ""),
            r.get("type", ""),
            check.get("type", ""),
            check.get("pattern", ""),
            r.get("description", ""),
        )

    console.print(table)


# ---------------------------------------------------------------------------
# rule show
# ---------------------------------------------------------------------------


@rule_app.command("show")
def rule_show(
    name: str = typer.Argument(..., help="Rule name."),
) -> None:
    """Show a rule's definition."""
    _require_init()

    try:
        rule = _rule_mod.load_rule(name)
    except FileNotFoundError as e:
        console.print(f"[red]✗ {e}[/red]")
        raise typer.Exit(1)

    check = rule.get("check") or {}
    console.print(f"\n[bold]Rule:[/bold] {rule.get('name', '')}")
    console.print(f"[bold]Type:[/bold] [cyan]{rule.get('type', '')}[/cyan]")
    console.print(f"[bold]Description:[/bold] {rule.get('description', '') or '(none)'}")
    console.print(f"[bold]Check type:[/bold] {check.get('type', '')}")
    console.print(f"[bold]Pattern:[/bold] {check.get('pattern', '')}")
    console.print(f"[bold]Fix hint:[/bold] {rule.get('fix_hint', '') or '(none)'}")
    console.print(f"[bold]Created:[/bold] {(rule.get('created_at') or '')[:19].replace('T', ' ')}")


# ---------------------------------------------------------------------------
# rule test
# ---------------------------------------------------------------------------


@rule_app.command("test")
def rule_test(
    name: str = typer.Argument(..., help="Rule name."),
    input_text: str = typer.Option(..., "--input", "-i", help="Input text to test."),
) -> None:
    """Test whether input text triggers a rule."""
    _require_init()

    try:
        result = _rule_mod.check_rule_by_name(name, input_text)
    except FileNotFoundError as e:
        console.print(f"[red]✗ {e}[/red]")
        raise typer.Exit(1)
    except ValueError as e:
        console.print(f"[red]✗ {e}[/red]")
        raise typer.Exit(1)

    if result.triggered:
        console.print(f"[red]✗ TRIGGERED[/red] — rule [bold]{name}[/bold] ([cyan]{result.rule_type}[/cyan])")
        if result.matches:
            console.print(f"  [bold]Matches:[/bold] {result.matches}")
        if result.fix_hint:
            console.print(f"  [bold]Fix hint:[/bold] {result.fix_hint}")
    else:
        console.print(f"[green]✓ PASSED[/green] — rule [bold]{name}[/bold] did not trigger")


# ---------------------------------------------------------------------------
# rule delete
# ---------------------------------------------------------------------------


@rule_app.command("delete")
def rule_delete(
    name: str = typer.Argument(..., help="Rule name."),
    yes: bool = typer.Option(False, "--yes", "-y", help="Skip confirmation."),
) -> None:
    """Delete a rule."""
    _require_init()

    if not yes:
        typer.confirm(f"Delete rule '{name}'?", abort=True)

    try:
        _rule_mod.delete_rule(name)
    except FileNotFoundError as e:
        console.print(f"[red]✗ {e}[/red]")
        raise typer.Exit(1)

    console.print(f"[green]✓ Deleted rule[/green] [bold]{name}[/bold]")


@rule_app.command("stats")
def rule_stats() -> None:
    """Show rule violation statistics aggregated from call logs."""
    _require_init()

    counts = _call_logger_mod.violation_stats()
    rules = _rule_mod.list_rules()

    if not rules and not counts:
        console.print("[dim]No rules found.[/dim]")
        return

    table = Table(title="Rule Violation Statistics", show_lines=False)
    table.add_column("Rule", style="cyan")
    table.add_column("Type", style="dim")
    table.add_column("Violations", justify="right")
    table.add_column("Description", style="dim")

    # Show all known rules with their counts
    shown_rules = set()
    for rule in rules:
        rname = rule.get("name", "")
        count = counts.get(rname, 0)
        rtype = rule.get("type", "hard")
        desc = rule.get("description", "")
        type_color = "red" if rtype == "hard" else "yellow"
        count_style = "bold red" if count > 0 else "dim"
        table.add_row(
            rname,
            f"[{type_color}]{rtype}[/{type_color}]",
            f"[{count_style}]{count}[/{count_style}]",
            desc,
        )
        shown_rules.add(rname)

    # Show any rules in logs that no longer exist as files
    for rname, count in sorted(counts.items()):
        if rname not in shown_rules:
            table.add_row(rname, "[dim]deleted[/dim]", f"[bold red]{count}[/bold red]", "[dim](rule file removed)[/dim]")

    console.print(table)

    total = sum(counts.values())
    if total:
        console.print(f"\n[dim]Total violations recorded in call logs: [bold]{total}[/bold][/dim]")
    else:
        console.print("\n[dim]No violations recorded in call logs.[/dim]")


# ---------------------------------------------------------------------------
# doctor
# ---------------------------------------------------------------------------


@app.command()
def doctor() -> None:
    """Scan .harness/ health — broken references, unused assets, cycles."""
    _require_init()

    report = _resolver_mod.run_doctor()

    console.print("\n[bold]HarnessKit Doctor[/bold] — .harness/ health check\n")

    # Group assets by type for display
    by_type: dict[str, list] = {}
    for asset in report.assets:
        by_type.setdefault(asset.asset_type, []).append(asset)

    total_broken = 0

    for asset_type, assets in by_type.items():
        console.print(f"[bold]Checking {asset_type}s...[/bold] ({len(assets)} found)")
        for a in assets:
            if a.broken:
                total_broken += 1
                console.print(f"  [red]✗[/red] [bold]{a.name}[/bold] — {a.issue}")
            else:
                tag_str = ""
                if a.tags:
                    parts = [f"{t}→{v}" for t, v in a.tags.items()]
                    tag_str = f"  [dim]tags: {', '.join(parts)}[/dim]"
                ver_str = (
                    f"[cyan]{a.version}[/cyan]" if a.version and a.version != "current" else ""
                )
                console.print(f"  [green]✓[/green] {a.name}  {ver_str}{tag_str}")
            for bt in a.broken_tags:
                total_broken += 1
                console.print(
                    f"    [red]✗[/red] tag '{bt}' → '{a.tags[bt]}' (version not found)"
                )

    if not report.assets:
        console.print("[dim]No assets found.[/dim]")

    console.print()

    # Circular references
    if report.cycles:
        console.print(
            f"[red]⚠ {len(report.cycles)} circular reference(s) detected:[/red]"
        )
        for cycle in report.cycles:
            console.print(f"  [red]•[/red] {' → '.join(cycle)}")
    else:
        console.print("[green]✓ No circular references detected.[/green]")

    # Unused assets
    if report.unused_assets:
        console.print(
            f"\n[yellow]⚠ {len(report.unused_assets)} unreferenced asset(s)[/yellow]"
            f" [dim](not referenced by any skill/harness):[/dim]"
        )
        for atype, aname in report.unused_assets:
            console.print(f"  [dim]•[/dim] {atype}: {aname}")
    else:
        console.print("[green]✓ No unreferenced assets.[/green]")

    # Summary
    console.print(
        f"\n[bold]Summary:[/bold] {total_broken} broken reference(s), "
        f"{len(report.unused_assets)} unreferenced asset(s), "
        f"{len(report.cycles)} cycle(s), "
        f"{len(report.assets)} total asset(s)"
    )

    if total_broken > 0 or report.cycles:
        raise typer.Exit(1)


# ---------------------------------------------------------------------------
# skill save
# ---------------------------------------------------------------------------


@skill_app.command("save")
def skill_save(
    file: Path = typer.Option(..., "--file", "-f", help="Path to the Skill YAML file."),
) -> None:
    """Save a skill from a YAML --file. Auto-increments patch version."""
    _require_init()

    if not file.exists():
        console.print(f"[red]✗ File not found: {file}[/red]")
        raise typer.Exit(1)

    raw = file.read_text(encoding="utf-8")
    try:
        data = yaml.safe_load(raw)
    except yaml.YAMLError as exc:
        console.print(f"[red]✗ Invalid YAML: {exc}[/red]")
        raise typer.Exit(1)

    if not isinstance(data, dict):
        console.print("[red]✗ Skill YAML must be a mapping at the top level.[/red]")
        raise typer.Exit(1)

    errors = _skill_mod._validate_skill_data(data)
    if errors:
        console.print("[red]✗ Skill YAML validation failed:[/red]")
        for err in errors:
            console.print(f"  [red]•[/red] {err}")
        raise typer.Exit(1)

    try:
        version, is_new = _skill_mod.save_skill_from_dict(data)
    except ValueError as exc:
        console.print(f"[red]✗ {exc}[/red]")
        raise typer.Exit(1)

    action = "Created" if is_new else "Updated"
    name = data.get("name", "")
    console.print(f"[green]✓ {action}[/green] skill [bold]{name}[/bold] → [cyan]{version}[/cyan]")


# ---------------------------------------------------------------------------
# skill show
# ---------------------------------------------------------------------------


@skill_app.command("show")
def skill_show(
    ref: str = typer.Argument(..., help="Skill name or name@version."),
    render: bool = typer.Option(False, "--render", help="Resolve and display full prompt content."),
) -> None:
    """Show a skill definition. Use name@v0.1.0 for a specific version."""
    _require_init()
    name, version = _parse_name_version(ref)

    try:
        data = _skill_mod.load_skill(name, version)
    except FileNotFoundError as e:
        console.print(f"[red]✗ {e}[/red]")
        raise typer.Exit(1)

    console.print(f"\n[bold cyan]{data['name']}[/bold cyan]  [dim]{data['version']}[/dim]")
    if data.get("description"):
        console.print(f"[italic]{data['description']}[/italic]")
    if data.get("trigger"):
        console.print(f"[dim]trigger:[/dim] {data['trigger']}")

    if data.get("inputs"):
        console.print("\n[bold]Inputs:[/bold]")
        for inp in data["inputs"]:
            req = " [red](required)[/red]" if inp.get("required") else ""
            default = f"  default={inp['default']}" if "default" in inp else ""
            console.print(f"  • {inp.get('name')} ([cyan]{inp.get('type')}[/cyan]){req}{default}")

    if data.get("outputs"):
        console.print("\n[bold]Outputs:[/bold]")
        for out in data["outputs"]:
            schema_ref = f"  schema={out['schema']}" if out.get("schema") else ""
            console.print(f"  • {out.get('name')} ([cyan]{out.get('type')}[/cyan]){schema_ref}")

    if data.get("assets"):
        console.print("\n[bold]Assets:[/bold]")
        console.print(
            yaml.dump(data["assets"], allow_unicode=True, default_flow_style=False).strip()
        )

    if data.get("examples"):
        console.print(f"\n[bold]Examples:[/bold] {len(data['examples'])} example(s)")

    if data.get("changelog"):
        console.print(f"\n[dim]changelog: {data['changelog']}[/dim]")
    console.print(f"[dim]created_at: {data.get('created_at', '')}[/dim]")

    if render:
        rendered = _skill_mod.render_skill_prompt(name, version)
        console.print("\n[bold magenta]── Rendered Prompt ──[/bold magenta]")
        if rendered["system"]:
            console.print("\n[bold]System Prompt:[/bold]")
            console.print(rendered["system"])
        if rendered["user"]:
            console.print("\n[bold]User Prompt:[/bold]")
            console.print(rendered["user"])
        if rendered["context"]:
            console.print("\n[bold]Context Template:[/bold]")
            console.print(rendered["context"])
        if rendered["rules"]:
            console.print("\n[bold]Rules:[/bold]")
            console.print(rendered["rules"])
        if rendered["schemas"]:
            console.print("\n[bold]Schemas (Tools):[/bold]")
            console.print(rendered["schemas"])


# ---------------------------------------------------------------------------
# skill list
# ---------------------------------------------------------------------------


@skill_app.command("list")
def skill_list() -> None:
    """List all skills (rich table)."""
    _require_init()

    skills = _skill_mod.list_skills()
    if not skills:
        console.print("[dim]No skills saved yet.[/dim]")
        return

    table = Table(title="Skills", show_lines=False, header_style="bold cyan")
    table.add_column("Name", style="bold")
    table.add_column("Version", style="cyan")
    table.add_column("Description")
    table.add_column("Trigger", style="dim")
    table.add_column("Updated", style="dim")

    for s in skills:
        created = (s.get("created_at") or "")[:19].replace("T", " ")
        table.add_row(
            s.get("name", ""),
            s.get("version", ""),
            s.get("description", ""),
            s.get("trigger", ""),
            created,
        )

    console.print(table)


# ---------------------------------------------------------------------------
# skill diff
# ---------------------------------------------------------------------------


@skill_app.command("diff")
def skill_diff(
    ref_a: str = typer.Argument(..., help="First skill ref: name or name@version."),
    ref_b: str = typer.Argument(..., help="Second skill ref: name or name@version."),
) -> None:
    """Show a coloured diff between two skill versions."""
    _require_init()
    name_a, version_a = _parse_name_version(ref_a)
    name_b, version_b = _parse_name_version(ref_b)

    try:
        lines = _skill_mod.diff_skills(name_a, version_a, name_b, version_b)
    except FileNotFoundError as e:
        console.print(f"[red]✗ {e}[/red]")
        raise typer.Exit(1)

    if not lines:
        console.print("[dim]No differences.[/dim]")
        return

    for line in lines:
        if line.startswith("+++") or line.startswith("---"):
            console.print(f"[bold]{line}[/bold]", end="")
        elif line.startswith("@@"):
            console.print(f"[cyan]{line}[/cyan]", end="")
        elif line.startswith("+"):
            console.print(f"[green]{line}[/green]", end="")
        elif line.startswith("-"):
            console.print(f"[red]{line}[/red]", end="")
        else:
            console.print(line, end="")


# ---------------------------------------------------------------------------
# skill validate
# ---------------------------------------------------------------------------


@skill_app.command("validate")
def skill_validate(
    ref: str = typer.Argument(..., help="Skill name or name@version."),
) -> None:
    """Validate that all asset references in a skill exist."""
    _require_init()
    name, version = _parse_name_version(ref)

    errors = _skill_mod.validate_skill_references(name, version)
    if not errors:
        console.print(f"[green]✓ All references valid[/green] for skill [bold]{ref}[/bold]")
        return

    console.print(f"[red]✗ {len(errors)} broken reference(s) in skill [bold]{ref}[/bold]:[/red]")
    for err in errors:
        console.print(f"  [red]•[/red] {err}")
    raise typer.Exit(1)


# ---------------------------------------------------------------------------
# skill delete
# ---------------------------------------------------------------------------


@skill_app.command("delete")
def skill_delete(
    ref: str = typer.Argument(..., help="Skill name or name@version to delete."),
    yes: bool = typer.Option(False, "--yes", "-y", help="Skip confirmation."),
) -> None:
    """Delete a skill or a specific version."""
    _require_init()
    name, version = _parse_name_version(ref)

    target = f"[bold]{name}[/bold]" if version is None else f"[bold]{name}[/bold]@[cyan]{version}[/cyan]"
    if not yes:
        typer.confirm(f"Delete {target}?", abort=True)

    try:
        _skill_mod.delete_skill(name, version)
    except FileNotFoundError as e:
        console.print(f"[red]✗ {e}[/red]")
        raise typer.Exit(1)

    console.print(f"[green]✓ Deleted[/green] {target}")


# ---------------------------------------------------------------------------
# skill run
# ---------------------------------------------------------------------------


@skill_app.command("run")
def skill_run(
    ref: str = typer.Argument(..., help="Skill name or name@version."),
    var: list[str] = typer.Option(
        [], "--var", "-v",
        help="Input variable as key=value. Can be repeated.",
    ),
    model: Optional[str] = typer.Option(None, "--model", "-m", help="Override model (e.g. gpt-4o)."),
    stream: bool = typer.Option(False, "--stream", "-s", help="Stream output token-by-token."),
    check_rules: str = typer.Option(
        "lenient",
        "--check-rules",
        help="Rule check mode: 'strict' (fail on hard rule violation) or 'lenient' (warn only).",
    ),
    dry_run: bool = typer.Option(False, "--dry-run", help="Show assembled prompt without calling LLM."),
) -> None:
    """Run a skill by calling the configured LLM."""
    _require_init()
    name, version = _parse_name_version(ref)

    # Load skill
    try:
        skill_data = _skill_mod.load_skill(name, version)
    except FileNotFoundError as e:
        console.print(f"[red]✗ {e}[/red]")
        raise typer.Exit(1)

    # Parse --var key=value pairs
    vars_dict: dict[str, str] = {}
    for v in var:
        if "=" not in v:
            console.print(f"[red]✗ Invalid --var format: [bold]{v}[/bold] (expected key=value)[/red]")
            raise typer.Exit(1)
        k, val = v.split("=", 1)
        vars_dict[k.strip()] = val

    # Validate required inputs
    for inp in skill_data.get("inputs") or []:
        if inp.get("required", True) and inp.get("name") not in vars_dict:
            if inp.get("default") is not None:
                vars_dict[inp["name"]] = str(inp["default"])
            else:
                console.print(
                    f"[red]✗ Missing required input: [bold]{inp['name']}[/bold][/red]\n"
                    f"  Use [bold]--var {inp['name']}=...[/bold] to provide it."
                )
                raise typer.Exit(1)

    # Render skill assets
    try:
        rendered = _skill_mod.render_skill_prompt(name, version)
    except Exception as e:
        console.print(f"[red]✗ Failed to render skill: {e}[/red]")
        raise typer.Exit(1)

    # Build messages
    from harness_kit.llm import LLMConfig, build_messages, call_llm

    cfg = read_config()
    llm_config = LLMConfig.from_harness_config(cfg, overrides={"model": model} if model else {})

    messages = build_messages(skill_data, rendered, vars_dict)

    if dry_run:
        console.print("\n[bold cyan]── Assembled Messages (dry-run) ──[/bold cyan]")
        for msg in messages:
            role_color = "green" if msg["role"] == "system" else "blue"
            console.print(f"\n[{role_color}][{msg['role'].upper()}][/{role_color}]")
            console.print(msg["content"])
        console.print(f"\n[dim]Model: {llm_config.model}[/dim]")
        return

    if not llm_config.api_key:
        console.print(
            "[red]✗ No API key found.[/red] "
            "Set [bold]OPENAI_API_KEY[/bold] environment variable or configure [cyan].harness/config.yaml[/cyan]."
        )
        raise typer.Exit(1)

    # Call LLM
    console.print(f"[dim]Calling [bold]{llm_config.model}[/bold] for skill [bold]{name}[/bold]…[/dim]")
    output_content = ""
    call_status = "success"
    call_error: str | None = None

    try:
        if stream:
            import time as _time
            t0 = _time.perf_counter()
            chunks: list[str] = []
            console.print("\n[bold cyan]── Output ──[/bold cyan]")
            for chunk in call_llm(messages, llm_config, stream=True):
                console.print(chunk, end="", highlight=False)
                chunks.append(chunk)
            console.print()
            output_content = "".join(chunks)
            llm_resp_duration = _time.perf_counter() - t0
            llm_resp_model = llm_config.model
            llm_resp_input_tokens = 0
            llm_resp_output_tokens = 0
        else:
            resp = call_llm(messages, llm_config, stream=False)
            output_content = resp.content
            llm_resp_duration = resp.duration
            llm_resp_model = resp.model
            llm_resp_input_tokens = resp.input_tokens
            llm_resp_output_tokens = resp.output_tokens
            console.print("\n[bold cyan]── Output ──[/bold cyan]")
            console.print(output_content)
            console.print(
                f"\n[dim]Model: {resp.model} | "
                f"Tokens: {resp.input_tokens}↑ {resp.output_tokens}↓ | "
                f"Duration: {resp.duration:.2f}s[/dim]"
            )
    except Exception as e:
        call_status = "error"
        call_error = str(e)
        console.print(f"[red]✗ LLM call failed: {e}[/red]")
        _call_logger_mod.log_call(
            skill=name,
            model=llm_config.model,
            input_tokens=0,
            output_tokens=0,
            duration=0.0,
            cost=0.0,
            status="error",
            error=call_error,
            inputs=vars_dict,
        )
        raise typer.Exit(1)

    # Apply hard rules if output available — collect structured violation data
    violations_data: list[dict] = []
    if output_content and output_content != "[streamed]":
        rule_names = []
        assets = skill_data.get("assets") or {}
        for rref in (assets.get("rules") or []):
            rname, _ = _skill_mod._parse_asset_ref(str(rref))
            rule_names.append(rname)

        for rname in rule_names:
            try:
                check_result = _rule_mod.check_rule_by_name(rname, output_content)
                if check_result.triggered and check_result.rule_type == "hard":
                    violations_data.append({
                        "rule": check_result.rule_name,
                        "type": "hard",
                        "matches": check_result.matches,
                        "fix_hint": check_result.fix_hint or "",
                    })
            except Exception:
                pass

    if violations_data:
        console.print("\n[bold yellow]── Rule Violations ──[/bold yellow]")
        for v in violations_data:
            console.print(
                f"  [yellow]⚠[/yellow] [hard] {v['rule']}: "
                f"{v['fix_hint'] or 'Rule violated'} (matches: {v['matches']})"
            )
        call_status = "rule_violation"
        _call_logger_mod.log_call(
            skill=name,
            model=llm_resp_model,
            input_tokens=llm_resp_input_tokens,
            output_tokens=llm_resp_output_tokens,
            duration=llm_resp_duration,
            cost=_cost_tracker_mod.estimate_cost(llm_resp_model, llm_resp_input_tokens, llm_resp_output_tokens),
            status=call_status,
            inputs=vars_dict,
            output=output_content,
            violations=violations_data,
        )
        if check_rules == "strict":
            raise typer.Exit(1)
        # lenient: warn but continue — log already written above
        return

    # Log successful call (no violations)
    _call_logger_mod.log_call(
        skill=name,
        model=llm_resp_model,
        input_tokens=llm_resp_input_tokens,
        output_tokens=llm_resp_output_tokens,
        duration=llm_resp_duration,
        cost=_cost_tracker_mod.estimate_cost(llm_resp_model, llm_resp_input_tokens, llm_resp_output_tokens),
        status=call_status,
        inputs=vars_dict,
        output=output_content,
    )


# ---------------------------------------------------------------------------
# skill tag
# ---------------------------------------------------------------------------


@skill_app.command("tag")
def skill_tag(
    name: str = typer.Argument(..., help="Skill name."),
    tag_name: str = typer.Option(..., "--name", "-n", help="Tag alias name (e.g. 'production')."),
    version: Optional[str] = typer.Option(None, "--version", "-v", help="Version to tag (default: current)."),
) -> None:
    """Create a tag alias for a skill version (e.g. 'production')."""
    _require_init()

    try:
        tagged_version = _skill_mod.tag_skill(name, tag_name, version)
    except FileNotFoundError as e:
        console.print(f"[red]✗ {e}[/red]")
        raise typer.Exit(1)

    console.print(
        f"[green]✓ Tagged[/green] [bold]{name}[/bold]@[cyan]{tagged_version}[/cyan] "
        f"→ [bold yellow]{tag_name}[/bold yellow]"
    )


# ---------------------------------------------------------------------------
# skill clone
# ---------------------------------------------------------------------------


@skill_app.command("clone")
def skill_clone(
    name: str = typer.Argument(..., help="Source skill name."),
    new_name: str = typer.Argument(..., help="New skill name."),
) -> None:
    """Clone a skill to a new name, resetting to v0.0.1."""
    _require_init()

    try:
        _skill_mod.clone_skill(name, new_name)
    except FileNotFoundError as e:
        console.print(f"[red]✗ {e}[/red]")
        raise typer.Exit(1)
    except FileExistsError as e:
        console.print(f"[red]✗ {e}[/red]")
        raise typer.Exit(1)

    console.print(
        f"[green]✓ Cloned[/green] [bold]{name}[/bold] → [bold]{new_name}[/bold] "
        f"([cyan]v0.0.1[/cyan])"
    )


# ---------------------------------------------------------------------------
# skill deps
# ---------------------------------------------------------------------------


@skill_app.command("deps")
def skill_deps(
    ref: str = typer.Argument(..., help="Skill name or name@version."),
) -> None:
    """List all asset dependencies of a skill."""
    _require_init()
    name, version = _parse_name_version(ref)

    try:
        deps = _skill_mod.get_skill_deps(name, version)
    except FileNotFoundError as e:
        console.print(f"[red]✗ {e}[/red]")
        raise typer.Exit(1)

    total = sum(len(v) for v in deps.values())
    if total == 0:
        console.print(f"[dim]Skill [bold]{ref}[/bold] has no asset dependencies.[/dim]")
        return

    console.print(f"\n[bold cyan]Dependencies of [bold]{ref}[/bold]:[/bold cyan]")

    if deps["prompts"]:
        console.print("\n[bold]Prompts:[/bold]")
        for r in deps["prompts"]:
            console.print(f"  • [cyan]{r}[/cyan]")

    if deps["schemas"]:
        console.print("\n[bold]Schemas:[/bold]")
        for r in deps["schemas"]:
            console.print(f"  • [cyan]{r}[/cyan]")

    if deps["rules"]:
        console.print("\n[bold]Rules:[/bold]")
        for r in deps["rules"]:
            console.print(f"  • [cyan]{r}[/cyan]")

    if deps["context"]:
        console.print("\n[bold]Context:[/bold]")
        for r in deps["context"]:
            console.print(f"  • [cyan]{r}[/cyan]")

    console.print(f"\n[dim]Total: {total} dependency(ies)[/dim]")





@logs_app.command("tail")
def logs_tail(
    n: int = typer.Option(20, "--n", "-n", help="Number of recent records to show."),
    since: Optional[str] = typer.Option(None, "--since", help="Only show records within this window (e.g. '1d', '2h', '30m')."),
) -> None:
    """Show the most recent LLM call log entries."""
    _require_init()
    records = _call_logger_mod.tail_logs(n=n, since=since)
    if not records:
        console.print("[dim]No call logs found.[/dim]")
        return

    table = Table(title="Recent LLM Calls", show_lines=False)
    table.add_column("Timestamp", style="dim", no_wrap=True)
    table.add_column("Skill", style="cyan")
    table.add_column("Model", style="blue")
    table.add_column("Status", style="bold")
    table.add_column("Tokens ↑/↓", justify="right")
    table.add_column("Cost (USD)", justify="right")
    table.add_column("Duration", justify="right")

    for rec in records:
        status = rec.get("status", "?")
        status_style = "green" if status == "success" else "red" if status == "error" else "yellow"
        ts = rec.get("timestamp", "")[:19].replace("T", " ")
        tokens = f"{rec.get('input_tokens', 0)} / {rec.get('output_tokens', 0)}"
        cost_val = rec.get("cost")
        cost_str = f"${cost_val:.4f}" if cost_val is not None else "-"
        duration = f"{rec.get('duration', 0):.2f}s"
        table.add_row(
            ts,
            rec.get("skill", "?"),
            rec.get("model", "?"),
            f"[{status_style}]{status}[/{status_style}]",
            tokens,
            cost_str,
            duration,
        )
    console.print(table)


@logs_app.command("search")
def logs_search(
    skill: Optional[str] = typer.Option(None, "--skill", help="Filter by skill name."),
    status: Optional[str] = typer.Option(None, "--status", help="Filter by status (success/error)."),
    since: Optional[str] = typer.Option(None, "--since", help="Only show records within this window (e.g. '1d', '2h', '30m')."),
    limit: int = typer.Option(50, "--limit", "-l", help="Maximum number of results."),
) -> None:
    """Search call logs with optional filters."""
    _require_init()
    records = _call_logger_mod.search_logs(skill=skill, status=status, since=since, limit=limit)
    if not records:
        console.print("[dim]No matching call logs found.[/dim]")
        return

    table = Table(title=f"Call Logs (skill={skill or '*'}, status={status or '*'}, since={since or 'all'})", show_lines=False)
    table.add_column("Timestamp", style="dim", no_wrap=True)
    table.add_column("Skill", style="cyan")
    table.add_column("Model", style="blue")
    table.add_column("Status", style="bold")
    table.add_column("Tokens ↑/↓", justify="right")
    table.add_column("Cost (USD)", justify="right")
    table.add_column("Duration", justify="right")

    for rec in records:
        status_val = rec.get("status", "?")
        status_style = "green" if status_val == "success" else "red" if status_val == "error" else "yellow"
        ts = rec.get("timestamp", "")[:19].replace("T", " ")
        tokens = f"{rec.get('input_tokens', 0)} / {rec.get('output_tokens', 0)}"
        cost_val = rec.get("cost")
        cost_str = f"${cost_val:.4f}" if cost_val is not None else "-"
        duration = f"{rec.get('duration', 0):.2f}s"
        table.add_row(
            ts,
            rec.get("skill", "?"),
            rec.get("model", "?"),
            f"[{status_style}]{status_val}[/{status_style}]",
            tokens,
            cost_str,
            duration,
        )
    console.print(table)


@logs_app.command("export")
def logs_export(
    fmt: str = typer.Option("csv", "--format", "-f", help="Export format: csv or jsonl."),
    since: Optional[str] = typer.Option(None, "--since", help="Only export records within this window (e.g. '7d', '2h')."),
    skill: Optional[str] = typer.Option(None, "--skill", help="Filter by skill name."),
    output: Optional[Path] = typer.Option(None, "--output", "-o", help="Write to file instead of stdout."),
) -> None:
    """Export call logs as CSV or JSON Lines."""
    _require_init()
    if fmt not in ("csv", "jsonl"):
        console.print("[red]Error:[/red] --format must be 'csv' or 'jsonl'.")
        raise typer.Exit(1)
    data = _call_logger_mod.export_logs(since=since, skill=skill, fmt=fmt)
    if not data:
        console.print("[dim]No call logs to export.[/dim]")
        return
    if output:
        output.write_text(data, encoding="utf-8")
        console.print(f"[green]Exported {len(data.splitlines())} records to {output}[/green]")
    else:
        # Print plain text (no Rich markup so the output is machine-readable)
        print(data, end="")


# ---------------------------------------------------------------------------
# harness create
# ---------------------------------------------------------------------------


@harness_app.command("create")
def harness_create(
    name: str = typer.Argument(..., help="Harness name (identifier)."),
    file: Optional[Path] = typer.Option(None, "--file", "-f", help="Load harness definition from YAML file."),
    description: str = typer.Option("", "--description", "-d", help="Short description."),
    skills: str = typer.Option("", "--skills", "-s", help="Comma-separated skill refs (e.g. skill1@v0.1.0,skill2)."),
    model_name: str = typer.Option("gpt-4o", "--model", help="LLM model name."),
    provider: str = typer.Option("openai", "--provider", help="LLM provider."),
    temperature: float = typer.Option(0.7, "--temperature", help="Sampling temperature."),
    max_tokens: int = typer.Option(2000, "--max-tokens", help="Max output tokens."),
    memory_scope: str = typer.Option("session", "--memory-scope", help="Memory scope: session/harness/global."),
    max_turns: int = typer.Option(10, "--max-turns", help="Max conversation turns before compressing."),
    context_budget: int = typer.Option(4000, "--context-budget", help="Context token budget."),
    changelog: str = typer.Option("", "--changelog", help="Changelog note for this version."),
    eval_suite: str = typer.Option("", "--eval-suite", help="Bind a test suite name to this harness (run with eval run)."),
) -> None:
    """Create or update a harness. Accepts --file <yaml> or individual options."""
    _require_init()

    if file:
        if not file.exists():
            console.print(f"[red]✗ File not found:[/red] {file}")
            raise typer.Exit(1)
        with file.open("r", encoding="utf-8") as f:
            data = yaml.safe_load(f)
        if not isinstance(data, dict):
            console.print("[red]✗ YAML file must contain a mapping.[/red]")
            raise typer.Exit(1)
        # Override name from argument if provided
        data["name"] = name
        if eval_suite:
            data["eval_suite"] = eval_suite
        errors = _harness_mod._validate_harness_data(data)
        if errors:
            console.print("[red]✗ Harness definition errors:[/red]")
            for e in errors:
                console.print(f"  • {e}")
            raise typer.Exit(1)
        version, is_new = _harness_mod.save_harness_from_dict(data)
    else:
        skill_list = [s.strip() for s in skills.split(",") if s.strip()] if skills else []
        data = {
            "name": name,
            "description": description,
            "skills": skill_list,
            "model": {
                "provider": provider,
                "name": model_name,
                "temperature": temperature,
                "max_tokens": max_tokens,
            },
            "memory": {
                "scope": memory_scope,
                "max_turns": max_turns,
            },
            "constraints": {},
            "context_budget": context_budget,
            "changelog": changelog,
        }
        if eval_suite:
            data["eval_suite"] = eval_suite
        errors = _harness_mod._validate_harness_data(data)
        if errors:
            console.print("[red]✗ Harness definition errors:[/red]")
            for e in errors:
                console.print(f"  • {e}")
            raise typer.Exit(1)
        version, is_new = _harness_mod.save_harness_from_dict(data)

    action = "[green]✓ Created[/green]" if is_new else "[blue]↑ Updated[/blue]"
    console.print(f"{action} harness [bold]{name}[/bold] → [cyan]{version}[/cyan]")
    if eval_suite:
        console.print(f"  [dim]eval-suite bound: {eval_suite}[/dim]")


# ---------------------------------------------------------------------------
# harness show
# ---------------------------------------------------------------------------


@harness_app.command("show")
def harness_show(
    ref: str = typer.Argument(..., help="Harness name or name@version."),
) -> None:
    """Show a harness definition."""
    _require_init()
    name, version = _parse_name_version(ref)
    try:
        data = _harness_mod.load_harness(name, version)
    except FileNotFoundError as e:
        console.print(f"[red]✗ {e}[/red]")
        raise typer.Exit(1)

    console.print(f"\n[bold cyan]{data['name']}[/bold cyan] [dim]{data['version']}[/dim]")
    if data.get("description"):
        console.print(f"[dim]{data['description']}[/dim]\n")

    # Skills
    skills = data.get("skills") or []
    if skills:
        console.print("[bold]Skills:[/bold]")
        for s in skills:
            console.print(f"  • [cyan]{s}[/cyan]")

    # Model
    model = data.get("model") or {}
    console.print("\n[bold]Model:[/bold]")
    for k, v in model.items():
        console.print(f"  [dim]{k}:[/dim] {v}")

    # Memory
    memory = data.get("memory") or {}
    console.print("\n[bold]Memory:[/bold]")
    for k, v in memory.items():
        console.print(f"  [dim]{k}:[/dim] {v}")

    # Constraints
    constraints = data.get("constraints") or {}
    if constraints:
        console.print("\n[bold]Constraints:[/bold]")
        for k, v in constraints.items():
            console.print(f"  [dim]{k}:[/dim] {v}")

    # Budget & metadata
    console.print(f"\n[dim]context_budget:[/dim] {data.get('context_budget', 4000)} tokens")
    console.print(f"[dim]created_at:[/dim] {data.get('created_at', 'N/A')}")
    if data.get("changelog"):
        console.print(f"[dim]changelog:[/dim] {data['changelog']}")


# ---------------------------------------------------------------------------
# harness list
# ---------------------------------------------------------------------------


@harness_app.command("list")
def harness_list() -> None:
    """List all harnesses."""
    _require_init()
    harnesses = _harness_mod.list_harnesses()
    if not harnesses:
        console.print("[dim]No harnesses found. Use [bold]harnesskit harness create[/bold] to create one.[/dim]")
        return

    table = Table(title="Harnesses", show_lines=False)
    table.add_column("Name", style="bold cyan")
    table.add_column("Version", style="dim")
    table.add_column("Skills", justify="right")
    table.add_column("Model")
    table.add_column("Memory Scope")
    table.add_column("Description")

    for h in harnesses:
        skill_count = str(len(h.get("skills") or []))
        model_name = (h.get("model") or {}).get("name", "?")
        memory_scope = (h.get("memory") or {}).get("scope", "?")
        table.add_row(
            h.get("name", "?"),
            h.get("version", "?"),
            skill_count,
            model_name,
            memory_scope,
            h.get("description", ""),
        )
    console.print(table)


# ---------------------------------------------------------------------------
# harness diff
# ---------------------------------------------------------------------------


@harness_app.command("diff")
def harness_diff(
    ref_a: str = typer.Argument(..., help="First harness ref (name@version or name)."),
    ref_b: str = typer.Argument(..., help="Second harness ref (name@version or name)."),
) -> None:
    """Show diff between two harness versions."""
    _require_init()
    name_a, ver_a = _parse_name_version(ref_a)
    name_b, ver_b = _parse_name_version(ref_b)
    try:
        lines = _harness_mod.diff_harnesses(name_a, ver_a, name_b, ver_b)
    except FileNotFoundError as e:
        console.print(f"[red]✗ {e}[/red]")
        raise typer.Exit(1)

    if not lines:
        console.print("[dim]No differences found.[/dim]")
        return

    for line in lines:
        line = line.rstrip("\n")
        if line.startswith("+++") or line.startswith("---"):
            console.print(f"[bold]{line}[/bold]")
        elif line.startswith("+"):
            console.print(f"[green]{line}[/green]")
        elif line.startswith("-"):
            console.print(f"[red]{line}[/red]")
        elif line.startswith("@@"):
            console.print(f"[cyan]{line}[/cyan]")
        else:
            console.print(line)


# ---------------------------------------------------------------------------
# harness clone
# ---------------------------------------------------------------------------


@harness_app.command("clone")
def harness_clone(
    name: str = typer.Argument(..., help="Source harness name."),
    new_name: str = typer.Argument(..., help="New harness name."),
) -> None:
    """Clone a harness to a new name (resets version to v0.0.1)."""
    _require_init()
    try:
        _harness_mod.clone_harness(name, new_name)
    except FileNotFoundError as e:
        console.print(f"[red]✗ {e}[/red]")
        raise typer.Exit(1)
    except FileExistsError as e:
        console.print(f"[red]✗ {e}[/red]")
        raise typer.Exit(1)
    console.print(f"[green]✓ Cloned[/green] [bold]{name}[/bold] → [bold]{new_name}[/bold] [dim](v0.0.1)[/dim]")


# ---------------------------------------------------------------------------
# harness validate
# ---------------------------------------------------------------------------


@harness_app.command("validate")
def harness_validate(
    ref: str = typer.Argument(..., help="Harness name or name@version."),
) -> None:
    """Validate that all skill references in a harness exist."""
    _require_init()
    name, version = _parse_name_version(ref)
    errors = _harness_mod.validate_harness_references(name, version)
    if not errors:
        console.print(f"[green]✓ All references in [bold]{ref}[/bold] are valid.[/green]")
    else:
        console.print(f"[red]✗ Found {len(errors)} broken reference(s) in [bold]{ref}[/bold]:[/red]")
        for e in errors:
            console.print(f"  • {e}")
        raise typer.Exit(1)


# ---------------------------------------------------------------------------
# harness delete
# ---------------------------------------------------------------------------


@harness_app.command("delete")
def harness_delete(
    ref: str = typer.Argument(..., help="Harness name or name@version."),
    yes: bool = typer.Option(False, "--yes", "-y", help="Skip confirmation prompt."),
) -> None:
    """Delete a harness or a specific version."""
    _require_init()
    name, version = _parse_name_version(ref)

    target = f"harness [bold]{name}[/bold]"
    if version:
        target += f" version [bold]{version}[/bold]"
    else:
        target += " [dim](all versions)[/dim]"

    if not yes:
        confirmed = typer.confirm(f"Delete {name}{'@' + version if version else ''}?")
        if not confirmed:
            console.print("[dim]Aborted.[/dim]")
            raise typer.Exit(0)

    try:
        _harness_mod.delete_harness(name, version)
    except FileNotFoundError as e:
        console.print(f"[red]✗ {e}[/red]")
        raise typer.Exit(1)

    console.print(f"[green]✓ Deleted[/green] {target}")


# ---------------------------------------------------------------------------
# harness run
# ---------------------------------------------------------------------------


def _estimate_tokens(char_count: int) -> int:
    """Rough token estimate: ~4 characters per token."""
    return max(1, char_count // 4)


@harness_app.command("run")
def harness_run(
    ref: str = typer.Argument(..., help="Harness name or name@version."),
    skill_name: Optional[str] = typer.Option(
        None, "--skill", "-s",
        help="Which skill in the harness to run. Required when harness has multiple skills.",
    ),
    var: list[str] = typer.Option(
        [], "--var", "-v",
        help="Input variable as key=value. Can be repeated.",
    ),
    model: Optional[str] = typer.Option(None, "--model", "-m", help="Override model."),
    stream: bool = typer.Option(False, "--stream", help="Stream output token-by-token."),
    check_rules: str = typer.Option(
        "lenient",
        "--check-rules",
        help="Rule check mode: 'strict' (fail on hard rule violation) or 'lenient' (warn only).",
    ),
    dry_run: bool = typer.Option(False, "--dry-run", help="Show assembled prompt without calling LLM."),
    no_memory: bool = typer.Option(False, "--no-memory", help="Disable memory persistence for this run."),
) -> None:
    """Run a harness: load config, resolve skills, manage context budget, call LLM."""
    _require_init()
    hname, hversion = _parse_name_version(ref)

    # Load harness
    try:
        harness_data = _harness_mod.load_harness(hname, hversion)
    except FileNotFoundError as e:
        console.print(f"[red]✗ {e}[/red]")
        raise typer.Exit(1)

    skills_refs = harness_data.get("skills") or []
    context_budget = harness_data.get("context_budget", 4000)
    harness_model_cfg = harness_data.get("model") or {}
    harness_version = harness_data.get("version", "?")

    # Load memory
    mem_config = harness_data.get("memory") or {}
    mem_scope = mem_config.get("scope", "session")
    mem_max_turns = int(mem_config.get("max_turns", 10))
    if no_memory:
        mem_scope = "session"  # treat as ephemeral when --no-memory
    mem_data = _memory_mod.load_memory(mem_scope, hname)

    console.print(
        f"\n[bold cyan]Harness:[/bold cyan] [bold]{hname}[/bold] "
        f"[dim]{harness_version}[/dim] — {harness_data.get('description', '')}"
    )
    console.print(
        f"[dim]Context budget: {context_budget} tokens | "
        f"Model: {harness_model_cfg.get('name', 'gpt-4o')} | "
        f"Skills: {len(skills_refs)}[/dim]\n"
    )

    # Determine which skill to run
    if not skills_refs:
        console.print("[red]✗ Harness has no skills defined.[/red]")
        raise typer.Exit(1)

    if len(skills_refs) == 1:
        resolved_skill_ref = skills_refs[0]
    else:
        if not skill_name:
            console.print(
                f"[yellow]⚠ Harness has {len(skills_refs)} skills. "
                f"Use [bold]--skill <name>[/bold] to select one:[/yellow]"
            )
            for sr in skills_refs:
                console.print(f"  • [cyan]{sr}[/cyan]")
            raise typer.Exit(1)
        # Find matching ref
        resolved_skill_ref = None
        for sr in skills_refs:
            sr_name, _ = _harness_mod._parse_skill_ref(str(sr))
            if sr_name == skill_name:
                resolved_skill_ref = sr
                break
        if resolved_skill_ref is None:
            console.print(
                f"[red]✗ Skill [bold]{skill_name}[/bold] not found in harness "
                f"[bold]{hname}[/bold].[/red]"
            )
            console.print(f"  Available skills: {', '.join(str(s) for s in skills_refs)}")
            raise typer.Exit(1)

    s_name, s_version = _harness_mod._parse_skill_ref(str(resolved_skill_ref))
    console.print(f"[dim]Running skill: [bold]{resolved_skill_ref}[/bold][/dim]\n")

    # Load skill
    try:
        skill_data = _skill_mod.load_skill(s_name, s_version)
    except FileNotFoundError as e:
        console.print(f"[red]✗ {e}[/red]")
        raise typer.Exit(1)

    # Parse --var key=value pairs
    vars_dict: dict[str, str] = {}
    for v in var:
        if "=" not in v:
            console.print(f"[red]✗ Invalid --var format: [bold]{v}[/bold] (expected key=value)[/red]")
            raise typer.Exit(1)
        k, val = v.split("=", 1)
        vars_dict[k.strip()] = val

    # Validate required inputs from skill
    for inp in skill_data.get("inputs") or []:
        if inp.get("required", True) and inp.get("name") not in vars_dict:
            if inp.get("default") is not None:
                vars_dict[inp["name"]] = str(inp["default"])
            else:
                console.print(
                    f"[red]✗ Missing required input: [bold]{inp['name']}[/bold][/red]\n"
                    f"  Use [bold]--var {inp['name']}=...[/bold] to provide it."
                )
                raise typer.Exit(1)

    # Render skill assets
    try:
        rendered = _skill_mod.render_skill_prompt(s_name, s_version)
    except Exception as e:
        console.print(f"[red]✗ Failed to render skill: {e}[/red]")
        raise typer.Exit(1)

    # Build messages
    from harness_kit.llm import LLMConfig, build_messages, call_llm

    cfg = read_config()

    # Merge harness model config with global config, then apply CLI overrides
    harness_overrides: dict = {}
    if harness_model_cfg.get("name"):
        harness_overrides["model"] = harness_model_cfg["name"]
    if harness_model_cfg.get("temperature") is not None:
        harness_overrides["temperature"] = harness_model_cfg["temperature"]
    if harness_model_cfg.get("max_tokens"):
        harness_overrides["max_tokens"] = harness_model_cfg["max_tokens"]
    if model:
        harness_overrides["model"] = model  # CLI --model takes priority

    llm_config = LLMConfig.from_harness_config(cfg, overrides=harness_overrides)

    messages = build_messages(skill_data, rendered, vars_dict)

    # Inject conversation history from memory between system message and user message
    history = _memory_mod.get_history_messages(mem_data)
    if history:
        # Insert history after the system message (if present) and before the last user msg
        if messages and messages[0]["role"] == "system":
            messages = [messages[0]] + history + messages[1:]
        else:
            messages = history + messages
        if mem_scope != "session":
            console.print(f"[dim]Memory: {len(history)} turn(s) loaded (scope: {mem_scope})[/dim]")

    # Context budget check
    total_chars = sum(len(m.get("content", "")) for m in messages)
    estimated_tokens = _estimate_tokens(total_chars)
    if estimated_tokens > context_budget:
        console.print(
            f"[yellow]⚠ Estimated prompt tokens (~{estimated_tokens}) exceed context_budget "
            f"({context_budget}). Consider reducing input size or increasing context_budget.[/yellow]"
        )

    if dry_run:
        console.print("[bold cyan]── Assembled Messages (dry-run) ──[/bold cyan]")
        for msg in messages:
            role_color = "green" if msg["role"] == "system" else "blue"
            console.print(f"\n[{role_color}][{msg['role'].upper()}][/{role_color}]")
            console.print(msg["content"])
        console.print(
            f"\n[dim]Model: {llm_config.model} | "
            f"Estimated tokens: ~{estimated_tokens} / {context_budget} budget[/dim]"
        )
        return

    if not llm_config.api_key:
        console.print(
            "[red]✗ No API key found.[/red] "
            "Set [bold]OPENAI_API_KEY[/bold] environment variable or configure [cyan].harness/config.yaml[/cyan]."
        )
        raise typer.Exit(1)

    # Merge harness constraint rules with skill rules for checking
    harness_constraints = harness_data.get("constraints") or {}
    harness_rules = harness_constraints.get("rules") or []

    # Call LLM
    console.print(f"[dim]Calling [bold]{llm_config.model}[/bold]…[/dim]")
    output_content = ""
    call_status = "success"
    call_error: str | None = None

    try:
        if stream:
            import time as _time
            t0 = _time.perf_counter()
            chunks: list[str] = []
            console.print("\n[bold cyan]── Output ──[/bold cyan]")
            for chunk in call_llm(messages, llm_config, stream=True):
                console.print(chunk, end="", highlight=False)
                chunks.append(chunk)
            console.print()
            output_content = "".join(chunks)
            llm_resp_duration = _time.perf_counter() - t0
            llm_resp_model = llm_config.model
            llm_resp_input_tokens = 0
            llm_resp_output_tokens = 0
        else:
            resp = call_llm(messages, llm_config, stream=False)
            output_content = resp.content
            llm_resp_duration = resp.duration
            llm_resp_model = resp.model
            llm_resp_input_tokens = resp.input_tokens
            llm_resp_output_tokens = resp.output_tokens
            console.print("\n[bold cyan]── Output ──[/bold cyan]")
            console.print(output_content)
            console.print(
                f"\n[dim]Model: {resp.model} | "
                f"Tokens: {resp.input_tokens}↑ {resp.output_tokens}↓ | "
                f"Duration: {resp.duration:.2f}s[/dim]"
            )
    except Exception as e:
        call_status = "error"
        call_error = str(e)
        console.print(f"[red]✗ LLM call failed: {e}[/red]")
        _call_logger_mod.log_call(
            skill=f"{hname}/{s_name}",
            model=llm_config.model,
            input_tokens=0,
            output_tokens=0,
            duration=0.0,
            cost=0.0,
            status="error",
            error=call_error,
            inputs=vars_dict,
        )
        raise typer.Exit(1)

    # Apply rules: skill rules + harness constraint rules
    violations_data: list[dict] = []
    if output_content:
        rule_names: list[str] = []
        assets = skill_data.get("assets") or {}
        for rref in (assets.get("rules") or []):
            rname, _ = _skill_mod._parse_asset_ref(str(rref))
            rule_names.append(rname)
        for rname in harness_rules:
            if rname not in rule_names:
                rule_names.append(str(rname))

        for rname in rule_names:
            try:
                check_result = _rule_mod.check_rule_by_name(rname, output_content)
                if check_result.triggered and check_result.rule_type == "hard":
                    violations_data.append({
                        "rule": check_result.rule_name,
                        "type": "hard",
                        "matches": check_result.matches,
                        "fix_hint": check_result.fix_hint or "",
                    })
            except Exception:
                pass

    if violations_data:
        console.print("\n[bold yellow]── Rule Violations ──[/bold yellow]")
        for v in violations_data:
            console.print(
                f"  [yellow]⚠[/yellow] [hard] {v['rule']}: "
                f"{v['fix_hint'] or 'Rule violated'} (matches: {v['matches']})"
            )
        call_status = "rule_violation"
        _call_logger_mod.log_call(
            skill=f"{hname}/{s_name}",
            model=llm_resp_model,
            input_tokens=llm_resp_input_tokens,
            output_tokens=llm_resp_output_tokens,
            duration=llm_resp_duration,
            cost=_cost_tracker_mod.estimate_cost(llm_resp_model, llm_resp_input_tokens, llm_resp_output_tokens),
            status=call_status,
            inputs=vars_dict,
            output=output_content,
            violations=violations_data,
        )
        if check_rules == "strict":
            raise typer.Exit(1)
        return

    # Log successful call
    _call_logger_mod.log_call(
        skill=f"{hname}/{s_name}",
        model=llm_resp_model,
        input_tokens=llm_resp_input_tokens,
        output_tokens=llm_resp_output_tokens,
        duration=llm_resp_duration,
        cost=_cost_tracker_mod.estimate_cost(llm_resp_model, llm_resp_input_tokens, llm_resp_output_tokens),
        status=call_status,
        inputs=vars_dict,
        output=output_content,
    )

    # Persist memory turn
    user_input = " ".join(f"{k}={v}" for k, v in vars_dict.items())
    _memory_mod.add_turn(mem_data, "user", user_input, tokens=llm_resp_input_tokens)
    _memory_mod.add_turn(mem_data, "assistant", output_content, tokens=llm_resp_output_tokens)
    _memory_mod.compress_memory(mem_data, mem_max_turns)
    _memory_mod.save_memory(mem_data, mem_scope, hname)


@app.callback()
def _main() -> None:
    """HarnessKit — manage AI Agent runtimes like code."""


# ---------------------------------------------------------------------------
# cost commands
# ---------------------------------------------------------------------------


@cost_app.command("report")
def cost_report_cmd(
    since: str = typer.Option("30d", "--since", "-s", help="Time window: 1d, 7d, 30d, etc."),
    group_by: str = typer.Option("skill", "--group-by", "-g", help="Group by: skill, model, or day."),
) -> None:
    """Show cost report grouped by skill, model, or day."""
    _require_init()
    report = _cost_tracker_mod.cost_report(since=since)
    total = report["total_cost"]
    calls = report["total_calls"]
    tokens = report["total_tokens"]

    console.print(f"\n[bold cyan]── Cost Report (last {since}) ──[/bold cyan]")
    console.print(
        f"Total: [bold green]${total:.4f}[/bold green]  "
        f"Calls: [bold]{calls}[/bold]  "
        f"Tokens: [bold]{tokens:,}[/bold]"
    )
    if calls > 0:
        console.print(f"Avg per call: [bold]${total/calls:.6f}[/bold]\n")

    if group_by == "model":
        data = report["by_model"]
        title = "Cost by Model"
    elif group_by == "day":
        # Convert daily_breakdown into the same format
        data = {
            date: {"cost": c, "calls": 0, "tokens": 0}
            for date, c in report["daily_breakdown"].items()
        }
        title = "Cost by Day"
    else:
        data = report["by_skill"]
        title = "Cost by Skill"

    if not data:
        console.print("[dim]No data found for the selected period.[/dim]")
        return

    table = Table(title=title, show_lines=False)
    table.add_column("Name", style="cyan")
    table.add_column("Cost (USD)", justify="right", style="green")
    if group_by != "day":
        table.add_column("Calls", justify="right")
        table.add_column("Tokens", justify="right")
        table.add_column("Avg/Call", justify="right")

    sorted_items = sorted(data.items(), key=lambda x: x[1].get("cost", 0.0), reverse=True)
    for name, stats in sorted_items:
        c = stats.get("cost", 0.0)
        n = stats.get("calls", 0)
        t = stats.get("tokens", 0)
        avg = f"${c/n:.6f}" if n > 0 else "-"
        if group_by == "day":
            table.add_row(name, f"${c:.4f}")
        else:
            table.add_row(name, f"${c:.4f}", str(n), f"{t:,}", avg)

    console.print(table)

    # Most expensive call
    top = report.get("most_expensive_call")
    if top and top.get("cost"):
        console.print(
            f"\n[bold]Most expensive call:[/bold] "
            f"[cyan]{top['skill']}[/cyan] via [blue]{top['model']}[/blue]  "
            f"[bold green]${top['cost']:.4f}[/bold green]  "
            f"[dim]{top['timestamp'][:19].replace('T', ' ')}[/dim]"
        )


@cost_app.command("breakdown")
def cost_breakdown_cmd(
    since: str = typer.Option("7d", "--since", "-s", help="Time window: 1d, 7d, 30d, etc."),
    skill: Optional[str] = typer.Option(None, "--skill", help="Filter by skill name."),
    limit: int = typer.Option(20, "--limit", "-n", help="Max number of calls to show."),
) -> None:
    """Show per-call cost breakdown (most expensive first)."""
    _require_init()
    from harness_kit.call_logger import search_logs
    records = search_logs(skill=skill, since=since, limit=10_000)
    if not records:
        console.print("[dim]No call logs found.[/dim]")
        return

    # Enrich with estimated cost if missing
    enriched = []
    for rec in records:
        cost_val = rec.get("cost")
        if cost_val is None:
            cost_val = _cost_tracker_mod.estimate_cost(
                rec.get("model", ""), rec.get("input_tokens", 0), rec.get("output_tokens", 0)
            ) or 0.0
        enriched.append((cost_val, rec))

    enriched.sort(key=lambda x: x[0], reverse=True)
    top_n = enriched[:limit]

    table = Table(title=f"Top {limit} Most Expensive Calls (last {since})", show_lines=False)
    table.add_column("Timestamp", style="dim", no_wrap=True)
    table.add_column("Skill", style="cyan")
    table.add_column("Model", style="blue")
    table.add_column("Cost (USD)", justify="right", style="green")
    table.add_column("Tokens ↑/↓", justify="right")
    table.add_column("Duration", justify="right")

    for cost_val, rec in top_n:
        ts = rec.get("timestamp", "")[:19].replace("T", " ")
        tokens = f"{rec.get('input_tokens', 0)} / {rec.get('output_tokens', 0)}"
        dur = f"{rec.get('duration', 0):.2f}s"
        table.add_row(ts, rec.get("skill", "?"), rec.get("model", "?"),
                      f"${cost_val:.4f}", tokens, dur)

    console.print(table)
    total_shown = sum(c for c, _ in top_n)
    console.print(f"\n[dim]Total shown: ${total_shown:.4f}[/dim]")


@cost_app.command("set-price")
def cost_set_price_cmd(
    model: str = typer.Argument(..., help="Model name (e.g. gpt-4o)."),
    input_price: float = typer.Option(..., "--input", help="Input price per 1K tokens (USD)."),
    output_price: float = typer.Option(..., "--output", help="Output price per 1K tokens (USD)."),
) -> None:
    """Set custom token pricing for a model in config."""
    _require_init()
    _cost_tracker_mod.set_model_price(model, input_price, output_price)
    console.print(
        f"[green]✓[/green] Price set for [cyan]{model}[/cyan]: "
        f"input=${input_price}/1K  output=${output_price}/1K"
    )


@cost_app.command("list-prices")
def cost_list_prices_cmd() -> None:
    """Show all model prices (built-in + user overrides)."""
    _require_init()
    prices = _cost_tracker_mod.get_model_prices()
    table = Table(title="Model Pricing (USD per 1K tokens)", show_lines=False)
    table.add_column("Model", style="cyan")
    table.add_column("Input $/1K", justify="right")
    table.add_column("Output $/1K", justify="right")
    for model, p in sorted(prices.items()):
        table.add_row(model, f"${p['input']:.5f}", f"${p['output']:.5f}")
    console.print(table)


# ---------------------------------------------------------------------------
# memory commands (appended after all other command groups so the module
# import of _memory_mod is already present)
# ---------------------------------------------------------------------------


@memory_app.command("show")
def memory_show(
    harness_name: str = typer.Argument(..., help="Harness name (or 'global')."),
    scope: str = typer.Option(
        "harness", "--scope", help="Memory scope: harness or global."
    ),
    limit: int = typer.Option(20, "--limit", "-n", help="Max number of turns to display."),
) -> None:
    """Show stored conversation history for a harness."""
    _require_init()
    data = _memory_mod.load_memory(scope, harness_name)
    turns = data.get("turns", [])
    meta = data.get("metadata", {})

    if not turns and not meta.get("summary"):
        console.print(f"[dim]No memory found for [bold]{harness_name}[/bold] (scope: {scope}).[/dim]")
        return

    if meta.get("summary"):
        console.print(f"\n[bold yellow]── Compressed History Summary ──[/bold yellow]")
        console.print(meta["summary"])

    if turns:
        console.print(f"\n[bold cyan]── Conversation Turns (last {min(limit, len(turns))}/{len(turns)}) ──[/bold cyan]")
        for t in turns[-limit:]:
            role_color = "green" if t["role"] == "assistant" else "blue"
            ts = t.get("timestamp", "")[:19]
            console.print(f"\n[{role_color}][{t['role'].upper()}][/{role_color}] [dim]{ts}[/dim]")
            console.print(t["content"])

    console.print(
        f"\n[dim]Total turns: {len(turns)} | Total tokens: {meta.get('total_tokens', 0)}[/dim]"
    )


@memory_app.command("list")
def memory_list() -> None:
    """List all persisted memory files."""
    _require_init()
    files = _memory_mod.list_memory_files()
    if not files:
        console.print("[dim]No memory files found.[/dim]")
        return

    table = Table(title="Memory Files", show_lines=False)
    table.add_column("Harness", style="cyan")
    table.add_column("Scope", style="dim")
    table.add_column("Turns", justify="right")
    table.add_column("Total Tokens", justify="right")
    table.add_column("Has Summary")

    for f in files:
        table.add_row(
            f["harness"],
            f["scope"],
            str(f["turns"]),
            str(f["total_tokens"]),
            "✓" if f["has_summary"] else "–",
        )
    console.print(table)


@memory_app.command("search")
def memory_search(
    harness_name: str = typer.Argument(..., help="Harness name (or 'global')."),
    keyword: str = typer.Argument(..., help="Search keyword."),
    scope: str = typer.Option("harness", "--scope", help="Memory scope: harness or global."),
) -> None:
    """Search conversation history by keyword."""
    _require_init()
    data = _memory_mod.load_memory(scope, harness_name)
    results = _memory_mod.search_memory(data, keyword)
    if not results:
        console.print(f"[dim]No turns matching '[bold]{keyword}[/bold]' found.[/dim]")
        return

    console.print(f"[bold cyan]{len(results)} turn(s) matching '{keyword}':[/bold cyan]\n")
    for t in results:
        role_color = "green" if t["role"] == "assistant" else "blue"
        ts = t.get("timestamp", "")[:19]
        console.print(f"[{role_color}][{t['role'].upper()}][/{role_color}] [dim]{ts}[/dim]")
        console.print(t["content"])
        console.print()


@memory_app.command("clear")
def memory_clear(
    harness_name: str = typer.Argument(..., help="Harness name (or 'global')."),
    scope: str = typer.Option("harness", "--scope", help="Memory scope: harness or global."),
    yes: bool = typer.Option(False, "--yes", "-y", help="Skip confirmation prompt."),
) -> None:
    """Clear persisted memory for a harness."""
    _require_init()
    if not yes:
        confirmed = typer.confirm(f"Clear memory for '{harness_name}' (scope: {scope})?")
        if not confirmed:
            console.print("[dim]Aborted.[/dim]")
            raise typer.Exit(0)
    removed = _memory_mod.clear_memory(scope, harness_name)
    if removed:
        console.print(f"[green]✓ Memory cleared for [bold]{harness_name}[/bold].[/green]")
    else:
        console.print(f"[dim]No memory file found for [bold]{harness_name}[/bold].[/dim]")



# ---------------------------------------------------------------------------
# agent commands
# ---------------------------------------------------------------------------


@agent_app.command("create")
def agent_create(
    name: str = typer.Argument(..., help="Agent name."),
    harness_ref: str = typer.Option(..., "--harness", "-H", help="Harness name or name@version."),
    identity_name: str = typer.Option("", "--identity-name", help="Display name for the agent."),
    identity_description: str = typer.Option("", "--description", "-d", help="Agent description."),
    memory_scope: str = typer.Option(
        "session", "--memory-scope",
        help="Memory scope: session / harness / global.",
    ),
    memory_persist: bool = typer.Option(False, "--persist", help="Persist memory across runs."),
    max_iterations: int = typer.Option(10, "--max-iterations", help="Max conversation turns."),
) -> None:
    """Create (or overwrite) an agent definition."""
    _require_init()

    # Validate harness ref exists
    if "@" in harness_ref:
        h_name, h_version = harness_ref.split("@", 1)
    else:
        h_name, h_version = harness_ref, None

    try:
        _harness_mod.load_harness(h_name, h_version)
    except FileNotFoundError as e:
        console.print(f"[red]✗ {e}[/red]")
        raise typer.Exit(1)

    is_new = _agent_mod.save_agent(
        name=name,
        harness_ref=harness_ref,
        identity_name=identity_name,
        identity_description=identity_description,
        memory_scope=memory_scope,
        memory_persist=memory_persist,
        max_iterations=max_iterations,
    )
    action = "Created" if is_new else "Updated"
    console.print(f"[green]✓ {action} agent [bold]{name}[/bold][/green]")
    console.print(f"  [dim]harness:[/dim] {harness_ref}")
    console.print(f"  [dim]memory scope:[/dim] {memory_scope} | [dim]persist:[/dim] {memory_persist}")
    console.print(f"  [dim]max_iterations:[/dim] {max_iterations}")


@agent_app.command("list")
def agent_list() -> None:
    """List all agents."""
    _require_init()
    agents = _agent_mod.list_agents()
    if not agents:
        console.print("[dim]No agents found.[/dim]")
        return

    table = Table(title="Agents", show_lines=False)
    table.add_column("Name", style="cyan bold")
    table.add_column("Harness", style="green")
    table.add_column("Identity")
    table.add_column("Memory Scope", style="dim")
    table.add_column("Max Iters", justify="right")

    for ag in agents:
        identity = ag.get("identity") or {}
        table.add_row(
            ag.get("name", ""),
            ag.get("harness", ""),
            identity.get("name", ""),
            (ag.get("memory") or {}).get("scope", "session"),
            str(ag.get("max_iterations", 10)),
        )
    console.print(table)


@agent_app.command("show")
def agent_show(
    name: str = typer.Argument(..., help="Agent name."),
) -> None:
    """Show full agent definition."""
    _require_init()
    try:
        data = _agent_mod.load_agent(name)
    except FileNotFoundError as e:
        console.print(f"[red]✗ {e}[/red]")
        raise typer.Exit(1)

    console.print(f"\n[bold cyan]Agent:[/bold cyan] [bold]{data['name']}[/bold]")
    identity = data.get("identity") or {}
    if identity.get("name"):
        console.print(f"  [dim]Display name:[/dim] {identity['name']}")
    if identity.get("description"):
        console.print(f"  [dim]Description:[/dim]  {identity['description']}")
    console.print(f"  [dim]Harness:[/dim]      {data.get('harness', '')}")
    mem = data.get("memory") or {}
    console.print(
        f"  [dim]Memory:[/dim]       scope={mem.get('scope', 'session')} "
        f"persist={mem.get('persist', False)}"
    )
    console.print(f"  [dim]Max iterations:[/dim] {data.get('max_iterations', 10)}")


@agent_app.command("delete")
def agent_delete(
    name: str = typer.Argument(..., help="Agent name."),
    yes: bool = typer.Option(False, "--yes", "-y", help="Skip confirmation."),
) -> None:
    """Delete an agent definition."""
    _require_init()
    if not yes:
        confirmed = typer.confirm(f"Delete agent '{name}'?")
        if not confirmed:
            console.print("[dim]Aborted.[/dim]")
            raise typer.Exit(0)
    try:
        _agent_mod.delete_agent(name)
    except FileNotFoundError as e:
        console.print(f"[red]✗ {e}[/red]")
        raise typer.Exit(1)
    console.print(f"[green]✓ Deleted agent [bold]{name}[/bold].[/green]")


@agent_app.command("run")
def agent_run(
    name: str = typer.Argument(..., help="Agent name."),
    model: Optional[str] = typer.Option(None, "--model", "-m", help="Override model."),
    stream: bool = typer.Option(False, "--stream", help="Stream output token-by-token."),
    no_memory: bool = typer.Option(False, "--no-memory", help="Disable memory for this session."),
) -> None:
    """Start an interactive conversation with an agent (REPL).

    Special commands:
      /reset   — clear conversation memory
      /save    — save conversation to a file
      /quit    — exit
    """
    _require_init()

    # Load agent definition
    try:
        agent_data = _agent_mod.load_agent(name)
    except FileNotFoundError as e:
        console.print(f"[red]✗ {e}[/red]")
        raise typer.Exit(1)

    harness_ref = agent_data.get("harness", "")
    if not harness_ref:
        console.print("[red]✗ Agent has no harness defined.[/red]")
        raise typer.Exit(1)

    identity = agent_data.get("identity") or {}
    display_name = identity.get("name") or name
    description = identity.get("description", "")
    max_iterations = int(agent_data.get("max_iterations", 10))

    # Parse harness ref
    if "@" in harness_ref:
        h_name, h_version = harness_ref.split("@", 1)
    else:
        h_name, h_version = harness_ref, None

    # Load harness
    try:
        harness_data = _harness_mod.load_harness(h_name, h_version)
    except FileNotFoundError as e:
        console.print(f"[red]✗ {e}[/red]")
        raise typer.Exit(1)

    # Determine memory scope
    agent_mem_cfg = agent_data.get("memory") or {}
    mem_scope = agent_mem_cfg.get("scope", "session")
    if no_memory:
        mem_scope = "session"

    # Harness model config
    harness_model_cfg = harness_data.get("model") or {}
    harness_overrides: dict = {}
    if harness_model_cfg.get("name"):
        harness_overrides["model"] = harness_model_cfg["name"]
    if harness_model_cfg.get("temperature") is not None:
        harness_overrides["temperature"] = harness_model_cfg["temperature"]
    if harness_model_cfg.get("max_tokens"):
        harness_overrides["max_tokens"] = harness_model_cfg["max_tokens"]
    if model:
        harness_overrides["model"] = model

    cfg = read_config()
    llm_config = LLMConfig.from_harness_config(cfg, overrides=harness_overrides)

    if not llm_config.api_key:
        console.print(
            "[red]✗ No API key found.[/red] "
            "Set [bold]OPENAI_API_KEY[/bold] or configure [cyan].harness/config.yaml[/cyan]."
        )
        raise typer.Exit(1)

    # Determine system prompt from harness skills
    skills_refs = harness_data.get("skills") or []
    system_prompt_parts: list[str] = []
    soft_rules_text: list[str] = []

    if skills_refs:
        # Pick the first skill as the "primary" skill for the session system prompt
        primary_ref = str(skills_refs[0])
        s_name, s_version = _harness_mod._parse_skill_ref(primary_ref)
        try:
            skill_data = _skill_mod.load_skill(s_name, s_version)
            rendered = _skill_mod.render_skill_prompt(s_name, s_version)
            if rendered.get("system"):
                system_prompt_parts.append(rendered["system"])
            # Collect soft rules for injection
            for rtext in (rendered.get("rules") or []):
                if rtext:
                    soft_rules_text.append(rtext)
        except Exception:
            pass  # skills are optional for agent conversation

    # Build persistent system prompt
    base_system = "\n\n".join(system_prompt_parts) if system_prompt_parts else (
        f"你是 {display_name}。" + (f" {description}" if description else "")
    )
    if soft_rules_text:
        base_system += "\n\n规则：\n" + "\n".join(soft_rules_text)

    # Load memory
    mem_max_turns = int((harness_data.get("memory") or {}).get("max_turns", max_iterations))
    mem_data = _memory_mod.load_memory(mem_scope, name)

    # Welcome banner
    console.print(f"\n[bold cyan]╔══ Agent: {display_name} ══[/bold cyan]")
    if description:
        console.print(f"[dim]{description}[/dim]")
    console.print(
        f"[dim]Harness: {harness_ref} | Model: {llm_config.model} | "
        f"Memory: {mem_scope}[/dim]"
    )
    console.print("[dim]Commands: /reset  /save  /quit[/dim]")
    console.print("[bold cyan]╚══════════════════════════════[/bold cyan]\n")

    harness_constraints = harness_data.get("constraints") or {}
    harness_rules = harness_constraints.get("rules") or []

    turn_count = 0

    while True:
        # Read user input
        try:
            user_input = console.input("[bold blue]You:[/bold blue] ")
        except (EOFError, KeyboardInterrupt):
            console.print("\n[dim]Interrupted. Goodbye![/dim]")
            break

        user_input = user_input.strip()
        if not user_input:
            continue

        # Handle special commands
        if user_input.lower() in ("/quit", "/exit", "/q"):
            console.print("[dim]Goodbye![/dim]")
            break

        if user_input.lower() == "/reset":
            mem_data = _memory_mod.load_memory("session", name)  # fresh empty memory
            if mem_scope != "session":
                _memory_mod.clear_memory(mem_scope, name)
            console.print("[green]✓ Memory reset.[/green]\n")
            turn_count = 0
            continue

        if user_input.lower() == "/save":
            saved_path = _agent_mod.save_conversation(name, mem_data)
            console.print(f"[green]✓ Conversation saved to [bold]{saved_path}[/bold][/green]\n")
            continue

        if user_input.lower().startswith("/save "):
            import os
            target = Path(user_input[6:].strip()).expanduser()
            saved_path = _agent_mod.save_conversation(name, mem_data, output_path=target)
            console.print(f"[green]✓ Conversation saved to [bold]{saved_path}[/bold][/green]\n")
            continue

        # Check max_iterations
        if turn_count >= max_iterations:
            console.print(
                f"[yellow]⚠ Max iterations ({max_iterations}) reached. "
                f"Use /reset to start a new conversation.[/yellow]"
            )
            continue

        # Compress memory if needed
        _memory_mod.compress_memory(mem_data, mem_max_turns, llm_config)

        # Build messages for this turn
        history = _memory_mod.get_history_messages(mem_data)
        messages: list[dict] = []
        if base_system:
            messages.append({"role": "system", "content": base_system})
        messages.extend(history)
        messages.append({"role": "user", "content": user_input})

        # Call LLM
        output_content = ""
        try:
            if stream:
                console.print("\n[bold green]Agent:[/bold green] ", end="")
                chunks: list[str] = []
                for chunk in call_llm(messages, llm_config, stream=True):
                    console.print(chunk, end="", highlight=False)
                    chunks.append(chunk)
                console.print()
                output_content = "".join(chunks)
                in_tokens = out_tokens = 0
            else:
                resp = call_llm(messages, llm_config, stream=False)
                output_content = resp.content
                in_tokens = resp.input_tokens
                out_tokens = resp.output_tokens
                console.print(f"\n[bold green]{display_name}:[/bold green]")
                console.print(output_content)
                console.print(
                    f"[dim]  {in_tokens}↑ {out_tokens}↓ tokens | {resp.duration:.2f}s[/dim]\n"
                )
        except Exception as e:
            console.print(f"[red]✗ LLM call failed: {e}[/red]\n")
            continue

        # Apply hard rules (harness-level)
        for rname in harness_rules:
            try:
                check_result = _rule_mod.check_rule_by_name(str(rname), output_content)
                if check_result.triggered and check_result.rule_type == "hard":
                    console.print(
                        f"[yellow]⚠ Hard rule violated: {rname}. "
                        f"{check_result.fix_hint or ''}[/yellow]"
                    )
            except Exception:
                pass

        # Update memory
        _memory_mod.add_turn(mem_data, "user", user_input, tokens=in_tokens if not stream else 0)
        _memory_mod.add_turn(mem_data, "assistant", output_content, tokens=out_tokens if not stream else 0)
        if mem_scope != "session":
            _memory_mod.save_memory(mem_data, mem_scope, name)

        turn_count += 1


@app.command()
def init() -> None:
    """Initialize a HarnessKit project in the current directory."""
    if is_initialized():
        console.print(
            f"[yellow]⚠ Already initialized[/yellow] — "
            f"[dim]{harness_dir()} already exists.[/dim]"
        )
        raise typer.Exit(0)

    init_harness()

    console.print("[green bold]✓ Initialized HarnessKit project[/green bold]\n")
    console.print("[bold]Created:[/bold]")
    console.print(f"  [cyan].harness/config.yaml[/cyan]")
    for sub in SUBDIRS:
        console.print(f"  [cyan].harness/{sub}/[/cyan]")

    cfg = read_config()
    console.print("\n[bold]Default config:[/bold]")
    for k, v in cfg.items():
        console.print(f"  [dim]{k}[/dim]: {v}")

    console.print(
        "\n[dim]Run [bold]harnesskit --help[/bold] to see available commands.[/dim]"
    )


def main() -> None:
    app()


# ---------------------------------------------------------------------------
# blueprint commands are appended below
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# blueprint create
# ---------------------------------------------------------------------------


@blueprint_app.command("create")
def blueprint_create(
    name: str = typer.Argument(..., help="Blueprint name (identifier)."),
    file: Optional[Path] = typer.Option(None, "--file", "-f", help="Load blueprint definition from YAML file."),
    description: str = typer.Option("", "--description", "-d", help="Short description."),
    changelog: str = typer.Option("", "--changelog", help="Changelog note for this version."),
) -> None:
    """Create or update a blueprint. Accepts --file <yaml> or individual options."""
    _require_init()

    if file:
        if not file.exists():
            console.print(f"[red]✗ File not found:[/red] {file}")
            raise typer.Exit(1)
        with file.open("r", encoding="utf-8") as fh:
            data = yaml.safe_load(fh)
        if not isinstance(data, dict):
            console.print("[red]✗ YAML file must contain a mapping.[/red]")
            raise typer.Exit(1)
        data["name"] = name
    else:
        data = {
            "name": name,
            "description": description,
            "inputs": [],
            "steps": [],
            "outputs": {},
            "changelog": changelog,
        }

    errors = _blueprint_mod._validate_blueprint_data(data)
    if errors:
        console.print("[red]✗ Blueprint definition errors:[/red]")
        for e in errors:
            console.print(f"  • {e}")
        raise typer.Exit(1)

    version, is_new = _blueprint_mod.save_blueprint_from_dict(data)
    action = "[green]✓ Created[/green]" if is_new else "[blue]↑ Updated[/blue]"
    console.print(f"{action} blueprint [bold]{name}[/bold] → [cyan]{version}[/cyan]")


# ---------------------------------------------------------------------------
# blueprint show
# ---------------------------------------------------------------------------


@blueprint_app.command("show")
def blueprint_show(
    ref: str = typer.Argument(..., help="Blueprint name or name@version."),
) -> None:
    """Show a blueprint definition."""
    _require_init()
    name, version = _parse_name_version(ref)
    try:
        data = _blueprint_mod.load_blueprint(name, version)
    except FileNotFoundError as e:
        console.print(f"[red]✗ {e}[/red]")
        raise typer.Exit(1)

    console.print(f"\n[bold cyan]{data['name']}[/bold cyan] [dim]{data['version']}[/dim]")
    if data.get("description"):
        console.print(f"[dim]{data['description']}[/dim]\n")

    inputs = data.get("inputs") or []
    if inputs:
        console.print("[bold]Inputs:[/bold]")
        for inp in inputs:
            req = "[red]*[/red]" if inp.get("required") else "[dim]opt[/dim]"
            default = f" (default: {inp['default']})" if inp.get("default") else ""
            console.print(f"  {req} [cyan]{inp['name']}[/cyan]{default}")

    steps = data.get("steps") or []
    if steps:
        console.print("\n[bold]Steps:[/bold]")
        for step in steps:
            stype = step.get("type", "?")
            sid = step.get("id", "?")
            sname = step.get("name", "")
            color = "green" if stype == "deterministic" else "yellow"
            console.print(f"  [{color}]{stype}[/{color}] [bold]{sid}[/bold]"
                          + (f" — {sname}" if sname else ""))
            if step.get("run"):
                console.print(f"    run: [dim]{step['run']}[/dim]")
            if step.get("harness"):
                console.print(f"    harness: [cyan]{step['harness']}[/cyan]")
            if step.get("skill"):
                console.print(f"    skill: [cyan]{step['skill']}[/cyan]")

    outputs = data.get("outputs") or {}
    if outputs:
        console.print("\n[bold]Outputs:[/bold]")
        for k, v in outputs.items():
            console.print(f"  [cyan]{k}[/cyan]: {v}")


# ---------------------------------------------------------------------------
# blueprint list
# ---------------------------------------------------------------------------


@blueprint_app.command("list")
def blueprint_list() -> None:
    """List all blueprints."""
    _require_init()
    items = _blueprint_mod.list_blueprints()
    if not items:
        console.print("[dim]No blueprints found.[/dim]")
        return

    table = Table(title="Blueprints", show_lines=False, header_style="bold cyan")
    table.add_column("Name", style="bold")
    table.add_column("Version", style="cyan")
    table.add_column("Steps", justify="right")
    table.add_column("Description")

    for bp in items:
        steps = bp.get("steps") or []
        table.add_row(
            bp.get("name", ""),
            bp.get("version", ""),
            str(len(steps)),
            bp.get("description", ""),
        )

    console.print(table)


# ---------------------------------------------------------------------------
# blueprint diff
# ---------------------------------------------------------------------------


@blueprint_app.command("diff")
def blueprint_diff(
    ref_a: str = typer.Argument(..., help="First blueprint ref (name or name@version)."),
    ref_b: str = typer.Argument(..., help="Second blueprint ref (name or name@version)."),
) -> None:
    """Show a unified diff between two blueprint versions."""
    _require_init()
    name_a, ver_a = _parse_name_version(ref_a)
    name_b, ver_b = _parse_name_version(ref_b)
    try:
        lines = _blueprint_mod.diff_blueprints(name_a, ver_a, name_b, ver_b)
    except FileNotFoundError as e:
        console.print(f"[red]✗ {e}[/red]")
        raise typer.Exit(1)

    if not lines:
        console.print("[dim]No differences.[/dim]")
        return

    for line in lines:
        line = line.rstrip("\n")
        if line.startswith("+++") or line.startswith("---"):
            console.print(Text(line, style="bold"))
        elif line.startswith("+"):
            console.print(Text(line, style="green"))
        elif line.startswith("-"):
            console.print(Text(line, style="red"))
        elif line.startswith("@@"):
            console.print(Text(line, style="cyan"))
        else:
            console.print(line)


# ---------------------------------------------------------------------------
# blueprint validate
# ---------------------------------------------------------------------------


@blueprint_app.command("validate")
def blueprint_validate(
    ref: str = typer.Argument(..., help="Blueprint name or name@version."),
    check_assets: bool = typer.Option(
        True, "--check-assets/--no-check-assets",
        help="Verify referenced harnesses and skills exist on disk.",
    ),
) -> None:
    """Validate a blueprint — structure, variable refs, asset existence, and cycles."""
    _require_init()
    name, version = _parse_name_version(ref)
    try:
        data = _blueprint_mod.load_blueprint(name, version)
    except FileNotFoundError as e:
        console.print(f"[red]✗ {e}[/red]")
        raise typer.Exit(1)

    display_version = version or _blueprint_mod.get_current_version(name)
    console.print(
        f"\n[bold]Blueprint '{name}@{display_version}' — Validation Report[/bold]"
    )
    console.rule()

    results = _blueprint_mod.full_validate(data)
    if not check_assets:
        results["asset_refs"] = []

    _CAT_LABELS = {
        "structure": "Structure",
        "variable_refs": "Variable References",
        "asset_refs": "Asset References",
        "goto_targets": "Goto Targets",
        "variable_cycles": "Variable Cycles",
    }

    total_errors = 0
    for cat, cat_errors in results.items():
        label = _CAT_LABELS.get(cat, cat)
        if cat_errors:
            console.print(f"\n[red][{label}] {len(cat_errors)} error(s)[/red]")
            for err in cat_errors:
                # Split error and fix hint on "Fix:"
                if "Fix:" in err:
                    msg, fix = err.split("Fix:", 1)
                    console.print(f"  [red]•[/red] {msg.strip()}")
                    console.print(f"    [dim]Fix:{fix}[/dim]")
                else:
                    console.print(f"  [red]•[/red] {err}")
            total_errors += len(cat_errors)
        else:
            console.print(f"\n[green][{label}] ✓ No errors[/green]")

    console.rule()
    if total_errors:
        console.print(
            f"[red]✗ Found {total_errors} error(s). Blueprint is NOT valid.[/red]\n"
        )
        raise typer.Exit(1)
    else:
        console.print(f"[green]✓ Blueprint '{name}' is valid.[/green]\n")


# ---------------------------------------------------------------------------
# blueprint run (Phase 4.3 — deterministic executor)
# ---------------------------------------------------------------------------


@blueprint_app.command("run")
def blueprint_run(
    ref: str = typer.Argument(..., help="Blueprint name or name@version."),
    var: list[str] = typer.Option(
        [],
        "--var",
        "-v",
        help="Input variable as key=value. Can be repeated.",
    ),
    dry_run: bool = typer.Option(
        False, "--dry-run", help="Render commands without executing them."
    ),
    start_step: Optional[str] = typer.Option(
        None, "--step", help="Start execution from this step ID (skips earlier steps)."
    ),
    verbose: bool = typer.Option(False, "--verbose", help="Show step stdout/stderr detail."),
) -> None:
    """Run a blueprint — execute its steps in order.

    Deterministic steps (shell commands) are executed immediately.
    Agentic steps call the configured Skill or Harness via LLM.
    """
    from harness_kit import blueprint_executor as _exec_mod

    _require_init()
    name, version = _parse_name_version(ref)

    try:
        data = _blueprint_mod.load_blueprint(name, version)
    except FileNotFoundError as e:
        console.print(f"[red]✗ {e}[/red]")
        raise typer.Exit(1)

    # Parse --var key=value pairs
    inputs: dict[str, str] = {}
    for v in var:
        if "=" not in v:
            console.print(
                f"[red]✗ Invalid --var format: [bold]{v}[/bold] (expected key=value)[/red]"
            )
            raise typer.Exit(1)
        k, val = v.split("=", 1)
        inputs[k.strip()] = val

    # Check required inputs
    for inp_def in data.get("inputs") or []:
        inp_name = inp_def.get("name", "")
        if inp_def.get("required", True) and inp_name not in inputs:
            if inp_def.get("default") is not None:
                inputs[inp_name] = str(inp_def["default"])
            else:
                console.print(
                    f"[red]✗ Missing required input: [bold]{inp_name}[/bold][/red]\n"
                    f"  Use [bold]--var {inp_name}=...[/bold] to provide it."
                )
                raise typer.Exit(1)

    display_version = version or _blueprint_mod.get_current_version(name)
    mode_tag = "[dim](dry-run)[/dim]" if dry_run else ""
    console.print(
        f"\n[bold]Blueprint[/bold] [cyan]{name}@{display_version}[/cyan] {mode_tag}"
    )
    console.rule()

    # Build step index for progress display
    steps = data.get("steps") or []
    total_steps = len(steps)

    # Progress display helpers (Phase 4.6 — real-time progress)
    _progress_instance: list = []  # use a list so the closure can mutate it
    _task_id: list = []

    def _on_step_start(step: dict) -> None:
        sid = step.get("id", "?")
        sname = step.get("name", sid)
        if _progress_instance:
            _progress_instance[0].update(
                _task_id[0],
                description=f"[cyan]{sid}[/cyan] [dim]{sname}[/dim]",
            )

    def _on_step_done(step_res) -> None:  # type: ignore[no-untyped-def]
        # Print step result line inside the progress context
        stype = step_res.step_type
        color = "green" if stype == "deterministic" else ("yellow" if stype == "agentic" else "dim")
        if step_res.status == "success":
            icon = "[green]✓[/green]"
        elif step_res.status == "failed":
            icon = "[red]✗[/red]"
        elif step_res.status == "timeout":
            icon = "[red]⏱[/red]"
        elif step_res.status == "dry_run":
            icon = "[dim]○[/dim]"
        else:
            icon = "[dim]–[/dim]"

        duration_tag = f"[dim]{step_res.duration:.2f}s[/dim]" if step_res.duration > 0 else ""
        console.print(
            f"  {icon} [{color}]{step_res.step_id}[/{color}]"
            f" [dim]{step_res.step_name}[/dim] {duration_tag}"
        )

        if verbose or step_res.status in ("failed", "timeout"):
            if step_res.output.strip():
                console.print(f"    [dim]stdout:[/dim] {step_res.output.strip()}")
            if step_res.stderr.strip():
                console.print(f"    [dim]stderr:[/dim] {step_res.stderr.strip()}")
        elif dry_run and step_res.output:
            console.print(f"    [dim]{step_res.output}[/dim]")

        if step_res.error and step_res.status not in ("failed", "timeout"):
            console.print(f"    [red]error: {step_res.error}[/red]")

        if _progress_instance:
            _progress_instance[0].advance(_task_id[0])

    # Run with live progress spinner
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        TimeElapsedColumn(),
        console=console,
        transient=True,  # clear spinner line when done
    ) as progress:
        _progress_instance.append(progress)
        task = progress.add_task(
            f"Starting [cyan]{name}[/cyan]…",
            total=total_steps,
        )
        _task_id.append(task)

        result = _exec_mod.execute_blueprint(
            data,
            inputs,
            dry_run=dry_run,
            start_step=start_step,
            base=Path.cwd(),
            on_step_start=_on_step_start,
            on_step_done=_on_step_done,
        )

    console.rule()

    # Outputs
    if result.outputs:
        console.print("\n[bold]Outputs:[/bold]")
        for k, v in result.outputs.items():
            truncated = v[:200] + "…" if len(v) > 200 else v
            console.print(f"  [cyan]{k}[/cyan]: {truncated}")

    # Save execution report (Phase 4.6)
    report_path = _exec_mod.save_run_report(result, base=Path.cwd())

    # Summary line
    duration_str = f"{result.duration:.2f}s"
    if result.status == "success":
        console.print(
            f"\n[green]✓ Blueprint '{name}' completed successfully[/green] "
            f"[dim]({duration_str})[/dim]"
        )
        console.print(f"[dim]Report saved: {report_path}[/dim]\n")
    elif result.status == "dry_run":
        console.print(
            f"\n[dim]Dry-run complete — no commands executed ({duration_str})[/dim]"
        )
        console.print(f"[dim]Report saved: {report_path}[/dim]\n")
    elif result.status == "stopped":
        reason = result.stop_reason or "step failed"
        console.print(f"\n[red]✗ Blueprint stopped: {reason}[/red] [dim]({duration_str})[/dim]")
        console.print(f"[dim]Report saved: {report_path}[/dim]\n")
        raise typer.Exit(1)
    else:  # "failed"
        console.print(
            f"\n[yellow]⚠ Blueprint '{name}' finished with failures[/yellow] "
            f"[dim]({duration_str})[/dim]"
        )
        console.print(f"[dim]Report saved: {report_path}[/dim]\n")
        raise typer.Exit(1)


# ---------------------------------------------------------------------------
# blueprint delete
# ---------------------------------------------------------------------------


@blueprint_app.command("delete")
def blueprint_delete(
    ref: str = typer.Argument(..., help="Blueprint name or name@version."),
    yes: bool = typer.Option(False, "--yes", "-y", help="Skip confirmation prompt."),
) -> None:
    """Delete a blueprint (or a specific version)."""
    _require_init()
    name, version = _parse_name_version(ref)

    if not yes:
        target = f"'{name}@{version}'" if version else f"all versions of '{name}'"
        console.print(f"[yellow]About to delete {target}.[/yellow]")
        confirmed = typer.confirm("Continue?")
        if not confirmed:
            console.print("[dim]Aborted.[/dim]")
            return

    try:
        _blueprint_mod.delete_blueprint(name, version)
    except FileNotFoundError as e:
        console.print(f"[red]✗ {e}[/red]")
        raise typer.Exit(1)

    label = f"'{name}@{version}'" if version else f"'{name}'"
    console.print(f"[green]✓ Deleted blueprint {label}.[/green]")


# ---------------------------------------------------------------------------
# eval suite-add
# ---------------------------------------------------------------------------


@eval_app.command("suite-add")
def eval_suite_add(
    file: str = typer.Option(..., "--file", "-f", help="Path to test suite YAML file."),
) -> None:
    """Add or update a test suite from a YAML file."""
    _require_init()
    path = Path(file)
    if not path.exists():
        console.print(f"[red]✗ File not found: {file}[/red]")
        raise typer.Exit(1)

    with path.open("r", encoding="utf-8") as fh:
        data = yaml.safe_load(fh)

    if not isinstance(data, dict):
        console.print("[red]✗ File must contain a YAML mapping.[/red]")
        raise typer.Exit(1)

    try:
        _eval_mod.save_suite(data)
    except ValueError as e:
        console.print(f"[red]✗ Validation error:[/red]\n{e}")
        raise typer.Exit(1)

    name = data.get("name", "?")
    case_count = len(data.get("cases") or [])
    console.print(f"[green]✓ Test suite '{name}' saved ({case_count} cases).[/green]")


# ---------------------------------------------------------------------------
# eval list
# ---------------------------------------------------------------------------


@eval_app.command("list")
def eval_list() -> None:
    """List all test suites."""
    _require_init()
    names = _eval_mod.list_suites()
    if not names:
        console.print("[dim]No test suites found.[/dim]")
        return

    table = Table(title="Test Suites", show_lines=False)
    table.add_column("Name", style="cyan")
    table.add_column("Description", style="white")
    table.add_column("Cases", justify="right")
    table.add_column("Assertions", justify="right")

    for name in names:
        try:
            data = _eval_mod.load_suite(name)
            s = _eval_mod.suite_summary(data)
            table.add_row(
                s["name"],
                s["description"][:60] + ("…" if len(s["description"]) > 60 else ""),
                str(s["case_count"]),
                str(s["assertion_count"]),
            )
        except Exception:
            table.add_row(name, "[red]error reading suite[/red]", "-", "-")

    console.print(table)


# ---------------------------------------------------------------------------
# eval show
# ---------------------------------------------------------------------------


@eval_app.command("show")
def eval_show(
    name: str = typer.Argument(..., help="Test suite name."),
) -> None:
    """Show test suite details."""
    _require_init()
    try:
        data = _eval_mod.load_suite(name)
    except FileNotFoundError as e:
        console.print(f"[red]✗ {e}[/red]")
        raise typer.Exit(1)

    s = _eval_mod.suite_summary(data)
    console.print(f"\n[bold cyan]{s['name']}[/bold cyan]")
    console.print(f"[dim]{s['description']}[/dim]")
    console.print(f"\n[bold]Cases:[/bold] {s['case_count']}  [bold]Assertions:[/bold] {s['assertion_count']}\n")

    cases = data.get("cases") or []
    for case in cases:
        cid = case.get("id", "?")
        cname = case.get("name", "")
        assertions = case.get("assertions") or []
        console.print(f"  [cyan]{cid}[/cyan]  {cname}")
        inputs = case.get("inputs") or {}
        if inputs:
            input_keys = ", ".join(f"[yellow]{k}[/yellow]" for k in inputs)
            console.print(f"    inputs: {input_keys}")
        for a in assertions:
            atype = a.get("type", "?")
            path_val = a.get("path", "")
            detail = ""
            if atype == "contains":
                detail = f"path={path_val!r} contains {a.get('value')!r}"
            elif atype == "regex":
                detail = f"path={path_val!r} matches r{a.get('pattern')!r}"
            elif atype == "json_schema":
                detail = f"path={path_val!r} validates JSON Schema"
            elif atype == "custom":
                detail = f"custom fn={a.get('function')!r}"
            else:
                detail = str(a)
            console.print(f"    [green]{atype}[/green]: {detail}")
        console.print()


# ---------------------------------------------------------------------------
# eval delete
# ---------------------------------------------------------------------------


@eval_app.command("delete")
def eval_delete(
    name: str = typer.Argument(..., help="Test suite name."),
    yes: bool = typer.Option(False, "--yes", "-y", help="Skip confirmation prompt."),
) -> None:
    """Delete a test suite."""
    _require_init()
    if not yes:
        console.print(f"[yellow]About to delete test suite '{name}'.[/yellow]")
        confirmed = typer.confirm("Continue?")
        if not confirmed:
            console.print("[dim]Aborted.[/dim]")
            return

    try:
        _eval_mod.delete_suite(name)
    except FileNotFoundError as e:
        console.print(f"[red]✗ {e}[/red]")
        raise typer.Exit(1)

    console.print(f"[green]✓ Test suite '{name}' deleted.[/green]")


# ---------------------------------------------------------------------------
# eval run
# ---------------------------------------------------------------------------


@eval_app.command("run")
def eval_run(
    target: str = typer.Argument(
        ...,
        help="Skill (or harness) to evaluate, e.g. 'my-skill' or 'my-skill@v0.1.0'.",
    ),
    suite: str = typer.Option(
        ..., "--suite", "-s",
        help="Test suite name.",
    ),
    model: Optional[str] = typer.Option(None, "--model", "-m", help="Override model."),
    ci: bool = typer.Option(
        False, "--ci",
        help="CI mode: exit with non-zero code when any test case fails.",
    ),
    junit_xml: Optional[Path] = typer.Option(
        None, "--junit-xml",
        help="Write JUnit XML report to this path (for CI systems).",
    ),
) -> None:
    """Run a test suite against a skill and generate an evaluation report."""
    _require_init()

    # Validate suite exists
    try:
        _eval_mod.load_suite(suite)
    except FileNotFoundError as e:
        console.print(f"[red]✗ {e}[/red]")
        raise typer.Exit(1)

    # Resolve target → skill name + version
    skill_name, skill_version = _parse_name_version(target)

    # Load skill (only skills supported for now; harness support is future)
    try:
        skill_data = _skill_mod.load_skill(skill_name, skill_version)
        actual_version = skill_data.get("version", "?")
        target_label = f"{skill_name}@{actual_version}"
    except FileNotFoundError as e:
        console.print(f"[red]✗ {e}[/red]")
        raise typer.Exit(1)

    # Build LLM config
    cfg = read_config()
    llm_config = LLMConfig.from_harness_config(cfg, overrides={"model": model} if model else {})

    if not llm_config.api_key:
        console.print(
            "[red]✗ No API key found.[/red] "
            "Set [bold]OPENAI_API_KEY[/bold] environment variable or configure [cyan].harness/config.yaml[/cyan]."
        )
        raise typer.Exit(1)

    # Pre-render skill prompt (done once, reused per case)
    try:
        rendered = _skill_mod.render_skill_prompt(skill_name, skill_version)
    except Exception as e:
        console.print(f"[red]✗ Failed to render skill: {e}[/red]")
        raise typer.Exit(1)

    # Build invoke_fn
    def _invoke(inputs: dict) -> tuple[str, int, int, float]:
        vars_dict: dict[str, str] = {k: str(v) for k, v in inputs.items()}
        # Apply skill input defaults
        for inp in skill_data.get("inputs") or []:
            iname = inp.get("name")
            if iname and iname not in vars_dict and inp.get("default") is not None:
                vars_dict[iname] = str(inp["default"])
        msgs = build_messages(skill_data, rendered, vars_dict)
        resp = call_llm(msgs, llm_config, stream=False)
        return resp.content, resp.input_tokens, resp.output_tokens, resp.duration

    # Run eval with progress display
    suite_data = _eval_mod.load_suite(suite)
    cases = suite_data.get("cases") or []
    total = len(cases)

    console.print(
        f"\n[bold cyan]Eval:[/bold cyan] [bold]{target_label}[/bold]  "
        f"suite=[bold]{suite}[/bold]  cases={total}\n"
    )

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        TimeElapsedColumn(),
        console=console,
        transient=True,
    ) as progress:
        task = progress.add_task("Running…", total=total)
        try:
            report = _eval_mod.run_eval(
                target=target_label,
                suite_name=suite,
                invoke_fn=_invoke,
            )
        except Exception as e:
            console.print(f"[red]✗ Eval failed: {e}[/red]")
            raise typer.Exit(1)
        progress.update(task, completed=total)

    # Display results table
    summary = report["summary"]
    passed = summary["passed"]
    failed = summary["failed"]
    result_file = report.get("_result_file", "")

    table = Table(title=f"Eval Results — {target_label}", show_lines=False)
    table.add_column("ID", style="cyan")
    table.add_column("Name")
    table.add_column("Status", justify="center")
    table.add_column("Duration", justify="right")
    table.add_column("Tokens", justify="right")
    table.add_column("Assertions", justify="right")

    for case in report["cases"]:
        status = case["status"]
        color = "green" if status == "passed" else ("red" if status == "failed" else "yellow")
        icon = "✓" if status == "passed" else ("✗" if status == "failed" else "!")
        asrt = case.get("assertion_summary", {})
        asrt_str = f"{asrt.get('passed', 0)}/{asrt.get('total', 0)}" if asrt else "-"
        tokens = case.get("input_tokens", 0) + case.get("output_tokens", 0)
        table.add_row(
            case["id"],
            case.get("name", ""),
            f"[{color}]{icon} {status}[/{color}]",
            f"{case['duration']:.2f}s",
            str(tokens) if tokens else "-",
            asrt_str,
        )

    console.print(table)

    # Print failed assertion details
    for case in report["cases"]:
        if case["status"] != "passed":
            console.print(f"\n[bold red]✗ {case['id']}[/bold red] — {case.get('name', '')}")
            if case.get("error"):
                console.print(f"  [red]Error: {case['error']}[/red]")
            for a in case.get("assertions") or []:
                if not a.get("passed"):
                    console.print(f"  [yellow]FAIL[/yellow] [{a['type']}] {a['message']}")

    pass_color = "green" if failed == 0 else "red"
    console.print(
        f"\n[bold]Summary:[/bold] total={total}  "
        f"[green]passed={passed}[/green]  [{pass_color}]failed={failed}[/{pass_color}]"
    )
    if result_file:
        console.print(f"[dim]Report saved: {result_file}[/dim]")

    if junit_xml:
        _eval_mod.generate_junit_xml(report, junit_xml)
        console.print(f"[dim]JUnit XML: {junit_xml}[/dim]")

    if ci and failed > 0:
        raise typer.Exit(1)


@eval_app.command("compare")
def eval_compare(
    a: str = typer.Option(..., "--a", help="First target, e.g. 'my-skill@v0.1.0'."),
    b: str = typer.Option(..., "--b", help="Second target, e.g. 'my-skill@v0.2.0'."),
    suite: str = typer.Option(..., "--suite", "-s", help="Test suite name."),
    model: Optional[str] = typer.Option(None, "--model", "-m", help="Override LLM model."),
    ci: bool = typer.Option(
        False, "--ci",
        help="CI mode: exit 1 when the better target still has failures.",
    ),
) -> None:
    """A/B compare two skill versions on the same test suite."""
    _require_init()

    # Validate suite
    try:
        _eval_mod.load_suite(suite)
    except FileNotFoundError as e:
        console.print(f"[red]✗ {e}[/red]")
        raise typer.Exit(1)

    # Load both targets
    def _load_target(ref: str) -> tuple[str, dict, object]:
        name, version = _parse_name_version(ref)
        try:
            data = _skill_mod.load_skill(name, version)
        except FileNotFoundError as exc:
            console.print(f"[red]✗ {exc}[/red]")
            raise typer.Exit(1)
        actual_ver = data.get("version", "?")
        label = f"{name}@{actual_ver}"
        try:
            rendered = _skill_mod.render_skill_prompt(name, version)
        except Exception as exc:
            console.print(f"[red]✗ Failed to render skill '{ref}': {exc}[/red]")
            raise typer.Exit(1)
        return label, data, rendered

    label_a, data_a, rendered_a = _load_target(a)
    label_b, data_b, rendered_b = _load_target(b)

    # Build LLM config
    cfg = read_config()
    llm_config = LLMConfig.from_harness_config(cfg, overrides={"model": model} if model else {})
    if not llm_config.api_key:
        console.print(
            "[red]✗ No API key found.[/red] "
            "Set [bold]OPENAI_API_KEY[/bold] or configure [cyan].harness/config.yaml[/cyan]."
        )
        raise typer.Exit(1)

    def _make_invoke(skill_data: dict, rendered: object) -> object:
        def _invoke(inputs: dict) -> tuple[str, int, int, float]:
            vars_dict: dict[str, str] = {k: str(v) for k, v in inputs.items()}
            for inp in skill_data.get("inputs") or []:
                iname = inp.get("name")
                if iname and iname not in vars_dict and inp.get("default") is not None:
                    vars_dict[iname] = str(inp["default"])
            msgs = build_messages(skill_data, rendered, vars_dict)
            resp = call_llm(msgs, llm_config, stream=False)
            return resp.content, resp.input_tokens, resp.output_tokens, resp.duration
        return _invoke

    invoke_a = _make_invoke(data_a, rendered_a)
    invoke_b = _make_invoke(data_b, rendered_b)

    suite_data = _eval_mod.load_suite(suite)
    total_cases = len(suite_data.get("cases") or [])

    console.print(
        f"\n[bold cyan]A/B Compare[/bold cyan]  suite=[bold]{suite}[/bold]  cases={total_cases}\n"
        f"  [bold]A:[/bold] {label_a}\n"
        f"  [bold]B:[/bold] {label_b}\n"
    )

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        TimeElapsedColumn(),
        console=console,
        transient=True,
    ) as progress:
        task_a = progress.add_task(f"Running A ({label_a})…", total=total_cases)
        try:
            report_a = _eval_mod.run_eval(target=label_a, suite_name=suite, invoke_fn=invoke_a)
        except Exception as e:
            console.print(f"[red]✗ Eval A failed: {e}[/red]")
            raise typer.Exit(1)
        progress.update(task_a, completed=total_cases)

        task_b = progress.add_task(f"Running B ({label_b})…", total=total_cases)
        try:
            report_b = _eval_mod.run_eval(target=label_b, suite_name=suite, invoke_fn=invoke_b)
        except Exception as e:
            console.print(f"[red]✗ Eval B failed: {e}[/red]")
            raise typer.Exit(1)
        progress.update(task_b, completed=total_cases)

    comparison = _eval_mod.compare_evals(report_a, report_b)
    m_a = comparison["metrics_a"]
    m_b = comparison["metrics_b"]

    # ── Metrics comparison table ──────────────────────────────────────────────
    def _delta(va: float, vb: float, higher_better: bool = True) -> str:
        diff = vb - va
        if diff == 0:
            return "[dim]±0[/dim]"
        better = diff > 0 if higher_better else diff < 0
        arrow = "▲" if diff > 0 else "▼"
        color = "green" if better else "red"
        return f"[{color}]{arrow}{abs(diff):.3g}[/{color}]"

    tbl = Table(title="Metrics Comparison", show_lines=True)
    tbl.add_column("Metric", style="bold")
    tbl.add_column(f"A: {label_a}", justify="right")
    tbl.add_column(f"B: {label_b}", justify="right")
    tbl.add_column("Change (B vs A)", justify="right")

    def _pass_str(m: dict) -> str:
        color = "green" if m["failed"] == 0 else "red"
        pct = f"{m['pass_rate']*100:.1f}%"
        return f"[{color}]{m['passed']}/{m['total']} ({pct})[/{color}]"

    tbl.add_row("Pass rate", _pass_str(m_a), _pass_str(m_b),
                _delta(m_a["pass_rate"], m_b["pass_rate"]))
    tbl.add_row("Avg tokens", f"{m_a['avg_tokens']:.1f}", f"{m_b['avg_tokens']:.1f}",
                _delta(m_a["avg_tokens"], m_b["avg_tokens"], higher_better=False))
    tbl.add_row("Total tokens", str(m_a["total_tokens"]), str(m_b["total_tokens"]),
                _delta(m_a["total_tokens"], m_b["total_tokens"], higher_better=False))
    tbl.add_row("Avg duration", f"{m_a['avg_duration']:.3f}s", f"{m_b['avg_duration']:.3f}s",
                _delta(m_a["avg_duration"], m_b["avg_duration"], higher_better=False))
    console.print(tbl)

    # ── Per-case diff table ───────────────────────────────────────────────────
    changed = comparison["changed_cases"]
    if changed:
        ctbl = Table(title="Changed Cases", show_lines=False)
        ctbl.add_column("ID", style="cyan")
        ctbl.add_column("Name")
        ctbl.add_column("A", justify="center")
        ctbl.add_column("B", justify="center")

        def _status_cell(s: str) -> str:
            if s == "passed":
                return "[green]✓ passed[/green]"
            if s == "failed":
                return "[red]✗ failed[/red]"
            if s == "error":
                return "[yellow]! error[/yellow]"
            return f"[dim]{s}[/dim]"

        for d in changed:
            ctbl.add_row(d["id"], d["name"], _status_cell(d["status_a"]), _status_cell(d["status_b"]))
        console.print(ctbl)
    else:
        console.print("[dim]No case status changes between A and B.[/dim]")

    # ── Verdict ───────────────────────────────────────────────────────────────
    winner_label = label_a if comparison["verdict"] == "a" else label_b
    loser_label = label_b if comparison["verdict"] == "a" else label_a
    console.print(
        f"\n[bold]Recommendation:[/bold] "
        f"[green]{winner_label}[/green] is better "
        f"(higher pass rate or fewer tokens than [dim]{loser_label}[/dim])."
    )

    if ci and (m_a["failed"] > 0 or m_b["failed"] > 0):
        raise typer.Exit(1)


@eval_app.command("benchmark")
def eval_benchmark(
    target: str = typer.Argument(
        ...,
        help="Skill to benchmark, e.g. 'my-skill' or 'my-skill@v0.1.0'.",
    ),
    suite: str = typer.Option(
        ..., "--suite", "-s",
        help="Test suite name.",
    ),
    models: str = typer.Option(
        ..., "--models",
        help="Comma-separated list of models, e.g. 'gpt-4o,claude-3-5,deepseek-v3'.",
    ),
    ci: bool = typer.Option(
        False, "--ci",
        help="CI mode: exit 1 when any model has failures.",
    ),
) -> None:
    """Benchmark a skill across multiple LLM models on the same test suite."""
    _require_init()

    # Validate suite
    try:
        suite_data = _eval_mod.load_suite(suite)
    except FileNotFoundError as e:
        console.print(f"[red]✗ {e}[/red]")
        raise typer.Exit(1)

    # Resolve skill
    skill_name, skill_version = _parse_name_version(target)
    try:
        skill_data = _skill_mod.load_skill(skill_name, skill_version)
        actual_version = skill_data.get("version", "?")
        skill_label = f"{skill_name}@{actual_version}"
    except FileNotFoundError as e:
        console.print(f"[red]✗ {e}[/red]")
        raise typer.Exit(1)

    try:
        rendered = _skill_mod.render_skill_prompt(skill_name, skill_version)
    except Exception as e:
        console.print(f"[red]✗ Failed to render skill: {e}[/red]")
        raise typer.Exit(1)

    # Parse model list
    model_list = [m.strip() for m in models.split(",") if m.strip()]
    if not model_list:
        console.print("[red]✗ --models must contain at least one model.[/red]")
        raise typer.Exit(1)

    # Read base config (for api_key, base_url)
    cfg = read_config()

    # Check API key from first model config
    base_llm = LLMConfig.from_harness_config(cfg, overrides={"model": model_list[0]})
    if not base_llm.api_key:
        console.print(
            "[red]✗ No API key found.[/red] "
            "Set [bold]OPENAI_API_KEY[/bold] or configure [cyan].harness/config.yaml[/cyan]."
        )
        raise typer.Exit(1)

    total_cases = len(suite_data.get("cases") or [])
    console.print(
        f"\n[bold cyan]Benchmark:[/bold cyan] [bold]{skill_label}[/bold]  "
        f"suite=[bold]{suite}[/bold]  models={len(model_list)}  cases={total_cases}\n"
    )

    reports: list[dict] = []

    for model_name in model_list:
        llm_config = LLMConfig.from_harness_config(cfg, overrides={"model": model_name})

        def _make_invoke(sd: dict, rend: dict, lc: LLMConfig):  # noqa: ANN001
            def _invoke(inputs: dict) -> tuple[str, int, int, float]:
                vars_dict: dict[str, str] = {k: str(v) for k, v in inputs.items()}
                for inp in sd.get("inputs") or []:
                    iname = inp.get("name")
                    if iname and iname not in vars_dict and inp.get("default") is not None:
                        vars_dict[iname] = str(inp["default"])
                msgs = build_messages(sd, rend, vars_dict)
                resp = call_llm(msgs, lc, stream=False)
                return resp.content, resp.input_tokens, resp.output_tokens, resp.duration
            return _invoke

        invoke_fn = _make_invoke(skill_data, rendered, llm_config)
        target_label = f"{skill_label} [{model_name}]"

        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            TimeElapsedColumn(),
            console=console,
            transient=True,
        ) as progress:
            task = progress.add_task(f"Running [bold]{model_name}[/bold]…", total=total_cases)
            try:
                report = _eval_mod.run_eval(
                    target=target_label,
                    suite_name=suite,
                    invoke_fn=invoke_fn,
                    extra_fields={"model": model_name, "skill": skill_label},
                )
            except Exception as e:
                console.print(f"[red]✗ {model_name}: {e}[/red]")
                raise typer.Exit(1)
            progress.update(task, completed=total_cases)

        reports.append(report)

    # Produce benchmark summary
    benchmark = _eval_mod.benchmark_evals(reports)
    entries = benchmark["entries"]

    # ── Per-model results table ────────────────────────────────────────────
    tbl = Table(title=f"Benchmark — {skill_label} × {suite}", show_lines=True)
    tbl.add_column("Model", style="bold cyan")
    tbl.add_column("Pass Rate", justify="center")
    tbl.add_column("Passed", justify="right")
    tbl.add_column("Failed", justify="right")
    tbl.add_column("Avg Tokens", justify="right")
    tbl.add_column("Total Tokens", justify="right")
    tbl.add_column("Avg Duration", justify="right")

    best_model = benchmark["best_model"]

    for entry in entries:
        m = entry["metrics"]
        model_name = entry["model"]
        is_best = model_name == best_model
        pct = f"{m['pass_rate'] * 100:.1f}%"
        pr_color = "green" if m["failed"] == 0 else "red"
        model_cell = f"[bold green]{model_name} ★[/bold green]" if is_best else model_name
        tbl.add_row(
            model_cell,
            f"[{pr_color}]{pct}[/{pr_color}]",
            f"[green]{m['passed']}[/green]",
            f"[red]{m['failed']}[/red]" if m["failed"] > 0 else "0",
            f"{m['avg_tokens']:.1f}",
            str(m["total_tokens"]),
            f"{m['avg_duration']:.3f}s",
        )

    console.print(tbl)

    # ── Per-case breakdown per model ──────────────────────────────────────
    all_case_ids = [c["id"] for c in (suite_data.get("cases") or [])]
    if all_case_ids:
        ctbl = Table(title="Per-Case Results", show_lines=False)
        ctbl.add_column("Case ID", style="cyan")
        for entry in entries:
            ctbl.add_column(entry["model"], justify="center")

        # Build a lookup: model → {case_id → status}
        model_case_status: dict[str, dict[str, str]] = {}
        for report, entry in zip(reports, entries):
            model_case_status[entry["model"]] = {
                c["id"]: c["status"] for c in (report.get("cases") or [])
            }

        for cid in all_case_ids:
            cells: list[str] = [cid]
            for entry in entries:
                status = model_case_status.get(entry["model"], {}).get(cid, "?")
                if status == "passed":
                    cells.append("[green]✓[/green]")
                elif status == "failed":
                    cells.append("[red]✗[/red]")
                elif status == "error":
                    cells.append("[yellow]![/yellow]")
                else:
                    cells.append("[dim]?[/dim]")
            ctbl.add_row(*cells)

        console.print(ctbl)

    # ── Recommendation ────────────────────────────────────────────────────
    console.print(
        f"\n[bold]Best Model:[/bold] [bold green]{best_model}[/bold green] "
        f"(highest pass rate; tie-break: fewest tokens, then fastest)"
    )

    if ci:
        any_failures = any(e["metrics"]["failed"] > 0 for e in entries)
        if any_failures:
            raise typer.Exit(1)


# ---------------------------------------------------------------------------
# eval trend  (Phase 5.6 — historical success-rate trend)
# ---------------------------------------------------------------------------


@eval_app.command("trend")
def eval_trend(
    target: Optional[str] = typer.Argument(
        None,
        help="Target name filter (substring match), e.g. 'my-skill'.",
    ),
    suite: Optional[str] = typer.Option(
        None, "--suite", "-s",
        help="Filter by exact suite name.",
    ),
    limit: int = typer.Option(
        20, "--limit", "-n",
        help="Maximum number of recent results to display.",
    ),
) -> None:
    """Show historical pass-rate trend for past eval runs."""
    _require_init()

    entries = _eval_mod.eval_trend(
        target_filter=target,
        suite_filter=suite,
        limit=limit,
    )

    if not entries:
        console.print("[dim]No eval results found. Run [bold]harnesskit eval run[/bold] first.[/dim]")
        return

    # ── Summary table ──────────────────────────────────────────────────────
    table = Table(title="Eval History Trend", show_lines=False)
    table.add_column("#", style="dim", justify="right")
    table.add_column("Timestamp", style="cyan")
    table.add_column("Target")
    table.add_column("Suite")
    table.add_column("Pass Rate", justify="right")
    table.add_column("Passed", justify="right")
    table.add_column("Total", justify="right")
    table.add_column("Trend", justify="left")

    prev_rate: Optional[float] = None
    for i, entry in enumerate(entries, 1):
        rate = entry["pass_rate"]
        rate_pct = f"{rate * 100:.1f}%"
        color = "green" if rate >= 1.0 else ("yellow" if rate >= 0.5 else "red")

        # Trend arrow vs previous
        if prev_rate is None:
            arrow = ""
        elif rate > prev_rate:
            arrow = "[green]↑[/green]"
        elif rate < prev_rate:
            arrow = "[red]↓[/red]"
        else:
            arrow = "[dim]→[/dim]"
        prev_rate = rate

        # Short timestamp (strip microseconds / timezone for display)
        ts = entry["timestamp"]
        ts_display = ts[:19].replace("T", " ") if ts else "—"

        table.add_row(
            str(i),
            ts_display,
            entry["target"],
            entry["suite"],
            f"[{color}]{rate_pct}[/{color}]",
            str(entry["passed"]),
            str(entry["total"]),
            arrow,
        )

    console.print(table)

    # ── ASCII sparkline chart ──────────────────────────────────────────────
    rates = [e["pass_rate"] for e in entries]
    if len(rates) >= 2:
        console.print("\n[bold]Pass-Rate Chart[/bold] (each bar = one run)\n")
        bar_chars = " ▁▂▃▄▅▆▇█"
        chart_rows = 4
        chart_width = len(rates)
        # Normalize rates to bar characters
        bars: list[str] = []
        for r in rates:
            idx = min(int(r * (len(bar_chars) - 1)), len(bar_chars) - 1)
            color = "green" if r >= 1.0 else ("yellow" if r >= 0.5 else "red")
            bars.append(f"[{color}]{bar_chars[idx]}[/{color}]")
        console.print("  " + "".join(bars))
        console.print(f"  [dim]{'─' * chart_width}[/dim]")
        padding = max(0, chart_width - 4)
        console.print(f"  [dim]0%{' ' * padding}100%[/dim]")
        console.print()

    # ── Latest stats ──────────────────────────────────────────────────────
    last = entries[-1]
    avg_rate = sum(e["pass_rate"] for e in entries) / len(entries)
    console.print(
        f"[bold]Latest:[/bold] [cyan]{last['pass_rate'] * 100:.1f}%[/cyan]  "
        f"[bold]Avg:[/bold] [cyan]{avg_rate * 100:.1f}%[/cyan]  "
        f"[dim]({len(entries)} runs shown)[/dim]"
    )


# ---------------------------------------------------------------------------
# stats commands
# ---------------------------------------------------------------------------


@stats_app.command("show")
def stats_show_cmd(
    target: str = typer.Argument(..., help="Skill or harness name to inspect."),
    since: Optional[str] = typer.Option(None, "--since", "-s", help="Time window: 1d, 7d, 30d, etc. Default: all time."),
    bar_width: int = typer.Option(30, "--bar-width", help="Width of ASCII bar charts (characters)."),
) -> None:
    """Show statistics dashboard for a skill or harness.

    Displays call count, success rate, duration stats, token consumption
    distribution, error type breakdown, and model usage — all rendered
    as rich tables and ASCII bar charts.
    """
    _require_init()
    data = _stats_mod.skill_stats(target=target, since=since)

    since_label = f"last {since}" if since else "all time"
    console.print(f"\n[bold cyan]── Stats: {target} ({since_label}) ──[/bold cyan]\n")

    if data["total_calls"] == 0:
        console.print(f"[dim]No call logs found for [bold]{target}[/bold].[/dim]")
        console.print("[dim]Run a skill first: [bold]harnesskit skill run <name>[/bold][/dim]")
        return

    # ── Overview table ────────────────────────────────────────────────────
    overview = Table(title="Overview", show_header=True, header_style="bold magenta")
    overview.add_column("Metric", style="cyan", no_wrap=True)
    overview.add_column("Value", justify="right")

    total = data["total_calls"]
    sr = data["success_rate"] * 100
    sr_color = "green" if sr >= 90 else ("yellow" if sr >= 70 else "red")

    overview.add_row("Total calls", str(total))
    overview.add_row("Successful", f"[green]{data['success_calls']}[/green]")
    overview.add_row("Errors", f"[red]{data['error_calls']}[/red]" if data["error_calls"] else "0")
    overview.add_row("Success rate", f"[{sr_color}]{sr:.1f}%[/{sr_color}]")

    if data["avg_duration"] is not None:
        overview.add_row("Avg duration", f"{data['avg_duration']:.2f}s")
        overview.add_row("Min duration", f"{data['min_duration']:.2f}s")
        overview.add_row("Max duration", f"{data['max_duration']:.2f}s")

    if data["avg_total_tokens"] is not None:
        overview.add_row("Avg tokens / call", f"{data['avg_total_tokens']:.0f}")
        overview.add_row("  ↳ input", f"{data['avg_input_tokens']:.0f}")
        overview.add_row("  ↳ output", f"{data['avg_output_tokens']:.0f}")
        overview.add_row("Total tokens", f"{data['total_tokens']:,}")

    if data["total_cost"] > 0:
        overview.add_row("Total cost", f"[green]${data['total_cost']:.4f}[/green]")
        if data["avg_cost"] is not None:
            overview.add_row("Avg cost / call", f"${data['avg_cost']:.6f}")

    console.print(overview)

    # ── Token distribution chart ──────────────────────────────────────────
    if data["token_buckets"]:
        console.print("\n[bold]Token Consumption Distribution[/bold] (total tokens per call)\n")
        rows = _stats_mod.bar_chart_rows(data["token_buckets"], bar_width=bar_width, color="blue")
        for label, count, bar in rows:
            if count > 0:
                console.print(f"  {label:<10} {bar} {count:>5}")
        console.print()

    # ── Duration distribution chart ───────────────────────────────────────
    if data["duration_buckets"]:
        console.print("[bold]Duration Distribution[/bold]\n")
        rows = _stats_mod.bar_chart_rows(data["duration_buckets"], bar_width=bar_width, color="cyan")
        for label, count, bar in rows:
            if count > 0:
                console.print(f"  {label:<10} {bar} {count:>5}")
        console.print()

    # ── Model usage table ─────────────────────────────────────────────────
    if data["models_used"]:
        model_table = Table(title="Model Usage", show_lines=False)
        model_table.add_column("Model", style="blue")
        model_table.add_column("Calls", justify="right")
        model_table.add_column("Share", justify="right")
        for model, count in data["models_used"].items():
            share = f"{count / total * 100:.1f}%"
            model_table.add_row(model, str(count), share)
        console.print(model_table)
        console.print()

    # ── Error type distribution ───────────────────────────────────────────
    if data["error_types"]:
        console.print("[bold]Error Type Distribution[/bold]\n")
        err_rows = _stats_mod.bar_chart_rows(data["error_types"], bar_width=bar_width, color="red")
        for label, count, bar in err_rows:
            console.print(f"  {label:<50} {bar} {count:>4}")
        console.print()
    elif data["error_calls"] == 0:
        console.print("[dim]No errors recorded — [green]all calls succeeded[/green][/dim]\n")


if __name__ == "__main__":
    main()
