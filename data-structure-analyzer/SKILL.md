---
name: data-structure-analyzer
description: Analyze the structure of JSON, JSONL, YAML, TOML, and JSON5 files using the "path" mapping method.
---

# Data Structure Analyzer

Extract and flatten schema paths from complex data files to understand their structure.

## Usage

Run the unified analyzer:

- **JSON, JSONL, YAML, TOML, JSON5**: `./scripts/analyze.py file.ext`

The script automatically detects the file type based on its extension.

## Implementation Details

- **Language**: Python 3.10+
- **Dependency Management**: Managed via `uv` (requires `PyYAML`, `json5`).
- **Path Generation**: Flattens nested objects and arrays using dot notation (e.g., `parent.child.*.grandchild`).
- **Safety**: Includes cycle detection for YAML/JSON5 and robust quoting for keys with special characters.
- **Errors**: Standard Python exceptions (like `ImportError`, `FileNotFoundError`, or parser-specific errors) are provided for easy interpretation and resolution.
