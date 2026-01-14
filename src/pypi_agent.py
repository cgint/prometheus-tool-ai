import json
import os
import urllib.request
from datetime import datetime
from typing import Any, Dict

import dspy

from constants import MODEL_NAME_GEMINI_2_5_FLASH
from dspy_utils import capture_dspy_inspect_history
from repl.python_tool_repl import build_python_repl_tool
from tool_tracker import ToolCallCallback, ToolUsageTracker
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


class AgentSignature(dspy.Signature):
    """
    You are an AI agent with a persistent Python REPL.

    POLICY:
    - Use python_repl to compute results.
    - Register ALL computed data (scalars, strings, tables) as named parts using `register_for_final_output(...)`.
    - In your final answer, use placeholders like `{count}`, `{table}`.
    - NEVER paste computed data directly; ONLY use placeholders.
    """
    question = dspy.InputField()
    answer = dspy.OutputField()


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
                signature=AgentSignature,
                tools=tools,
                max_iters=12,
            )

            q = """
Analyze PyPI metadata for these packages: ["httpx", "pydantic", "rich"].

Please compute and report:
1) Latest version and total release count for each.
2) Total distribution files across all releases for each.
3) Top 8 most common trove classifier prefixes (first segment before " :: ").
4) Which "Programming Language :: Python :: 3.x" classifiers appear, and which packages declare each.
"""
            print(f"\nQuestion:\n -> {q}\n")
            pred = agent(question=q)
            
            run_id = datetime.now().strftime("%Y%m%d_%H%M%S")
            os.makedirs("logs", exist_ok=True)
            with open(f"logs/pypi_agent_{run_id}.md", "w") as f:
                f.write(tracker.get_summary())
            # Try to get usage from the last prediction
            usage = pred.get_lm_usage()
            if usage:
                usage_output = json.dumps(usage, indent=2) if usage else "No token usage metadata available"
                with open(f"logs/pypi_agent_{run_id}_usage.json", "w") as f:
                    f.write(usage_output)
            history = capture_dspy_inspect_history()
            with open(f"logs/pypi_agent_{run_id}_history.md", "w") as f:
                f.write(history)
                
            tracker.print_summary(cutoff_input_output_length=100)

            # Render placeholders - AI decides placement
            final_vars = tracker.get_final_output_vars()
            final_answer = tracker.render_with_final_output_vars(pred.answer, final_vars)
            with open(f"logs/pypi_agent_{run_id}_final_answer.md", "w") as f:
                f.write(final_answer)

            print(f"\n{'='*60}")
            print("REGISTERED VARS:")
            for k, v in final_vars.items():
                preview = str(v)[:80] + "..." if len(str(v)) > 80 else str(v)
                print(f"  {k}: {preview}")
            print(f"{'='*60}")
            print(f"RAW pred.answer:\n{pred.answer}")
            print(f"{'='*60}")
            print(f"RENDERED final_answer:\n{final_answer}")
            print(f"{'='*60}\n")
    finally:
        callback.close()


if __name__ == "__main__":
    main()
