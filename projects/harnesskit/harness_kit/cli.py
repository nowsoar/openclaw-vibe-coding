"""HarnessKit CLI entry point."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Optional

import typer
import yaml
from rich.console import Console
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
) -> None:
    """Show the most recent LLM call log entries."""
    _require_init()
    records = _call_logger_mod.tail_logs(n=n)
    if not records:
        console.print("[dim]No call logs found.[/dim]")
        return

    table = Table(title="Recent LLM Calls", show_lines=False)
    table.add_column("Timestamp", style="dim", no_wrap=True)
    table.add_column("Skill", style="cyan")
    table.add_column("Model", style="blue")
    table.add_column("Status", style="bold")
    table.add_column("Tokens ↑↓", justify="right")
    table.add_column("Duration", justify="right")

    for rec in records:
        status = rec.get("status", "?")
        status_style = "green" if status == "success" else "red" if status == "error" else "yellow"
        ts = rec.get("timestamp", "")[:19].replace("T", " ")
        tokens = f"{rec.get('input_tokens', 0)} / {rec.get('output_tokens', 0)}"
        duration = f"{rec.get('duration', 0):.2f}s"
        table.add_row(
            ts,
            rec.get("skill", "?"),
            rec.get("model", "?"),
            f"[{status_style}]{status}[/{status_style}]",
            tokens,
            duration,
        )
    console.print(table)


@logs_app.command("search")
def logs_search(
    skill: Optional[str] = typer.Option(None, "--skill", help="Filter by skill name."),
    status: Optional[str] = typer.Option(None, "--status", help="Filter by status (success/error)."),
    limit: int = typer.Option(50, "--limit", "-l", help="Maximum number of results."),
) -> None:
    """Search call logs with optional filters."""
    _require_init()
    records = _call_logger_mod.search_logs(skill=skill, status=status, limit=limit)
    if not records:
        console.print("[dim]No matching call logs found.[/dim]")
        return

    table = Table(title=f"Call Logs (skill={skill or '*'}, status={status or '*'})", show_lines=False)
    table.add_column("Timestamp", style="dim", no_wrap=True)
    table.add_column("Skill", style="cyan")
    table.add_column("Model", style="blue")
    table.add_column("Status", style="bold")
    table.add_column("Tokens ↑/↓", justify="right")
    table.add_column("Duration", justify="right")

    for rec in records:
        status_val = rec.get("status", "?")
        status_style = "green" if status_val == "success" else "red" if status_val == "error" else "yellow"
        ts = rec.get("timestamp", "")[:19].replace("T", " ")
        tokens = f"{rec.get('input_tokens', 0)} / {rec.get('output_tokens', 0)}"
        duration = f"{rec.get('duration', 0):.2f}s"
        table.add_row(
            ts,
            rec.get("skill", "?"),
            rec.get("model", "?"),
            f"[{status_style}]{status_val}[/{status_style}]",
            tokens,
            duration,
        )
    console.print(table)


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
        errors = _harness_mod._validate_harness_data(data)
        if errors:
            console.print("[red]✗ Harness definition errors:[/red]")
            for e in errors:
                console.print(f"  • {e}")
            raise typer.Exit(1)
        version, is_new = _harness_mod.save_harness_from_dict(data)

    action = "[green]✓ Created[/green]" if is_new else "[blue]↑ Updated[/blue]"
    console.print(f"{action} harness [bold]{name}[/bold] → [cyan]{version}[/cyan]")


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


if __name__ == "__main__":
    main()
