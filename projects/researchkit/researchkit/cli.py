"""ResearchKit CLI"""
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TaskProgressColumn
from rich.table import Table
from rich import print as rprint

app = typer.Typer(
    name="researchkit",
    help="ResearchKit — AI 驱动的自动化调研平台",
    no_args_is_help=True,
)
console = Console()

RESEARCHKIT_DIR = Path.home() / ".researchkit"


@app.command("init")
def init():
    """初始化 ResearchKit 配置目录"""
    RESEARCHKIT_DIR.mkdir(parents=True, exist_ok=True)

    config_path = RESEARCHKIT_DIR / "config.yaml"
    if not config_path.exists():
        config_path.write_text(
            "ai:\n"
            "  default_model: gpt-4o-mini\n"
            "  api_key: ${OPENAI_API_KEY}\n"
            "  base_url: https://api.openai.com/v1\n"
            "  task_models:\n"
            "    synthesize: gpt-4o\n"
            "  cost_limit_usd: 3.0\n\n"
            "cache:\n"
            "  enabled: true\n"
            "  ttl_days: 3\n\n"
            "output:\n"
            "  dir: ~/Documents/research/\n",
            encoding="utf-8",
        )
        console.print(f"✓ 已创建配置文件：{config_path}")
    else:
        console.print(f"[dim]配置文件已存在：{config_path}[/dim]")

    sources_path = RESEARCHKIT_DIR / "sources.yaml"
    if not sources_path.exists():
        sources_path.write_text(
            "# 数据源库配置\n\n"
            "wechat:\n"
            "  auth: ~/.researchkit/wechat-auth.json\n"
            "  accounts:\n"
            "    - { name: 36氪, biz: MzI2NDk5NzA0NA== }\n"
            "    - { name: 虎嗅APP, biz: MTQzMjE1NjQwNA== }\n\n"
            "rss:\n"
            "  feeds:\n"
            "    - { name: TechCrunch, url: https://techcrunch.com/feed/ }\n",
            encoding="utf-8",
        )
        console.print(f"✓ 已创建数据源配置：{sources_path}")

    history_path = RESEARCHKIT_DIR / "history.json"
    if not history_path.exists():
        history_path.write_text("[]", encoding="utf-8")

    console.print("\n[green]✓ ResearchKit 初始化完成[/green]")
    console.print(f"\n下一步：编辑 [bold]{config_path}[/bold] 填入 AI 接口配置")


@app.command("run")
def run(
    task_file: Path = typer.Argument(..., help="调研任务 YAML 文件路径"),
    dry_run: bool = typer.Option(False, "--dry-run", help="预览模式，不调用 AI"),
    config: Optional[Path] = typer.Option(None, "--config", help="全局配置文件路径"),
):
    """运行调研任务"""
    if not task_file.exists():
        console.print(f"[red]✗ 任务文件不存在：{task_file}[/red]")
        raise typer.Exit(1)

    from .core.config import load_global_config, load_task_config
    from .core.models import ResearchContext, ResearchTask, TaskStatus
    from .core.pipeline import Pipeline

    global_config = load_global_config(config)
    task_data = load_task_config(task_file)

    # 构建 ResearchContext
    context = ResearchContext(
        topic=task_data.get("topic", task_data.get("name", "")),
        query=task_data.get("query", ""),
        keywords=task_data.get("keywords", []),
        time_range_days=_parse_time_range(task_data.get("time_range", "30d")),
        language=task_data.get("language", "zh"),
    )

    # 构建 ResearchTask
    task = ResearchTask(
        name=task_data.get("name", "调研任务"),
        context=context,
        sources_config=task_data.get("sources", {}),
        pipeline_config=task_data.get("pipeline", []),
        output_config=task_data.get("output", {}),
    )

    console.print(f"\n[bold]📋 {task.name}[/bold]")
    console.print(f"   主题：{context.topic}")
    console.print(f"   时间范围：{context.time_range_days} 天")

    if dry_run:
        console.print("\n[yellow]⚡ Dry-run 模式：不会调用 AI，只显示任务配置[/yellow]")
        console.print(f"\n启用的数据源：")
        for src, cfg in task.sources_config.items():
            if cfg.get("enabled"):
                console.print(f"  • {src}")
        console.print(f"\n流水线步骤：")
        for step in task.pipeline_config:
            console.print(f"  • {step.get('step')}")
        return

    # 执行流水线
    console.print()
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TaskProgressColumn(),
        console=console,
    ) as progress:
        fetch_task = progress.add_task("数据抓取", total=100)
        process_task = progress.add_task("内容处理", total=100)
        output_task = progress.add_task("生成报告", total=100)

        def on_progress(stage, current, total, msg=""):
            if stage == "fetch":
                pct = int(current / max(total, 1) * 100)
                progress.update(fetch_task, completed=pct, description=f"数据抓取 {msg}")
            elif stage == "process":
                pct = int(current / max(total, 1) * 100)
                progress.update(process_task, completed=pct, description=f"内容处理 {msg}")
            elif stage == "output":
                pct = int(current / max(total, 1) * 100)
                progress.update(output_task, completed=pct, description=f"生成报告 {msg}")

        pipeline = Pipeline(task, global_config)
        try:
            report_md = pipeline.run(progress_callback=on_progress)
            progress.update(fetch_task, completed=100)
            progress.update(process_task, completed=100)
            progress.update(output_task, completed=100)
        except Exception as e:
            console.print(f"\n[red]✗ 调研任务失败：{e}[/red]")
            raise typer.Exit(1)

    # 保存历史
    _save_history(task.name, len(task.articles))

    console.print(f"\n[green]✓ 调研完成[/green]")
    console.print(f"  共处理 [bold]{len(task.articles)}[/bold] 篇文章")
    console.print(f"  报告已保存到 ~/Documents/research/")


