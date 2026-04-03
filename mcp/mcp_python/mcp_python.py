#!/usr/bin/env -S uv run --script
# /// script
# dependencies = [
#   "fastmcp", "numpy", "polars", "scipy", "openpyxl", "pyyaml", "tomli", "requests"
# ]
# ///

import os
import re
import subprocess
import sys
from datetime import datetime
from typing import Annotated

from fastmcp import FastMCP

# Initialize FastMCP
mcp = FastMCP("PythonEngine")


def _get_sandbox_profile(cwd: str) -> str:
    """Builds the macOS Seatbelt sandbox profile string."""
    sandbox_rules_path = os.path.join(cwd, ".sandbox-rules")
    extra_rules_list = []

    if os.path.exists(sandbox_rules_path):
        try:
            with open(sandbox_rules_path, "r") as f:
                now = datetime.now()
                for line in f:
                    match = re.search(r";\s*EXPIRES:\s*([^ ]*)", line)
                    if match:
                        date_str = match.group(1).strip()
                        try:
                            expiry = datetime.fromisoformat(date_str)
                            if expiry < now:
                                continue
                        except ValueError:
                            raise ValueError(
                                f"Invalid EXPIRES format: '{date_str}'. Expected ISO 8601 (YYYY-MM-DDTHH:MM:SS)."
                            )
                    extra_rules_list.append(line.strip())
        except Exception as e:
            # Re-raise to be caught by the tool
            raise RuntimeError(f"Error reading .sandbox-rules: {str(e)}")

    extra_rules = "\n".join(extra_rules_list)

    # Note: Rules are evaluated in order; the LAST matching rule wins.
    # To ensure specific denials are enforced, they must come after broad allowances.
    return f"""
    (version 1)
    (allow default)
    (deny network*)
    (deny file-write*)
    (allow file-write* (subpath "/dev")) ; Allow writing to stdout/stderr
    (allow file-write* (subpath "{cwd}")) ; Allow writing to current directory
    {extra_rules}
    (deny file-read* (literal "{sandbox_rules_path}")) ; Prevent reading the rules file
    (deny file-write* (literal "{sandbox_rules_path}")) ; Prevent modifying the rules file
    """


# --- Sandboxed Standard Python (CPython) ---
@mcp.tool()
def execute_python(
    code: Annotated[
        str,
        "The complete, self-contained Python script to execute. Must include print() statements to yield output.",
    ],
) -> str:
    """
    Executes a self-contained Python script.
    DO: Delegate entire complex tasks to a single, intelligent script. Write end-to-end programs that handle their own intermediate logic, data, and imports, and then use print() to output the final result.
    DO NOT: Use this as a line-by-line interactive shell. Do not make multiple back-and-forth tool calls to calculate intermediate steps.
    CRITICAL: The environment is STRICTLY STATELESS. Every execution starts entirely fresh. You must consolidate all variables, imports, and logic into one single tool call.

    Available libraries: numpy, polars, scipy, openpyxl, pyyaml, tomli, requests
    """

    try:
        sandbox_profile = _get_sandbox_profile(os.getcwd())

        # sys.executable ensures it uses the same Python (and dependencies) uv is using
        result = subprocess.run(
            ["sandbox-exec", "-p", sandbox_profile, sys.executable, "-c", code],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,  # This interleaves stderr into stdout chronologically
            text=True,
            timeout=10,
        )

        return result.stdout.strip() or "Success (no output)."

    except subprocess.TimeoutExpired:
        return "Error: Execution timed out after 10 seconds. Check for infinite loops."


if __name__ == "__main__":
    mcp.run()
