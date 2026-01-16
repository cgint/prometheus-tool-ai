# Log Agent — Example (high level)
This is a “how it behaves” walkthrough of the Log Agent. It focuses on the ReAct loop, the Python REPL tool, and the small set of tools we hand to that REPL.

Diagram source: [docs/log_agent.d2](log_agent.d2)

![Log Agent (ReAct + Python REPL tool structure)](log_agent.svg)

## The tools it has (in this module)
- ReAct tool: `python_repl` (a persistent Python session)
- Tools available *inside* `python_repl`:
  - `fetch_log_data(path)` (read a repo-local log file, bounded)
  - `get_available_files()` (list sample log files)
- Tracking “sidecar” (not a tool the agent calls directly):
  - `ToolCallCallback` + `ToolUsageTracker` (records tool usage + registered outputs)

## Why this pattern matters
The key benefit is that big, messy data (like large log files) does **not** need to be pasted into the LLM’s context window. The data is read and processed *outside* the model via `python_repl`, and only the small, human-ready results are registered and referenced in the final answer.

This helps:
- Reduce context-window pressure (you don’t “spend tokens” on raw logs).
- Reduce cost (less text sent to the model).
- Reduce hallucination risk for computed values (counts/totals come from code, not guesswork).
- Keep you in control: you can inspect the tool code, inputs, and registered outputs without ever pasting the full logs into the prompt.

It doesn’t make hallucinations impossible: the model can still explain results incorrectly, but the core computed artifacts are inspectable and reproducible from the tool code and inputs.

## One concrete run (example)
**User question (input):** “For these log files, count how many lines contain `ERROR`, and give me totals.”

Imagine you just dropped three log files into the repo. They might be huge, so the agent doesn’t try to “read everything into its brain” or do mental math.

1) **ReAct decides to compute.** It recognizes the task is counting and chooses the calculator: `python_repl`.
2) **ReAct delegates to `python_repl`.** The REPL is where the real work happens.
3) **The REPL pulls only what it’s allowed to pull.** For each file, it calls `fetch_log_data(path=...)`, which reads repo-local data and bounds the read.
4) **The REPL counts and formats.** It scans lines for `ERROR`, builds a small bullet list, and sums a total.
5) **The REPL registers “final answer parts”.** It stores display-ready strings under names like `file_error_counts` and `total_error_count`.
6) **ReAct responds with placeholders.** The final answer references `{total_error_count}` and `{file_error_counts}` so the computed content is injected cleanly.
7) **Callback + tracker tie it together.** `ToolCallCallback` records the `python_repl` usage and the registered variables into `ToolUsageTracker`.

### What one `python_repl` tool call can look like
Why this is useful:
- The logs stay outside the LLM context window; the REPL code reads/processes them directly and only produces compact results.
- `register_for_final_output(...)` links code → answer by saving display-ready strings under names that the final answer can reference as `{placeholders}`.

The REPL receives Python code like this (Python only):
```python
log_files = [
    "src/optimize_agent/sample_logs/file1.log",
    "src/optimize_agent/sample_logs/file2.log",
    "src/optimize_agent/sample_logs/file3.log",
]

error_counts = {}
total_errors = 0

for file_path in log_files:
    log_content = fetch_log_data(path=file_path)
    if log_content:
        lines = log_content.split("\n")
        error_count = sum(1 for line in lines if "ERROR" in line)
        error_counts[file_path] = error_count
        total_errors += error_count

file_counts_str = "\n".join([f"- {file}: {count}" for file, count in error_counts.items()])

register_for_final_output(
    file_error_counts=file_counts_str,
    total_error_count=str(total_errors),
)
```

And here’s how that connects to what gets produced:

#### 1) Registered vars
These are the named, display-ready strings produced by `register_for_final_output(...)`.
```
REGISTERED VARS:
  file_error_counts_str: - file1.log: 2
- file2.log: 0
- file3.log: 4
  total_errors_str: 6
```

#### 2) Raw model answer (with placeholders)
This is the model’s answer text before substitution; it references the registered vars by name.
```
RAW pred.answer:
Here are the error counts for each file:
{file_error_counts_str}

Total errors across all files: {total_errors_str}
```

#### 3) Rendered final answer
This is what a user sees after placeholders are filled with the registered values.
```
RENDERED final_answer:
Here are the error counts for each file:
- file1.log: 2
- file2.log: 0
- file3.log: 4

Total errors across all files: 6
```

 
