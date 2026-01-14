import os
import dspy
from datetime import datetime
from constants import MODEL_NAME_GEMINI_2_5_FLASH
from tool_tracker import ToolCallCallback, ToolUsageTracker
from utils import dspy_configure, get_lm_for_model_name
from tools.prom import prom_buildinfo, prom_metrics, prom_labels, prom_label_values, prom_query, prom_range
from repl.python_tool_repl import build_python_repl_tool

def main() -> None:
    lm = get_lm_for_model_name(MODEL_NAME_GEMINI_2_5_FLASH, "disable")
    dspy_configure(lm)

    tracker = ToolUsageTracker()
    callback = ToolCallCallback(tracker)

    try:
        with dspy.context(lm=lm, callbacks=[callback]):
            base_tools = [
                dspy.Tool(prom_buildinfo),
                dspy.Tool(prom_metrics),
                dspy.Tool(prom_labels),
                dspy.Tool(prom_label_values),
                dspy.Tool(prom_query),
                dspy.Tool(prom_range),
            ]
            tools = [build_python_repl_tool(tracker, base_tools)]

            agent = dspy.ReAct(signature="question -> answer", tools=tools, max_iters=12)  # type: ignore[arg-type]

            q = (
                "List kube service info metrics for namespace argocd: return the service names (the `service` label) and the total count. "
                "Use python_repl as a scratchpad: assign tool results to variables, peek to learn structure, then compute the count "
                "from the returned data (show the python you ran). "
                "Register computed values (e.g. service_count, service_list) and use placeholders in your final answer."
            )
            print(f"\nQuestion:\n -> {q}\n")
            pred = agent(question=q)

            run_id = datetime.now().strftime("%Y%m%d_%H%M%S")
            os.makedirs("logs", exist_ok=True)
            with open(f"logs/prom_agent_{run_id}.md", "w") as f:
                f.write(tracker.get_summary())

            tracker.print_summary(cutoff_input_output_length=100)

            # Render placeholders - AI decides placement
            final_vars = tracker.get_final_output_vars()
            final_answer = tracker.render_with_final_output_vars(pred.answer, final_vars)

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
