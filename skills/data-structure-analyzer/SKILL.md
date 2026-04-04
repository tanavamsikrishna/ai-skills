---
name: data-structure-analyzer
description: Extracts the structure of JSON, JSONL, YAML, TOML, and JSON5 files by listing all the unique path.to.the.keys. Use this to safely understand the schema of a data file without reading its entire contents into your context window, which is crucial for large files.
---

# Data Structure Analyzer

Extract and flatten schema paths from complex data files. This tool helps you understand the shape of a dataset without exceeding your token limits.

## Usage

Run the unified analyzer:

- **JSON, JSONL, YAML, TOML, JSON5**: `./scripts/analyze.py file.ext`.

## Example
File contents of *data.json*:
```json
{
  "company": "TechCorp",
  "location": "New York",
  "departments": {
    "engineering": {
      "manager": "Jane Doe",
      "headcount": 42,
      "technologies": [
        "Python",
        "Rust",
        "Go"
      ],
      "active_projects": [
        {
          "id": "PRJ-101",
          "name": "Data Migration",
          "priority": "High"
        },
        {
          "id": "PRJ-102",
          "name": "API V2",
          "priority": "Medium"
        }
      ]
    }
  }
}
```

Running `./scripts/analyze.py data.json` would produce
```txt
company
departments
departments.engineering
departments.engineering.active_projects
departments.engineering.active_projects.*
departments.engineering.active_projects.*.id
departments.engineering.active_projects.*.name
departments.engineering.active_projects.*.priority
departments.engineering.headcount
departments.engineering.manager
departments.engineering.technologies
departments.engineering.technologies.*
location
```

The script automatically detects the file type based on its extension.

## Implementation Details

- **Language**: Python 3.12+ (utilizes built-in `tomllib` for TOML).
- **Dependency Management**: Automatically managed by the script via `uv` (requires `PyYAML`, `json5`).
- **Path Generation**: Flattens nested objects and arrays using dot notation, replacing array indices with wildcards (e.g., `parent.child.*.grandchild`) to provide a clean schema summary.
- **Safety**: Includes cycle detection for YAML/JSON5 and robust quoting for keys with special characters (e.g., `parent."key.with.dots".child`).
- **Errors**: Standard Python exceptions (like `ImportError`, `FileNotFoundError`, or parser-specific errors) are provided for easy interpretation and resolution.
