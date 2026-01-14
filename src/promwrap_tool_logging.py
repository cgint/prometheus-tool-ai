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


def build_python_repl_tool(tracker: ToolUsageTracker, tools: List[dspy.Tool]) -> dspy.Tool:
    """Build a persistent python_repl tool.

    This REPL provides:
    - A persistent Python state across tool calls (assign variables and reuse them).
    - Read-only bindings to prior *tool outputs*:
      - `<tool_name>_<n>` for each tool call (0-based, per tool)
      - `_` for the most recent non-python tool output
    - A set of Python-callable functions injected at runtime (the caller decides which tools are available).

    The goal is to enable iterative "peek → compute" workflows without hardcoding tool knowledge.
    """

    def _format_tool_line(t: dspy.Tool) -> str:
        name = t.name
        args = t.args
        desc = t.desc
        return f"- {name} - {args} -  {desc}"

    tool_catalog = "\n".join(_format_tool_line(t) for t in tools)

    repl_instructions_and_tool_info = f"""Persistent Python scratchpad.

Use this REPL to iteratively explore data and compute results.

Key behaviors:
- State persists across calls: assign to variables and reuse them later.
- Single expression returns a value; multi-line code runs via exec, so print what you want to see.
- Prefer a few multi-line steps per call (fetch + compact peeks), then follow up with additional calls.

Available functions (callable from Python):
{tool_catalog}
"""

    state: Dict[str, Any] = {}

    def python_repl(code: str) -> str:
        import collections
        import contextlib
        import io
        import math
        import sys

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
            "type": type,
            "isinstance": isinstance,
            "repr": repr,
            "dir": dir,
            "hasattr": hasattr,
            "Counter": collections.Counter,
        }

        tools_by_name: Dict[str, dspy.Tool] = {}
        for t in tools:
            name = t.name or getattr(t.func, "__name__", type(t.func).__name__)
            tools_by_name[name] = t

        def tool_names() -> List[str]:
            return sorted(tools_by_name.keys())

        def _wrap_tool(tool: dspy.Tool):
            tool_name = tool.name or getattr(tool.func, "__name__", "tool")
            func = tool.func

            def _wrapped(*args, **kwargs):
                inputs = {"args": list(args), "kwargs": dict(kwargs)}
                out = func(*args, **kwargs)
                # Ensure tracker prints are not captured as python_repl output.
                with contextlib.redirect_stdout(sys.__stdout__):
                    tracker.log_tool_call(tool_name, inputs, out)
                return out

            _wrapped.__name__ = tool_name
            return _wrapped

        tools_env: Dict[str, Any] = {name: _wrap_tool(t) for name, t in tools_by_name.items()}

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

        env: Dict[str, Any] = {
            "__builtins__": safe_builtins,
            "math": math,
            "tool_names": tool_names,
        }
        env.update(tools_env)
        env.update(state)
        env.update(bindings)

        if len(code.splitlines()) > 30:
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
                if k not in {"__builtins__", "math", "tool_names"} and k not in bindings and k not in tools_env
            }
        )

        def _render(obj: Any) -> str:
            try:
                if isinstance(obj, dict):
                    ks = list(obj.keys())
                    return f"dict(keys={ks[:10]})"
                if isinstance(obj, (list, tuple)):
                    return f"{type(obj).__name__}(len={len(obj)})"
                s = str(obj)
                return s if len(s) <= 800 else "(ok)"
            except Exception:
                return "(ok)"

        stdout = buf.getvalue().strip()
        if result is not None:
            rendered = _render(result)
            if stdout:
                return f"{rendered}\n{stdout}" if rendered != "(ok)" else stdout
            return rendered
        return stdout or "(ok)"

    print(f"\nEmitting Python REPL TOOL with structure:\n{repl_instructions_and_tool_info}\n")
    return dspy.Tool(python_repl, desc=repl_instructions_and_tool_info)


def main() -> None:
    lm = get_lm_for_model_name(MODEL_NAME_GEMINI_2_5_FLASH, "disable")
    dspy_configure(lm)

    tracker = ToolUsageTracker()
    callback = ToolCallCallback(tracker)

    try:
        with dspy.context(lm=lm, callbacks=[callback]):
            base_tools = [
                dspy.Tool(prom_buildinfo),
                dspy.Tool(prom_metrics),
                dspy.Tool(prom_labels),
                dspy.Tool(prom_label_values),
                dspy.Tool(prom_query),
                dspy.Tool(prom_range),
            ]
            tools = [build_python_repl_tool(tracker, base_tools)]

            agent = dspy.ReAct(signature="question -> answer", tools=tools, max_iters=12)  # type: ignore[arg-type]

            q = (
                "List kube service info metrics for namespace argocd: return the service names (the `service` label) and the total count. "
                "Use python_repl as a scratchpad: assign tool results to variables, peek to learn structure, then compute the count "
                "from the returned data (show the python you ran)."
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
