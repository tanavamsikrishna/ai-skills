# Sandbox Rules Configuration (`.sandbox-rules`)

The `PythonEngine` MCP tool supports a dynamic sandbox configuration via a `.sandbox-rules` file located in the current working directory. This file allows you to extend the macOS Seatbelt sandbox profile used when executing Python scripts.

## File Format
The file should contain standard macOS Seatbelt (Scheme-based) sandbox rules. Each rule should be on its own line.

### Basic Example
```scheme
(allow file-read* (subpath "/Users/vamsi/data"))
(deny file-write* (subpath "/etc"))
```

## Expiry Feature
You can add an optional expiry timestamp to any rule. Rules that have expired will be automatically filtered out by the `execute_python` tool before the sandbox is initialized.

### Syntax
Append a comment to the rule using the following format:
`; EXPIRES: YYYY-MM-DDTHH:MM:SS`

### Example with Expiry
```scheme
; Grant temporary read access to a specific folder until April 5th, 2026
(allow file-read* (subpath "/Users/vamsi/sensitive-project")) ; EXPIRES: 2026-04-05T00:00:00

; This rule will be ignored after the specified time
(allow network-outbound (remote ip "192.168.1.1:80")) ; EXPIRES: 2026-04-03T18:30:00
```

## How it Works
1. **Refresh on Call:** The `.sandbox-rules` file is read and parsed every time the `execute_python` tool is invoked.
2. **Validation:** The tool checks the current system time against any `; EXPIRES:` metadata found in the file.
3. **Strict Validation:** If an `EXPIRES:` timestamp is malformed or invalid (not valid ISO 8601), the tool will raise an explicit error to prevent accidental bypassing of expiration dates.
4. **Statelessness:** Since the rules are appended to the profile dynamically, you can modify `.sandbox-rules` at any time to change the permissions of the next execution.
