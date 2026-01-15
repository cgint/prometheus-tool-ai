from __future__ import annotations

from pathlib import Path

import dspy

from agent_logging import AgentLogConfig, write_agent_logs
from constants import MODEL_NAME_GEMINI_2_5_FLASH
from repl.python_tool_repl import build_python_repl_tool
from tool_tracker import ToolCallCallback, ToolUsageTracker
from utils import dspy_configure, get_lm_for_model_name


def fetch_log_data(path: str, *, max_bytes: int = 200_000) -> str:
    """Fetch a local log file as text (bounded).

    This is intentionally scoped to files within the repository root to avoid arbitrary host reads.
    """
    repo_root = Path(__file__).resolve().parents[1]
    target = (repo_root / path).resolve()
    if repo_root not in target.parents and target != repo_root:
        raise ValueError(f"Path must be within repo root: {path}")
    if not target.is_file():
        raise FileNotFoundError(str(target))
    data = target.read_bytes()
    if len(data) > max_bytes:
        data = data[:max_bytes]
    return data.decode("utf-8", errors="replace")


class AgentSignature(dspy.Signature):
    """
    You are an AI agent with a persistent Python REPL.

    POLICY:
    - Use python_repl to compute results.
    - Register ALL computed data as named parts using `register_for_final_output(...)`.
    - Final-output variables MUST be STRINGS (display-ready snippets). Convert scalars with `str(...)`.
      For structured data (lists/dicts), format it into the exact text you want to appear in the final answer,
      then register that string (e.g. `per_file_counts_text`, `total_error_lines_str`, `matching_lines_excerpt`).
    - In your final answer, use placeholders like `{per_file_counts_text}`, `{total_error_lines_str}`.
    - NEVER paste computed data directly in your final answer; ONLY use placeholders.
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
                dspy.Tool(fetch_log_data),
            ]

            tools = [build_python_repl_tool(tracker, base_tools, track_sub_tools=False)]

            agent = dspy.ReAct(
                signature=AgentSignature,
                tools=tools,
                max_iters=10,
            )

            q = (
                "Read these local log files: "
                '["logs/sample_logs/file1.log", "logs/sample_logs/file2.log", "logs/sample_logs/file3.log"].\n'
                'For each file, compute how many lines contain the substring "ERROR". '
                "Also compute the total across all files.\n"
                "Return a short explanation plus the per-file counts and the total."
            )
            print(f"\nQuestion:\n -> {q}\n")
            pred = agent(question=q)

            write_agent_logs(
                agent_name="log_agent",
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

