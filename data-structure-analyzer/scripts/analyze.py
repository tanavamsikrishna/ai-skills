#!/usr/bin/env -S uv run -q --script
# /// script
# dependencies = ["PyYAML", "json5"]
# ///

import json
import os
import sys


def quote_key(key):
    s = str(key)
    if any(c in s for c in ". []\"'()"):
        return f'"{s.replace('"', '\\"')}"'
    return s


def get_paths(obj, current_path_parts=None, paths=None, seen=None):
    if paths is None:
        paths = set()
    if current_path_parts is None:
        current_path_parts = []
    if seen is None:
        seen = set()

    if isinstance(obj, (dict, list, tuple)):
        obj_id = id(obj)
        if obj_id in seen:
            return paths
        seen.add(obj_id)
        try:
            if isinstance(obj, dict):
                for k, v in obj.items():
                    new_parts = current_path_parts + [quote_key(k)]
                    paths.add(".".join(new_parts))
                    get_paths(v, new_parts, paths, seen)
            elif isinstance(obj, (list, tuple)):
                new_parts = current_path_parts + ["*"]
                paths.add(".".join(new_parts))
                for item in obj:
                    get_paths(item, new_parts, paths, seen)
        finally:
            seen.remove(obj_id)
    return paths


def main():
    if len(sys.argv) < 2:
        sys.exit(1)
    file_path = sys.argv[1]
    ext = os.path.splitext(file_path)[1].lower()
    paths = set()

    with open(file_path, "rb" if ext == ".toml" else "r") as f:
        if ext in (".yaml", ".yml"):
            import yaml

            get_paths(yaml.safe_load(f), [], paths)
        elif ext == ".json5":
            import json5

            get_paths(json5.load(f), [], paths)
        elif ext == ".toml":
            import tomllib

            get_paths(tomllib.load(f), [], paths)
        elif ext == ".jsonl":
            for line in f:
                if line.strip():
                    get_paths(json.loads(line), [], paths)
        else:  # Default to JSON
            get_paths(json.load(f), [], paths)

    for p in sorted(list(paths)):
        print(p)


if __name__ == "__main__":
    main()
