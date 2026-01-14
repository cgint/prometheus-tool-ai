from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import dspy

from constants import MODEL_NAME_GEMINI_2_5_FLASH, PROM_URL
from promwrap import PromClient, PromwrapConfig
from promwrap.client import parse_step_seconds, resolve_time
from simplest_tool_logging import ToolCallCallback, ToolUsageTracker
from utils import dspy_configure, get_lm_for_model_name


def _client() -> PromClient:
    return PromClient(PromwrapConfig(base_url=PROM_URL))


def prom_buildinfo() -> Dict[str, Any]:
    """Fetch Prometheus buildinfo."""
    return _client().buildinfo()


def prom_metrics(match_regex: Optional[str] = None, limit: int = 50) -> List[str]:
    """List metric names (client-side regex filter)."""
    metrics = _client().metric_names()
    if match_regex:
        import re

        rx = re.compile(match_regex)
        metrics = [m for m in metrics if rx.search(m)]
    return metrics[:limit] if limit > 0 else metrics


def prom_labels(limit: int = 50) -> List[str]:
    """List label names."""
    labels = _client().label_names()
    return labels[:limit] if limit > 0 else labels


def prom_label_values(label: str, match_regex: Optional[str] = None, limit: int = 50) -> List[str]:
    """List values for a given label (client-side regex filter)."""
    values = _client().label_values(label)
    if match_regex:
        import re

        rx = re.compile(match_regex)
        values = [v for v in values if rx.search(v)]
    return values[:limit] if limit > 0 else values


def prom_query(promql: str, time: str = "now") -> Dict[str, Any]:
    """Run an instant query via /api/v1/query."""
    t = resolve_time(time, now=datetime.now(timezone.utc))
    return _client().query_instant(promql, time_rfc3339=t)


def prom_range(promql: str, start: str, end: str = "now", step: str = "30s") -> Dict[str, Any]:
    """Run a range query via /api/v1/query_range.

    start/end accept RFC3339, 'now', or lookback (e.g. 1h).
    step accepts 10s/1m/1h.
    """
    now = datetime.now(timezone.utc)
    s = resolve_time(start, now=now)
    e = resolve_time(end, now=now)
    step_seconds = parse_step_seconds(step)
    return _client().query_range(promql, start_rfc3339=s, end_rfc3339=e, step_seconds=step_seconds)


