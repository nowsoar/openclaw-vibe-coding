#!/usr/bin/env python3
"""JSON diff tool: compare two JSON files and show differences."""

import argparse
import json
import sys


# ANSI color codes
class Color:
    RED = "\033[91m"
    GREEN = "\033[92m"
    YELLOW = "\033[93m"
    CYAN = "\033[96m"
    RESET = "\033[0m"
    BOLD = "\033[1m"


def colorize(text, color, use_color):
    if use_color:
        return f"{color}{text}{Color.RESET}"
    return text


def load_json(path):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        print(f"Error: file not found: {path}", file=sys.stderr)
        sys.exit(1)
    except json.JSONDecodeError as e:
        print(f"Error: invalid JSON in {path}: {e}", file=sys.stderr)
        sys.exit(1)


def format_value(value):
    if isinstance(value, str):
        return json.dumps(value)
    return json.dumps(value, ensure_ascii=False)


def diff(a, b, path, ignore_keys, use_color, results):
    """Recursively diff two values, recording changes into results list."""
    if isinstance(a, dict) and isinstance(b, dict):
        all_keys = set(a) | set(b)
        for key in sorted(all_keys):
            if key in ignore_keys:
                continue
            child_path = f"{path}.{key}" if path else key
            if key not in a:
                results.append((
                    "added",
                    child_path,
                    None,
                    b[key],
                ))
            elif key not in b:
                results.append((
                    "removed",
                    child_path,
                    a[key],
                    None,
                ))
            else:
                diff(a[key], b[key], child_path, ignore_keys, use_color, results)

    elif isinstance(a, list) and isinstance(b, list):
        max_len = max(len(a), len(b))
        for i in range(max_len):
            child_path = f"{path}[{i}]"
            if i >= len(a):
                results.append(("added", child_path, None, b[i]))
            elif i >= len(b):
                results.append(("removed", child_path, a[i], None))
            else:
                diff(a[i], b[i], child_path, ignore_keys, use_color, results)
    else:
        if a != b:
            results.append(("modified", path, a, b))


def print_results(results, use_color):
    if not results:
        msg = "No differences found."
        print(colorize(msg, Color.CYAN, use_color))
        return

    counts = {"added": 0, "removed": 0, "modified": 0}

    for kind, path, old_val, new_val in results:
        counts[kind] += 1
        if kind == "added":
            prefix = colorize("+ ADDED   ", Color.GREEN, use_color)
            val_str = colorize(format_value(new_val), Color.GREEN, use_color)
            path_str = colorize(path, Color.BOLD, use_color)
            print(f"{prefix} {path_str}: {val_str}")
        elif kind == "removed":
            prefix = colorize("- REMOVED ", Color.RED, use_color)
            val_str = colorize(format_value(old_val), Color.RED, use_color)
            path_str = colorize(path, Color.BOLD, use_color)
            print(f"{prefix} {path_str}: {val_str}")
        elif kind == "modified":
            prefix = colorize("~ MODIFIED", Color.YELLOW, use_color)
            old_str = colorize(format_value(old_val), Color.RED, use_color)
            new_str = colorize(format_value(new_val), Color.GREEN, use_color)
            path_str = colorize(path, Color.BOLD, use_color)
            print(f"{prefix} {path_str}: {old_str} -> {new_str}")

    print()
    added_str = colorize(f'+{counts["added"]} added', Color.GREEN, use_color)
    removed_str = colorize(f'-{counts["removed"]} removed', Color.RED, use_color)
    modified_str = colorize(f'~{counts["modified"]} modified', Color.YELLOW, use_color)
    summary = f"Summary: {added_str}, {removed_str}, {modified_str}"
    print(summary)


def main():
    parser = argparse.ArgumentParser(
        description="Compare two JSON files and show differences."
    )
    parser.add_argument("file_a", help="First JSON file (base)")
    parser.add_argument("file_b", help="Second JSON file (compare against)")
    parser.add_argument(
        "--color", action="store_true", help="Enable colorized output"
    )
    parser.add_argument(
        "--ignore-keys",
        metavar="KEY",
        nargs="+",
        default=[],
        help="Keys to ignore during comparison (e.g. --ignore-keys id timestamp)",
    )
    args = parser.parse_args()

    a = load_json(args.file_a)
    b = load_json(args.file_b)

    ignore_keys = set(args.ignore_keys)

    results = []
    diff(a, b, "", ignore_keys, args.color, results)
    print_results(results, args.color)

    # Exit code: 0 = no diff, 1 = diff found
    sys.exit(0 if not results else 1)


if __name__ == "__main__":
    main()
