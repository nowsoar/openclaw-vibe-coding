# json_diff — JSON Diff CLI Tool

A lightweight command-line tool to compare two JSON files and display their differences in a readable format. Built with Python standard library only — no third-party dependencies.

## Features

- Detects **added**, **removed**, and **modified** fields recursively
- Supports nested objects and arrays (with index-based diffing)
- `--color` flag for ANSI colorized output (green = added, red = removed, yellow = modified)
- `--ignore-keys` flag to skip specific keys during comparison
- Exit code `0` if no differences, `1` if differences found (pipeline-friendly)

## Requirements

- Python 3.6+
- No third-party packages needed

## Usage

```bash
python3 json_diff.py <file_a> <file_b> [--color] [--ignore-keys KEY [KEY ...]]
```

### Arguments

| Argument | Description |
|---|---|
| `file_a` | Base JSON file |
| `file_b` | JSON file to compare against |
| `--color` | Enable colorized output |
| `--ignore-keys KEY ...` | Keys to skip during comparison |

## Examples

### Basic comparison

```bash
python3 json_diff.py examples/a.json examples/b.json
```

**`examples/a.json`**
```json
{
  "name": "Alice",
  "age": 30,
  "email": "alice@example.com",
  "roles": ["admin", "user"],
  "address": { "city": "Beijing", "zip": "100000" }
}
```

**`examples/b.json`**
```json
{
  "name": "Alice",
  "age": 31,
  "roles": ["admin", "user", "moderator"],
  "address": { "city": "Shanghai", "zip": "200000" },
  "phone": "123-456-7890"
}
```

**Output:**
```
~ MODIFIED address.city: "Beijing" -> "Shanghai"
~ MODIFIED address.zip: "100000" -> "200000"
~ MODIFIED age: 30 -> 31
- REMOVED  email: "alice@example.com"
+ ADDED    phone: "123-456-7890"
+ ADDED    roles[2]: "moderator"

Summary: +2 added, -1 removed, ~3 modified
```

### Ignore specific keys

```bash
python3 json_diff.py examples/a.json examples/b.json --ignore-keys email age
```

**Output:**
```
~ MODIFIED address.city: "Beijing" -> "Shanghai"
~ MODIFIED address.zip: "100000" -> "200000"
+ ADDED    phone: "123-456-7890"
+ ADDED    roles[2]: "moderator"

Summary: +2 added, -0 removed, ~2 modified
```

### Colorized output

```bash
python3 json_diff.py examples/a.json examples/b.json --color
```

Output is the same as above but with ANSI colors: green for additions, red for removals, yellow for modifications.

### No differences

```bash
python3 json_diff.py examples/a.json examples/a.json
```

**Output:**
```
No differences found.
```

## Path notation

Differences are reported using dot notation for object keys and bracket notation for array indices:

- `address.city` — nested object field
- `roles[2]` — array element at index 2
- `a.b[0].c` — combined nesting
