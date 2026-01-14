import dspy

from agent_logging import AgentLogConfig, write_agent_logs
from constants import MODEL_NAME_GEMINI_2_5_FLASH
from repl.python_tool_repl import build_python_repl_tool
from tool_tracker import ToolCallCallback, ToolUsageTracker
from utils import dspy_configure, get_lm_for_model_name


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
            # No external tools needed - pure REPL computation
            tools = [
                build_python_repl_tool(tracker, sub_tools=[], track_sub_tools=False)
            ]

            agent = dspy.ReAct(
                signature=AgentSignature,
                tools=tools,
                max_iters=8,
            )

            q = "Generate all Fibonacci numbers up to (and including) 10000. Provide the full sequence, the count of numbers, and the largest number."
            print(f"\nQuestion:\n -> {q}\n")
            pred = agent(question=q)

            write_agent_logs(
                agent_name="fib_agent",
                tracker=tracker,
                prediction=pred,
                config=AgentLogConfig(
                    write_summary=True,
                    write_usage=True,
                    write_history=True,
                    write_final_answer=True,
                ),
            )
    finally:
        callback.close()


if __name__ == "__main__":
    main()
