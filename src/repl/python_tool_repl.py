from typing import Any, Dict, List

import dspy

from tool_tracker import ToolUsageTracker
from utils import indent


def build_python_repl_tool(tracker: ToolUsageTracker, sub_tools: List[dspy.Tool], track_sub_tools: bool = False) -> dspy.Tool:
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
        line = f" ===== Function: '{t.name}' =====\n"
        line += f"   Arguments: {t.args}\n"
        line += f"{indent(t.desc or '', '   ')}\n"
        return line

    tool_catalog = "\n".join(_format_tool_line(t) for t in sub_tools)

    repl_instructions_and_tool_info = f"""Persistent Python scratchpad.

Use this REPL to iteratively explore data and compute results.

Key behaviors:
- State persists across calls: assign to variables and reuse them later.
- Single expression returns a value; multi-line code runs via exec, so print what you want to see.
- Prefer a few multi-line steps per call (fetch + compact peeks), then follow up with additional calls.
- Imports are allowed but restricted to a safe allowlist; if an import fails, use pre-injected helpers instead.
- You may register values for the final answer via `register_for_final_output(...)`. In your FINAL natural-language answer,
  you can use placeholders like `{{total_count}}` and they will be substituted after the agent finishes.

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
        import traceback

        allowed_imports = {
            # Common "safe-ish" standard library helpers (no subprocess)
            "collections",
            "copy",
            "csv",
            "datetime",
            "decimal",
            "difflib",
            "functools",
            "itertools",
            "json",
            "math",
            "pprint",
            "re",
            "statistics",
            "string",
            "textwrap",
        }
        _real_import = __import__

        def _safe_import(name: str, globals_: Any = None, locals_: Any = None, fromlist: tuple = (), level: int = 0) -> Any:
            base = name.split(".", 1)[0]
            if base not in allowed_imports:
                raise ImportError(f"Import '{name}' not allowed. Allowed: {sorted(allowed_imports)}")
            return _real_import(name, globals_, locals_, fromlist, level)

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
            "__import__": _safe_import,
        }

        tools_by_name: Dict[str, dspy.Tool] = {}
        for t in sub_tools:
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

        tools_env: Dict[str, Any] = {name: _wrap_tool(t) if track_sub_tools else t.func for name, t in tools_by_name.items()}

        def register_for_final_output(*args, **kwargs) -> str:
            """Register named values for late-binding into the final answer.

            Supported call styles:
              - register_for_final_output({"total_count": 8})
              - register_for_final_output(total_count=8)
              - register_for_final_output([("total_count", 8), ("blob", big_str)])
              - register_for_final_output([{"total_count": 8}, {"blob": big_str}])
            """
            values: Dict[str, Any] = {}

            if len(args) == 1 and isinstance(args[0], dict):
                values.update(args[0])
            elif len(args) == 1 and isinstance(args[0], (list, tuple)):
                for item in args[0]:
                    if isinstance(item, dict):
                        values.update(item)
                    elif isinstance(item, (list, tuple)) and len(item) == 2:
                        k, v = item
                        values[str(k)] = v
                    elif isinstance(item, set) and len(item) == 2:
                        # Allow the common mistake: {"name", value} (a set, not a dict).
                        # We only accept it if there's exactly one string element.
                        key_candidates = [x for x in item if isinstance(x, str)]
                        if len(key_candidates) != 1:
                            raise TypeError("Set form must contain exactly one string key")
                        k = key_candidates[0]
                        v = next(x for x in item if x is not k)
                        values[k] = v
                    else:
                        raise TypeError(f"Unsupported item in list: {type(item).__name__}")
            elif len(args) != 0:
                raise TypeError("register_for_final_output expects a dict, a list, or kwargs")

            values.update(kwargs)
            tracker.register_final_output_vars(values)
            return f"registered: {sorted(values.keys())}"

        bindings: Dict[str, Any] = {}
        per_tool_counts: Dict[str, int] = {}
        for log in tracker.get_tool_logs():
            tool_name = str(log.get("tool_name", "tool"))
            if tool_name in {"python_repl"}:
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
            "register_for_final_output": register_for_final_output,
        }
        env.update(tools_env)
        env.update(state)
        env.update(bindings)

        if len(code.splitlines()) > 30:
            return "ERROR: Too many lines for one python_repl call; split work across multiple calls."

        buf = io.StringIO()
        had_error = False
        with contextlib.redirect_stdout(buf), contextlib.redirect_stderr(buf):
            try:
                try:
                    compiled = compile(code, "<python_repl>", "eval")
                    result = eval(compiled, env, env)
                except SyntaxError:
                    compiled = compile(code, "<python_repl>", "exec")
                    exec(compiled, env, env)
                    result = None
            except Exception:
                had_error = True
                traceback.print_exc()
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
        if had_error:
            return stdout or "ERROR: python_repl failed (no traceback captured)"
        if result is not None:
            rendered = _render(result)
            if stdout:
                return f"{rendered}\n{stdout}" if rendered != "(ok)" else stdout
            return rendered
        return stdout or "(ok)"

    print(f"\nEmitting Python REPL TOOL with structure:\n{repl_instructions_and_tool_info}\n")
    return dspy.Tool(python_repl, desc=repl_instructions_and_tool_info)
