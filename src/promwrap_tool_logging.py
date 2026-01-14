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


_PY_REPL_STATE: Dict[str, Any] = {}

# Set by main() so python_repl can access prior tool outputs.
_TOOL_USAGE_TRACKER: ToolUsageTracker | None = None


def _tool_call_bindings() -> Dict[str, Any]:
    """Expose prior tool outputs to python_repl.

    Provides:
    - `<tool_name>_<n>`: output of the n-th call of that tool (0-based, per tool)
    - `_`: output of the most recent tool call (any tool)
    """

    if _TOOL_USAGE_TRACKER is None:
        return {}

    bindings: Dict[str, Any] = {}
    per_tool_counts: Dict[str, int] = {}

    for log in _TOOL_USAGE_TRACKER.get_tool_logs():
        tool_name = str(log.get("tool_name", "tool"))
        idx = per_tool_counts.get(tool_name, 0)
        per_tool_counts[tool_name] = idx + 1

        out = log.get("output")
        bindings[f"{tool_name}_{idx}"] = out
        bindings["_"] = out

    return bindings


def python_repl(code: str) -> str:
    """Evaluate simple Python for calculations.

    State is preserved across calls (variables stored in a shared dict).

    Additionally, outputs from previous tool calls are available:
    - `prom_query_0`, `prom_query_1`, ...
    - `_` for the most recent tool output
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
    }

    env: Dict[str, Any] = {"__builtins__": safe_builtins, "math": math}
    env.update(_PY_REPL_STATE)

    tool_bindings = _tool_call_bindings()
    env.update(tool_bindings)

    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        try:
            compiled = compile(code, "<python_repl>", "eval")
            result = eval(compiled, env, env)
        except SyntaxError:
            compiled = compile(code, "<python_repl>", "exec")
            exec(compiled, env, env)
            result = None

    _PY_REPL_STATE.clear()
    _PY_REPL_STATE.update({
        k: v
        for k, v in env.items()
        if k not in {"__builtins__", "math"} and k not in tool_bindings
    })

    stdout = buf.getvalue().strip()
    if result is not None and stdout:
        return f"{result}\n{stdout}"
    if result is not None:
        return str(result)
    return stdout or "(ok)"


def main() -> None:
    lm = get_lm_for_model_name(MODEL_NAME_GEMINI_2_5_FLASH, "disable")
    dspy_configure(lm)

    tracker = ToolUsageTracker()
    callback = ToolCallCallback(tracker)

    global _TOOL_USAGE_TRACKER
    _TOOL_USAGE_TRACKER = tracker

    try:
        with dspy.context(lm=lm, callbacks=[callback]):
            tools = [
                dspy.Tool(prom_buildinfo),
                dspy.Tool(prom_metrics),
                dspy.Tool(prom_labels),
                dspy.Tool(prom_label_values),
                dspy.Tool(prom_query),
                dspy.Tool(prom_range),
                dspy.Tool(python_repl),
            ]

            agent = dspy.ReAct(signature="question -> answer", tools=tools, max_iters=12)  # type: ignore[arg-type]

            q = "List kube service info metrics for namespace argocd. Also calculate the count of entries as python code"
            # q = "List 10 metric names containing 'argocd' and then run count(up)."
            print(f"\nQuestion:\n -> {q}\n")
            pred = agent(question=q)
            
            tracker.print_summary()
            
            print(f"\nAnswer:\n -> {pred.answer}\n")

    finally:
        callback.close()


if __name__ == "__main__":
    main()