@app.command("check-sources")
def check_sources(
    config: Optional[Path] = typer.Option(None, "--config"),
):
    """检查各数据源连接状态"""
    from .core.config import load_global_config, load_sources_config
    from .sources.wechat import WeChatSource
    from .sources.rss import RSSSource
    from .sources.web import WebSource

    sources_cfg = load_sources_config()

    table = Table(title="数据源状态", show_header=True)
    table.add_column("数据源", style="bold")
    table.add_column("状态")
    table.add_column("详情")

    checks = {
        "wechat": (WeChatSource, sources_cfg.get("wechat", {})),
        "rss": (RSSSource, sources_cfg.get("rss", {})),
        "web": (WebSource, sources_cfg.get("web", {})),
    }

    for name, (cls, cfg) in checks.items():
        src = cls(name=name, config=cfg)
        ok, msg = src.health_check()
        status = "[green]● 正常[/green]" if ok else "[red]✗ 异常[/red]"
        table.add_row(name, status, msg)

    console.print(table)


@app.command("history")
def history():
    """查看历史调研任务"""
    history_path = RESEARCHKIT_DIR / "history.json"
    if not history_path.exists():
        console.print("[dim]暂无历史记录[/dim]")
        return

    records = json.loads(history_path.read_text(encoding="utf-8"))
    if not records:
        console.print("[dim]暂无历史记录[/dim]")
        return

    table = Table(title="历史调研任务", show_header=True)
    table.add_column("时间", style="dim")
    table.add_column("任务名称", style="bold")
    table.add_column("文章数", justify="right")

    for r in reversed(records[-20:]):
        table.add_row(r.get("time", ""), r.get("name", ""), str(r.get("articles", 0)))

    console.print(table)


def _parse_time_range(value: str) -> int:
    """解析时间范围字符串，如 '30d' / '7d' / '30'"""
    if isinstance(value, int):
        return value
    value = str(value).lower().strip()
    if value.endswith("d"):
        return int(value[:-1])
    return int(value)


def _save_history(name: str, article_count: int):
    history_path = RESEARCHKIT_DIR / "history.json"
    records = []
    if history_path.exists():
        try:
            records = json.loads(history_path.read_text(encoding="utf-8"))
        except Exception:
            pass
    records.append({
        "time": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "name": name,
        "articles": article_count,
    })
    history_path.write_text(json.dumps(records, ensure_ascii=False, indent=2), encoding="utf-8")


if __name__ == "__main__":
    app()
