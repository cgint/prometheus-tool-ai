import json
import urllib.request
from typing import Any, Dict

import dspy

from agent_logging import AgentLogConfig, write_agent_logs
from constants import MODEL_NAME_GEMINI_2_5_FLASH
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
    - Register ALL computed data as named parts using `register_for_final_output(...)`.
    - Final-output variables MUST be STRINGS (display-ready snippets). Convert scalars with `str(...)`.
      For structured data (dict/list/tuples), format it into the exact text you want to appear in the final answer,
      then register that string (e.g. `q1_text`, `q2_text`, `q3_text`, `q4_text`).
    - In your final answer, use placeholders like `{q1_text}`, `{count}`, `{some_snippet}`.
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
            
            write_agent_logs(
                agent_name="pypi_agent",
                tracker=tracker,
                prediction=pred,
                config=AgentLogConfig(
                    write_summary=True,
                    write_usage=True,
                    write_history=True,
                    write_final_answer=True,
                    print_registered_vars=True,
                    print_raw_answer=True,
                ),
            )
    finally:
        callback.close()


if __name__ == "__main__":
    main()
