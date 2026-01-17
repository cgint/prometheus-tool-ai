from pathlib import Path

import dspy

from agent_logging import AgentLogConfig, write_agent_logs
from constants import MODEL_NAME_GEMINI_3_FLASH_PREVIEW
from repl.python_tool_repl import build_hacky_python_repl_tool
from tool_tracker import ToolCallCallback, ToolUsageTracker
from tools.llm_tool import ask_llm
from utils import dspy_configure, get_lm_for_model_name


def list_files(path: str) -> list[str]:
    """List python files in a directory."""
    repo_root = Path(__file__).resolve().parents[1]
    target = (repo_root / path).resolve()

    # Security check: ensure path is within repo root
    if repo_root not in target.parents and target != repo_root:
        raise ValueError(f"Path must be within repo root: {path}")

    if not target.is_dir():
        raise FileNotFoundError(str(target))

    return [str(p.relative_to(repo_root)) for p in target.glob("**/*.py")]


def read_file(path: str) -> str:
    """Read file content."""
    repo_root = Path(__file__).resolve().parents[1]
    target = (repo_root / path).resolve()

    # Security check
    if repo_root not in target.parents and target != repo_root:
        raise ValueError(f"Path must be within repo root: {path}")

    if not target.is_file():
        raise FileNotFoundError(str(target))

    return target.read_text(encoding="utf-8")


class CodeAuditAgentSignature(dspy.Signature):
    """
    You are a Tech Debt Collector agent.

    Your goal is to identify the "ugliest" or "most complex" Python code in a given directory.

    ## POLICY:
    1. Use `python_repl` to scan files and compute metrics (e.g. line counts).
    2. Filter candidates programmatically (e.g. files > 20 lines).
    3. For candidate files, use the `ask_llm` tool (available inside python_repl) to semantically audit them.
       - Example: `score = ask_llm("Rate code hackiness 0-10", context=file_content)`
    4. Aggregate results in Python and formulate a "Debt Repayment Plan".

    ## CRITICAL REPL RULES:
    - **NEVER hardcode data** from previous steps. Variables persist between calls.
    - If you define `files = ...` in step 1, use `for f in files:` in step 2.
    - Do NOT manually type out lists of files or content.

    ## POLICY Final Answer:
    - Final-output variable values MUST be STRINGS (display-ready snippets). Convert scalars with `str(...)`.
      For structured data (lists/dicts), format it into the exact text you want to appear in the final answer, then register that string.
    - In your final answer, use placeholders like `Number of items: {item_count}`.
    - NEVER paste computed data directly in your final answer; ONLY use placeholders.
    """

    question = dspy.InputField()
    answer = dspy.OutputField()


class CodeAuditAgentModule(dspy.Module):
    def __init__(self):
        super().__init__()
        self.tracker = ToolUsageTracker()
        self.callback = ToolCallCallback(self.tracker)

        # We inject the ask_llm tool into the REPL so the python code can call it
        self.tools = [
            build_hacky_python_repl_tool(
                self.tracker,
                sub_tools=[
                    dspy.Tool(list_files),
                    dspy.Tool(read_file),
                    dspy.Tool(ask_llm),
                ],
                track_sub_tools=False,
            )
        ]
        self.agent = dspy.ReAct(
            signature=CodeAuditAgentSignature,
            tools=self.tools,
            max_iters=15,
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
    lm = get_lm_for_model_name(MODEL_NAME_GEMINI_3_FLASH_PREVIEW, "disable")
    dspy_configure(lm)

    agent = None
    try:
        q = (
            "Scan the 'src/tools' directory. "
            "Identify the files that seem most complex or 'hacky'. "
            "1. List all files and their line counts. "
            "2. For any file over 20 lines, ask the LLM to rate its 'hackiness' (0-10) and explain why. "
            "3. Present a table of the top offenders."
        )
        print(f"\nQuestion:\n -> {q}\n")

        agent = CodeAuditAgentModule()
        pred = agent(question=q)

        write_agent_logs(
            agent_name="code_audit_agent",
            tracker=agent.tracker,
            prediction=pred,
            config=AgentLogConfig(
                write_summary=True,
                write_usage=True,
                write_history=True,
                write_final_answer=True,
                write_tool_calls=True,
                print_registered_vars=True,
                print_raw_answer=True,
            ),
        )
    finally:
        if agent:
            agent.callback.close()


if __name__ == "__main__":
    main()
