import json
import os
import urllib.request
from datetime import datetime
from typing import Any, Dict

import dspy

from constants import MODEL_NAME_GEMINI_2_5_FLASH
from repl.python_tool_repl import build_python_repl_tool
from simplest_tool_logging import ToolCallCallback, ToolUsageTracker
from utils import dspy_configure, get_lm_for_model_name


def http_get(
    url: str,
    timeout_s: float = 15.0,
    max_bytes: int = 250_000,
    *,
    allow_truncate: bool = True,
    add_truncation_marker: bool = True,
) -> str:
    """Fetch a URL and return text (optionally truncated)."""
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": "prometheus-tool-ai/0.1 (dspy ReAct demo)",
            "Accept": "application/json,text/plain,*/*",
        },
    )
    with urllib.request.urlopen(req, timeout=timeout_s) as resp:
        data = resp.read(max_bytes + 1)

    truncated = len(data) > max_bytes
    if truncated and not allow_truncate:
        raise ValueError(f"Response exceeded max_bytes={max_bytes}; increase max_bytes for {url}")

    text = data[:max_bytes].decode("utf-8", errors="replace")
    if truncated and add_truncation_marker:
        text += "\n\n[TRUNCATED]"
    return text


def pypi_json(package: str, timeout_s: float = 15.0, max_bytes: int = 2_000_000) -> Dict[str, Any]:
    """Fetch PyPI JSON metadata for a package."""
    url = f"https://pypi.org/pypi/{package}/json"
    try:
        body = http_get(url, timeout_s=timeout_s, max_bytes=max_bytes, allow_truncate=False, add_truncation_marker=False)
    except Exception as e:
        return {"error": f"{type(e).__name__}: {e}", "url": url}
    try:
        return json.loads(body)
    except json.JSONDecodeError as e:
        return {"error": f"JSONDecodeError: {e}", "url": url, "raw_prefix": body[:2000]}


def main() -> None:
    lm = get_lm_for_model_name(MODEL_NAME_GEMINI_2_5_FLASH, "disable")
    dspy_configure(lm)

    tracker = ToolUsageTracker()
    callback = ToolCallCallback(tracker)

    try:
        with dspy.context(lm=lm, callbacks=[callback]):
            base_tools = [
                dspy.Tool(http_get),
                dspy.Tool(pypi_json),
            ]

            tools = [
                build_python_repl_tool(tracker, base_tools, track_sub_tools=False)
            ]

            agent = dspy.ReAct(
                signature="question -> answer",  # type: ignore[arg-type]
                tools=tools,
                max_iters=12,
            )

            q = """
You are doing multi-step web metadata mining via the persistent python_repl scratchpad.

REPL constraints:
- Imports are disabled in python_repl (so do not use `import ...`).
- `Counter` is available as a builtin named `Counter` (no import needed).

Goal:
Build a small report for these packages: ["httpx", "pydantic", "rich"].

Hard requirement (do not skip):
- Use python_repl across MULTIPLE calls.
- Store intermediate results in variables (e.g. pkgs, raw_by_pkg, classifiers_by_pkg).
- Peek at the data structure first (print keys / small samples) before doing computations.
- Reuse variables from earlier python_repl calls in later python_repl calls.
- Show the python snippets you ran (prints are fine).

What to compute (from PyPI JSON):
1) For each package: latest version (info.version) and total number of release versions (len(releases)).
2) For each package: total number of distribution files across all releases (sum(len(releases[v]))).
3) Across ALL packages: top 8 most common trove classifier PREFIXES, where prefix is the first segment before " :: "
   (use Counter; show the Counter output).
4) Across ALL packages: which "Programming Language :: Python :: 3.x" classifiers appear, and which packages declare each.

Output:
- A short markdown table per package for (1)-(2)
- Then bullet points for (3)-(4)
"""
            print(f"\nQuestion:\n -> {q}\n")
            pred = agent(question=q)
            run_id = datetime.now().strftime("%Y%m%d_%H%M%S")
            os.makedirs("logs", exist_ok=True)
            with open(f"logs/pypi_agent_{run_id}.md", "w") as f:
                f.write(tracker.get_summary())

            tracker.print_summary(cutoff_input_output_length=100)
            print(f"\nAnswer:\n -> {pred.answer}\n")
    finally:
        callback.close()


if __name__ == "__main__":
    main()
