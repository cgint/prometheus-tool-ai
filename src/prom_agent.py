import dspy

from agent_logging import AgentLogConfig, write_agent_logs
from constants import MODEL_NAME_GEMINI_2_5_FLASH
from repl.python_tool_repl import build_hacky_python_repl_tool
from tool_tracker import ToolCallCallback, ToolUsageTracker
from tools.prom import prom_buildinfo, prom_labels, prom_label_values, prom_metrics, prom_query, prom_range
from utils import dspy_configure, get_lm_for_model_name


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
            tools = [build_hacky_python_repl_tool(tracker, base_tools)]

            agent = dspy.ReAct(signature="question -> answer", tools=tools, max_iters=12)  # type: ignore[arg-type]

            q = (
                "List kube service info metrics for namespace argocd: return the service names (the `service` label) and the total count. "
                "Use python_repl as a scratchpad: assign tool results to variables, peek to learn structure, then compute the count "
                "from the returned data (show the python you ran). "
                "Register computed values (e.g. service_count, service_list) and use placeholders in your final answer."
            )
            print(f"\nQuestion:\n -> {q}\n")
            pred = agent(question=q)

            write_agent_logs(
                agent_name="prom_agent",
                tracker=tracker,
                prediction=pred,
                config=AgentLogConfig(
                    write_summary=True,
                    print_registered_vars=True,
                    print_raw_answer=True,
                ),
            )

    finally:
        callback.close()


if __name__ == "__main__":
    main()
