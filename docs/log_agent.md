# Log Agent (`src/log_agent.py`)
This module defines a small DSPy ReAct agent that can read bounded, repo-local log files via a Python REPL tool, compute results inside the REPL, and write structured run artifacts (summary/usage/history/final answer) to the project’s logging output.

Diagram source: [docs/log_agent.d2](log_agent.d2)

![Log Agent (ReAct + Python REPL tool structure)](log_agent.svg)

## What it is
`LogAgentModule` wraps a `dspy.ReAct` agent configured with:
- A persistent Python REPL tool (built by `build_python_repl_tool`)
- Two “sub-tools” exposed inside that REPL: `fetch_log_data()` and `get_available_files()`
- A `ToolUsageTracker` plus `ToolCallCallback` to capture tool usage and “final-output” registered variables

The prompt contract (in `AgentSignature`) strongly encourages doing computation in the REPL and returning a final answer that uses placeholders for registered variables, rather than pasting computed data directly.

## Key pieces
- `fetch_log_data(path, max_bytes=200_000)`: reads a repo-relative file path, enforces that it resolves within the repo root, bounds reads by bytes, and decodes as UTF-8 (replace errors).
- `get_available_files()`: lists `*.log` files under `src/optimize_agent/sample_logs/` and returns repo-relative paths.
- `AgentSignature`: the ReAct signature, including a policy block that guides tool usage and final-output registration.
- `LogAgentModule.forward(question)`: runs the ReAct agent with callbacks enabled, then attaches `registered_vars` and `registered_var_names` onto the returned `dspy.Prediction`.
- `main()`: configures an LM (`MODEL_NAME_GEMINI_2_5_FLASH`), asks a sample question over three sample log files, runs the agent, and persists logs via `write_agent_logs(...)`.

## Data flow (high level)
1) A question is passed to `LogAgentModule.forward()`.
2) `dspy.ReAct` runs up to `max_iters=10`, calling the Python REPL tool as needed.
3) Inside the REPL, the agent can call:
   - `fetch_log_data()` to read a specific log file (repo-scoped, size-bounded)
   - `get_available_files()` to discover sample log files
4) The tracker captures tool calls and any `register_for_final_output(...)` values.
5) `forward()` returns a prediction augmented with the registered variables for downstream display/logging.
6) `write_agent_logs()` writes run artifacts (summary/usage/history/final answer) for inspection and debugging.

## Safety boundaries (why the file reading is constrained)
`fetch_log_data()` resolves paths against the repository root and rejects any target outside it. This prevents the agent from reading arbitrary host files (e.g., `~/.ssh/*`) even if the REPL is otherwise capable.

## How to run
- From repo root: `uv run python src/log_agent.py`

Expected outputs are written via `write_agent_logs(...)` (see `src/agent_logging.py` for exact file locations and formats).

## Practical extension points
- Add additional read-only helpers as REPL sub-tools (e.g., parse JSON logs, extract time ranges) and keep them repo-scoped.
- Tune `max_bytes` and `max_iters` based on log size and desired agent behavior.
- Swap the model name in `main()` or wire `LogAgentModule` into a larger runner (e.g., a CLI or web endpoint) while keeping the same tracker/logging contract.
