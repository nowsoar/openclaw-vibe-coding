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
# init
# ---------------------------------------------------------------------------


@app.callback()
def _main() -> None:
    """HarnessKit — manage AI Agent runtimes like code."""


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
