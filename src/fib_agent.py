import json
import os
from datetime import datetime

import dspy

from constants import MODEL_NAME_GEMINI_2_5_FLASH
from dspy_utils import capture_dspy_inspect_history
from repl.python_tool_repl import build_python_repl_tool
from tool_tracker import ToolCallCallback, ToolUsageTracker
from utils import dspy_configure, get_lm_for_model_name


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
                signature="question -> answer",  # type: ignore[arg-type]
                tools=tools,
                max_iters=8,
            )

            q = """
Compute Fibonacci numbers using the persistent python_repl.

Goal:
Generate all Fibonacci numbers up to (and including) any value <= 10000.

Requirements:
- Use python_repl to compute the sequence.
- Register the results as **named data parts** using `register_for_final_output(...)`.
  This keeps large/deterministic outputs out of the model's context window.

Data parts to register (use these exact names):
- `fib_count`: how many Fibonacci numbers were generated (an integer)
- `fib_string`: the full sequence as a comma-separated string (e.g. "0,1,1,2,3,5,8,...")
- `largest_fib`: the largest Fibonacci number in the sequence (an integer)

In your final answer:
- Write a short, natural-language summary in your own words.
- Embed placeholders like `{fib_count}`, `{fib_string}`, `{largest_fib}` wherever you want
  the data to appear.
- Do NOT paste the actual sequence or numbers directly; use the placeholders instead.

Example of a good final answer (you can structure it differently):
  "I computed **{fib_count}** Fibonacci numbers. The largest is **{largest_fib}**.
   Here is the full sequence: {fib_string}"

Example of a BAD final answer (do NOT do this):
  "I computed 21 Fibonacci numbers: 0,1,1,2,3,5,8,13,21,34,55,89,144,..."
  (This pastes the data directly instead of using placeholders.)
"""
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

            print(f"\n{'='*60}")
            print("REGISTERED VARS:")
            for k, v in final_vars.items():
                preview = str(v)[:80] + "..." if len(str(v)) > 80 else str(v)
                print(f"  {k}: {preview}")
            print(f"{'='*60}")
            print(f"RAW pred.answer (check for placeholders vs pasted data):\n{pred.answer}")
            print(f"{'='*60}")
            print(f"RENDERED final_answer:\n{final_answer}")
            print(f"{'='*60}\n")
    finally:
        callback.close()


if __name__ == "__main__":
    main()
