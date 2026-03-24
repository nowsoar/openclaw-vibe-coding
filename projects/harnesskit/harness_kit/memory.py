"""Memory system — persists conversation history across harness runs.

Scopes
------
session  : in-process only; nothing written to disk.
harness  : stored in .harness/memory/{harness_name}.json
global   : stored in .harness/memory/global.json
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _memory_dir(base: Path | None = None) -> Path:
    from harness_kit.config import harness_dir
    return harness_dir(base) / "memory"


def _memory_file(scope: str, harness_name: str, base: Path | None = None) -> Path:
    root = _memory_dir(base)
    if scope == "global":
        return root / "global.json"
    return root / f"{harness_name}.json"


def _empty_memory() -> dict[str, Any]:
    return {
        "turns": [],
        "metadata": {
            "total_tokens": 0,
            "summary": None,
        },
    }


def _simple_summary(turns: list[dict[str, Any]]) -> str:
    """Create a simple text summary when no LLM is available."""
    lines = [f"{t['role'].upper()}: {t['content'][:120]}" for t in turns]
    return f"[历史摘要 {len(turns)} 轮]\n" + "\n".join(lines)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def load_memory(
    scope: str,
    harness_name: str,
    base: Path | None = None,
) -> dict[str, Any]:
    """Load memory from disk.

    Returns an empty memory structure for 'session' scope or when the file
    does not exist / cannot be parsed.
    """
    if scope == "session":
        return _empty_memory()
    path = _memory_file(scope, harness_name, base)
    if not path.exists():
        return _empty_memory()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return _empty_memory()
    # Ensure required keys are present
    data.setdefault("turns", [])
    data.setdefault("metadata", {})
    data["metadata"].setdefault("total_tokens", 0)
    data["metadata"].setdefault("summary", None)
    return data


def save_memory(
    data: dict[str, Any],
    scope: str,
    harness_name: str,
    base: Path | None = None,
) -> None:
    """Persist memory to disk.  No-op for 'session' scope."""
    if scope == "session":
        return
    path = _memory_file(scope, harness_name, base)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(data, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def add_turn(
    memory: dict[str, Any],
    role: str,
    content: str,
    tokens: int = 0,
) -> None:
    """Append a turn to *memory* in-place."""
    memory["turns"].append(
        {
            "role": role,
            "content": content,
            "timestamp": datetime.now(tz=timezone.utc).isoformat(),
        }
    )
    memory["metadata"]["total_tokens"] = (
        memory["metadata"].get("total_tokens", 0) + tokens
    )


def get_history_messages(memory: dict[str, Any]) -> list[dict[str, str]]:
    """Return turns as an LLM-compatible message list (role + content only)."""
    return [
        {"role": t["role"], "content": t["content"]}
        for t in memory.get("turns", [])
    ]


def compress_memory(
    memory: dict[str, Any],
    max_turns: int,
    llm_config: Any | None = None,
) -> bool:
    """Compress memory when turn count exceeds *max_turns*.

    Keeps the most recent ``max_turns // 2`` turns and summarises the rest.
    Uses the LLM for summarisation when *llm_config* is provided; falls back
    to a plain-text summary otherwise.

    Returns True if compression was performed.
    """
    turns = memory.get("turns", [])
    if len(turns) <= max_turns:
        return False

    keep_count = max(1, max_turns // 2)
    to_summarise = turns[:-keep_count]
    recent = turns[-keep_count:]

    if llm_config is not None:
        try:
            from harness_kit.llm import call_llm
            summary_messages = [
                {
                    "role": "system",
                    "content": "请将以下对话历史压缩为简洁的摘要，保留所有关键信息。",
                },
                {
                    "role": "user",
                    "content": "\n".join(
                        f"{t['role'].upper()}: {t['content']}"
                        for t in to_summarise
                    ),
                },
            ]
            resp = call_llm(summary_messages, llm_config, stream=False)
            summary_text = resp.content
        except Exception:
            summary_text = _simple_summary(to_summarise)
    else:
        summary_text = _simple_summary(to_summarise)

    memory["turns"] = recent
    memory["metadata"]["summary"] = summary_text
    return True


def search_memory(memory: dict[str, Any], keyword: str) -> list[dict[str, Any]]:
    """Return turns whose content contains *keyword* (case-insensitive)."""
    kw = keyword.lower()
    return [t for t in memory.get("turns", []) if kw in t.get("content", "").lower()]


def clear_memory(
    scope: str,
    harness_name: str,
    base: Path | None = None,
) -> bool:
    """Delete persisted memory file.

    Returns True when a file was removed; False for 'session' scope or when
    no file existed.
    """
    if scope == "session":
        return False
    path = _memory_file(scope, harness_name, base)
    if path.exists():
        path.unlink()
        return True
    return False


def list_memory_files(base: Path | None = None) -> list[dict[str, Any]]:
    """List all persisted memory files with basic metadata."""
    root = _memory_dir(base)
    if not root.exists():
        return []
    results: list[dict[str, Any]] = []
    for p in sorted(root.glob("*.json")):
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            data = {}
        harness_name = p.stem  # "global" or a harness name
        scope = "global" if harness_name == "global" else "harness"
        results.append(
            {
                "harness": harness_name,
                "scope": scope,
                "turns": len(data.get("turns", [])),
                "total_tokens": data.get("metadata", {}).get("total_tokens", 0),
                "has_summary": bool(data.get("metadata", {}).get("summary")),
                "file": str(p),
            }
        )
    return results
