import json
import os
from datetime import datetime

import dspy

from constants import MODEL_NAME_GEMINI_2_5_FLASH
from dspy_utils import capture_dspy_inspect_history
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

            run_id = datetime.now().strftime("%Y%m%d_%H%M%S")
            os.makedirs("logs", exist_ok=True)
            with open(f"logs/fib_agent_{run_id}.md", "w") as f:
                f.write(tracker.get_summary())

            usage = pred.get_lm_usage()
            if usage:
                usage_output = json.dumps(usage, indent=2)
                with open(f"logs/fib_agent_{run_id}_usage.json", "w") as f:
                    f.write(usage_output)

            history = capture_dspy_inspect_history()
            with open(f"logs/fib_agent_{run_id}_history.md", "w") as f:
                f.write(history)

            tracker.print_summary(cutoff_input_output_length=100)

            # Render placeholders - no fallback, AI decides placement
            final_vars = tracker.get_final_output_vars()
            final_answer = tracker.render_with_final_output_vars(pred.answer, final_vars)
            with open(f"logs/fib_agent_{run_id}_final_answer.md", "w") as f:
                f.write(final_answer)

            print(f"\n{'='*60}")
            print(f"RENDERED final_answer:\n{final_answer}")
            print(f"{'='*60}\n")
    finally:
        callback.close()


if __name__ == "__main__":
    main()
