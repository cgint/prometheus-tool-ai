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


def get_available_files() -> list[str]:
    """Return the available sample log file paths (repo-relative)."""
    repo_root = Path(__file__).resolve().parents[1]
    sample_dir = (repo_root / "src" / "optimize_agent" / "sample_logs").resolve()
    if repo_root not in sample_dir.parents and sample_dir != repo_root:
        raise ValueError("Sample log directory must be within repo root.")
    if not sample_dir.is_dir():
        raise FileNotFoundError(str(sample_dir))

    files = sorted(p.name for p in sample_dir.glob("*.log") if p.is_file())
    return [f"src/optimize_agent/sample_logs/{name}" for name in files]


class AgentSignature(dspy.Signature):
    """
    You are an AI agent with a persistent Python REPL.

    ## POLICY Python REPL:
    - Use python_repl to compute results instead of processing or calculating yourself.
    - Register computed data as named parts using `register_for_final_output(item_count=str(len(items)))`.
    - Only register data that you plan to use in the final answer.

    ## POLICY Final Answer:
    - Final-output variable values MUST be STRINGS (display-ready snippets). Convert scalars with `str(...)`.
      For structured data (lists/dicts), format it into the exact text you want to appear in the final answer, then register that string.
    - In your final answer, use placeholders like `Number of items: {item_count}`.
    - NEVER paste computed data directly in your final answer; ONLY use placeholders.

    ## EXAMPLE of an execution process with Python REPL tool call and final answer:
    ### In python_repl: compute and register
    n_str = str(len(items))
    items_bullets = "\n".join("- " + str(item) for item in items)
    register_for_final_output(item_count=n_str, items_list=items_bullets)

    ### In your final answer: use the placeholders
    "I found **{item_count}** items:\n\n{items_list}"
    """

    question = dspy.InputField()
    answer = dspy.OutputField()

class LogAgentModule(dspy.Module):
    def __init__(self):
        super().__init__()
        self.tracker = ToolUsageTracker()
        self.callback = ToolCallCallback(self.tracker)
        self.tools = [
            build_python_repl_tool(
                self.tracker,
                sub_tools=[dspy.Tool(fetch_log_data), dspy.Tool(get_available_files)],
                track_sub_tools=False,
            )
        ]
        self.agent = dspy.ReAct(
            signature=AgentSignature,
            tools=self.tools,
            max_iters=10,
        )

    def get_tracker(self) -> ToolUsageTracker:
        return self.tracker

    def forward(self, question: str) -> dspy.Prediction:
        try:
            with dspy.context(callbacks=[self.callback]):
                pred = self.agent(question=question)
        finally:
            self.callback.close()

        registered_vars = self.tracker.get_final_output_vars()
        pred.registered_vars = registered_vars
        pred.registered_var_names = sorted(registered_vars.keys())
        return pred

def main() -> None:
    lm = get_lm_for_model_name(MODEL_NAME_GEMINI_2_5_FLASH, "disable")
    dspy_configure(lm)
    try:
        q = (
            "Read these local log files: "
            '["src/optimize_agent/sample_logs/file1.log", "src/optimize_agent/sample_logs/file2.log", "src/optimize_agent/sample_logs/file3.log"].\n'
            'For each file, compute how many lines contain the substring "ERROR". '
            "Also compute the total across all files.\n"
            "Return a short explanation plus the per-file counts and the total."
        )
        print(f"\nQuestion:\n -> {q}\n")
        agent = LogAgentModule()
        pred = agent(question=q)

        write_agent_logs(
            agent_name="log_agent",
            tracker=agent.tracker,
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
        agent.callback.close()


if __name__ == "__main__":
    main()
