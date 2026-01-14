# prometheus-tool-ai

A small sandbox for building **agentic Prometheus workflows** with **DSPy ReAct** and a **persistent Python REPL tool**.

The core idea: let a ReAct agent call Prometheus discovery/query tools, then use a persistent `python_repl` scratchpad to **store tool outputs in variables**, **peek at their structure**, and **compute follow-up answers** (counts, grouping, reshaping) across multiple tool calls.

## What's inside

- **`src/prom_agent.py`**
  - Example DSPy `ReAct` agent wired to Prometheus tools plus `python_repl`.
  - Demonstrates the intended "peek → compute" workflow over Prometheus JSON.

- **`src/repl/python_tool_repl.py`**
  - `build_python_repl_tool(...)` creates a **persistent** `python_repl` tool.
  - It preserves Python state across calls and exposes prior tool outputs as bindings like:
    - `<tool_name>_<n>` (0-based per tool, e.g. `prom_query_0`)
    - `_` (most recent non-python tool output)

- **`src/promwrap/`**
  - Minimal Prometheus HTTP API wrapper + guardrails (timeouts, range limits, min step, max points).
  - `src/promwrap/cli.py` provides a `promwrap` CLI.

- **`src/tools/prom.py`**
  - Thin "tool" functions around `promwrap` for agents:
    - `prom_metrics`, `prom_labels`, `prom_label_values`, `prom_query`, `prom_range`, `prom_buildinfo`

## Requirements

- Python **3.13** (see `pyproject.toml`)
- Uses `uv` for dependency management (see `uv.lock`)

## Install (recommended)

```bash
uv sync
```

## Configure Prometheus access

By default the code uses `PROM_URL` from `src/constants.py` (currently set to an internal URL).

If your Prometheus needs auth or custom headers/certs, use the `promwrap` CLI flags (see below).

## Run the ReAct agent demo

The repo exposes a console script:

- `prom` → `prom_agent:main` (see `pyproject.toml`)

Run:

```bash
uv run prom
```

## Run the Prometheus wrapper CLI (`promwrap`)

The CLI supports:

- `ping`
- `buildinfo`
- `metrics [--match REGEX] [--limit N]`
- `labels [--limit N]`
- `label-values <label> [--match REGEX] [--limit N]`
- `query <promql> [--time now|RFC3339]`
- `range <promql> --start <lookback|RFC3339> [--end now|RFC3339] [--step 30s|1m|...]`
- `series --match '<selector>' [--start ...] [--end ...] [--max-series N]`

Examples:

```bash
uv run python -m promwrap.cli ping --output json
uv run python -m promwrap.cli buildinfo --output json

uv run python -m promwrap.cli metrics --match 'kube_.*' --limit 50
uv run python -m promwrap.cli labels --limit 50
uv run python -m promwrap.cli label-values namespace --match 'argo.*' --limit 50

uv run python -m promwrap.cli query 'count(up)' --output json
uv run python -m promwrap.cli range 'sum(rate(http_requests_total[5m]))' --start 1h --step 30s --output json
```

Auth / TLS options (if needed):

- `--auth-header 'Bearer …'`
- `--header 'Name: value'` (repeatable)
- `--cookie 'name=value; ...'`
- `--ca-file`, `--cert-file`, `--key-file`
- `--insecure-skip-verify`

## Why the persistent `python_repl` tool matters

For many Prometheus questions, the hard part isn't running a single query—it's:

- discovering the right metric/labels
- inspecting returned JSON structure
- computing aggregates (counts, uniques, top-k labels) over results
- iterating safely

This repo's pattern is: **use tools to fetch data → use `python_repl` to analyze/reshape → reuse stored variables in follow-up calls**.

## Docs / context

- `PROMETHEUS_ASSISTANT.md`: product direction + requirements
- `TASK_WRAPPER_SPEC.md`: spec for the Prometheus wrapper + guardrails
- `PROMETHEUS_TOOLS_DETAIL.md`: detailed tool descriptions
- `RecursiveLanguageModels.txt`: inspiration for "REPL-as-context/scratchpad" patterns

## Notes

- This is a local/dev sandbox. Be mindful of:
  - query cost (range + step)
  - high-cardinality selectors
  - leaking sensitive labels/values into external LLMs