def build_python_repl_tool(tracker: ToolUsageTracker):
    """Build a python_repl tool with per-run state and access to prior tool outputs.

    Python available in `code` (read-only bindings from prior tool calls):
    - `prom_query_0`, `prom_query_1`, ...: outputs of previous prom_query calls
    - `<tool_name>_<n>`: outputs of other tools (0-based, per tool)
    - `_`: output of the most recent non-python tool call

    Python also has access to *tool functions* (which are logged to `tracker`):
    - `prom_buildinfo()`, `prom_metrics(...)`, `prom_labels()`, `prom_label_values(...)`
    - `prom_query(...)`, `prom_range(...)`

    Prefer using the bindings (e.g. `len(prom_query_0['data']['result'])`) instead of
    inlining large payloads.

    State is preserved across python_repl calls within a single agent run.
    """

    state: Dict[str, Any] = {}

    def python_repl(code: str) -> str:
        """Evaluate Python for calculations and light inspection.

        Available inside this REPL:
        - Prometheus helpers: `prom_query(...)`, `prom_range(...)`, `prom_metrics(...)`, `prom_labels()`, `prom_label_values(...)`, `prom_buildinfo()`.
          These are normal Python callables and their calls are logged like tools.

        Tips:
        - State persists across python_repl calls: assign to variables and reuse them later.
        - Prefer *multiple small python_repl calls*: fetch/peek first, then compute.
        - Use "peek" operations to learn the data shape instead of guessing (e.g. `type(x)`, `x.keys()` for dicts,
          `len(x)`, slicing like `x[:3]` for lists).

        Generic example flow (you choose the actual query and fields):
        1) `resp = prom_query('...')`
        2) `resp.keys()`
        3) `data = resp.get('data')`
        4) `type(data)`
        """

        import contextlib
        import io
        import math

        safe_builtins: Dict[str, Any] = {
            "abs": abs,
            "min": min,
            "max": max,
            "sum": sum,
            "len": len,
            "round": round,
            "range": range,
            "float": float,
            "int": int,
            "str": str,
            "bool": bool,
            "list": list,
            "dict": dict,
            "set": set,
            "tuple": tuple,
            "pow": pow,
            "sorted": sorted,
            "enumerate": enumerate,
            "print": print,
            # Introspection helpers for "peeking"
            "type": type,
            "isinstance": isinstance,
            "repr": repr,
        }

        def _wrap_tool(tool_name: str, func):
            def _wrapped(*args, **kwargs):
                import inspect

                # Convenience aliases (helps the model iterate without memorizing exact arg names).
                if tool_name in {"prom_query", "prom_range"} and "query" in kwargs and "promql" not in kwargs:
                    q = kwargs.pop("query")
                    kwargs["promql"] = q

                try:
                    bound = inspect.signature(func).bind_partial(*args, **kwargs)
                    bound.apply_defaults()
                    inputs = dict(bound.arguments)
                except Exception:
                    inputs = {"args": list(args), "kwargs": dict(kwargs)}

                out = func(*args, **kwargs)
                import contextlib as _contextlib
                import sys as _sys

                # Ensure tracker prints are not captured as python_repl output.
                with _contextlib.redirect_stdout(_sys.__stdout__):
                    tracker.log_tool_call(tool_name, inputs, out)
                return out

            _wrapped.__name__ = tool_name
            return _wrapped

        tools_env: Dict[str, Any] = {
            "prom_buildinfo": _wrap_tool("prom_buildinfo", prom_buildinfo),
            "prom_metrics": _wrap_tool("prom_metrics", prom_metrics),
            "prom_labels": _wrap_tool("prom_labels", prom_labels),
            "prom_label_values": _wrap_tool("prom_label_values", prom_label_values),
            "prom_query": _wrap_tool("prom_query", prom_query),
            "prom_range": _wrap_tool("prom_range", prom_range),
        }

        bindings: Dict[str, Any] = {}
        per_tool_counts: Dict[str, int] = {}
        for log in tracker.get_tool_logs():
            tool_name = str(log.get("tool_name", "tool"))
            if tool_name in {"python_repl", "finish"}:
                continue

            idx = per_tool_counts.get(tool_name, 0)
            per_tool_counts[tool_name] = idx + 1
            out = log.get("output")
            bindings[f"{tool_name}_{idx}"] = out
            bindings["_"] = out

        env: Dict[str, Any] = {"__builtins__": safe_builtins, "math": math}
        env.update(tools_env)
        env.update(state)
        env.update(bindings)

        if ";" in code:
            return "ERROR: Please avoid semicolons; split work across multiple python_repl calls."

        if len(code.splitlines()) > 12:
            return "ERROR: Too many lines for one python_repl call; split work across multiple calls."

        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            try:
                compiled = compile(code, "<python_repl>", "eval")
                result = eval(compiled, env, env)
            except SyntaxError:
                compiled = compile(code, "<python_repl>", "exec")
                exec(compiled, env, env)
                result = None

        state.clear()
        state.update(
            {
                k: v
                for k, v in env.items()
                if k not in {"__builtins__", "math"} and k not in bindings and k not in tools_env
            }
        )

        stdout = buf.getvalue().strip()
        if result is not None:
            # Keep large structures compact (esp. Prometheus API responses).
            if isinstance(result, dict) and isinstance(result.get("data"), dict):
                data = result.get("data")
                if isinstance(data, dict) and isinstance(data.get("result"), list):
                    rendered = f"Prometheus response: resultType={data.get('resultType')} (data.result is a list)"
                else:
                    rendered = "Prometheus response (ok)"
            else:
                rendered = str(result)
                if len(rendered) > 800:
                    rendered = "(ok)"

            if stdout:
                return f"{rendered}\n{stdout}" if rendered != "(ok)" else stdout
            return rendered
        return stdout or "(ok)"

    return python_repl


def main() -> None:
    lm = get_lm_for_model_name(MODEL_NAME_GEMINI_2_5_FLASH, "disable")
    dspy_configure(lm)

    tracker = ToolUsageTracker()
    callback = ToolCallCallback(tracker)

    try:
        with dspy.context(lm=lm, callbacks=[callback]):
            # Force the model to use python_repl (and call tools from within Python)
            # so it can assign intermediate results to variables and iterate.
            tools = [dspy.Tool(build_python_repl_tool(tracker))]

            agent = dspy.ReAct(signature="question -> answer", tools=tools, max_iters=12)  # type: ignore[arg-type]

            q = (
                "List kube service info metrics for namespace argocd: return the service names (the `service` label) and the count. "
                "Use python_repl as a scratchpad: assign tool results to variables, peek to learn structure, then compute the count "
                "from the returned data (show the python you ran). "
                "You will likely need to call python_repl multiple times."
            )
            # q = "List 10 metric names containing 'argocd' and then run count(up)."
            print(f"\nQuestion:\n -> {q}\n")
            pred = agent(question=q)
            
            tracker.print_summary()
            
            print(f"\nAnswer:\n -> {pred.answer}\n")

    finally:
        callback.close()


if __name__ == "__main__":
    main()
