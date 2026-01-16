import argparse
import json
from pathlib import Path
from typing import Any

import dspy

from agent_logging import AgentLogConfig, write_agent_logs
from constants import MODEL_NAME_GEMINI_3_FLASH_PREVIEW
from repl.python_tool_repl import build_hacky_python_repl_tool
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


def load_optimized_program_state(path: str | Path) -> dict[str, Any]:
    """Load a DSPy module state from a combined optimized program JSON file."""
    repo_root = Path(__file__).resolve().parents[1]
    target = Path(path)
    if not target.is_absolute():
        target = (repo_root / target).resolve()
    else:
        target = target.resolve()

    if repo_root not in target.parents and target != repo_root:
        raise ValueError(f"Path must be within repo root: {path}")
    if not target.is_file():
        raise FileNotFoundError(str(target))

    data = json.loads(target.read_text(encoding="utf-8"))
    if "program" not in data:
        raise ValueError(f"Missing 'program' in optimized file: {path}")
    return data["program"]


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
#
# TODO: Thoughts on better way to handle the REPL and registering the final output (GEPA+concurrency safe)
#
# dspy.context(...) is the right “run context” mechanism in DSPy — the “only once / same thread” restriction you’re thinking of applies to dspy.configure(...), not to dspy.context(...).        
#                                                                                                                                                                                                 
#  Conclusion: even inside GEPA you are in control of per-run context, because GEPA ultimately evaluates by calling program(**example.inputs()) inside Evaluate worker threads. Your module’s     
#  forward() runs there, so you can create a fresh per-example tracker/REPL-state and install it with dspy.context(...) inside forward(). GEPA doesn’t need to wrap anything.                     
#                                                                                                                                                                                                 
#  The missing piece is: context only helps if the tool reads state from the context. If python_repl still closes over a long-lived tracker/state (closure), GEPA+deepcopy+threads can still      
#  leak.                                                                                                                                                                                          
#                                                                                                                                                                                                 
#  Two “work with the system” patterns:                                                                                                                                                           
#  1. Per-call objects created in forward() + passed via dspy.context                                                                                                                             
#      - tracker = ToolUsageTracker(), callback = ToolCallCallback(tracker), repl_state = {}                                                                                                      
#      - with dspy.context(callbacks=[callback], run_state=...) run the agent                                                                                                                     
#      - python_repl looks up dspy.settings.run_state at call time (no captured tracker/state)                                                                                                    
#  2. Use callbacks as the “run context container” (most DSPy-native)                                                                                                                             
#      - Put tracker + repl_state on a callback instance                                                                                                                                          
#      - Push it via dspy.context(callbacks=[that_callback])                                                                                                                                      
#      - python_repl finds the active callback via dspy.settings.callbacks and uses its state                                                                                                     
#                                                                                                                                                                                                 
#  Either way, you don’t need any special GEPA hook: the isolation boundary is per forward() call, and GEPA can’t bypass that.                                                                    
#                                                                                                                                                                                                 
#  2. sounds good - Just two things because we ran into issues previously - The self.agent must be present for GEPA. I am not sure if it has to be initialized in the constructor already.        
#  Because if we initialize the tracker in the forward, then we have kind of a hen and egg. Please look at class LogAgentModule(dspy.Module):Again, and tell me what you think.                   
# 
#  Yes: for GEPA you really want self.agent (and therefore the underlying predictors) to exist before GEPA.compile(...) runs. GEPA reads student.named_predictors() and then repeatedly does      
#  student.deepcopy() + edits predictor instructions. If you rebuild self.agent inside forward(), you risk throwing away GEPA’s mutated predictor instructions (you’d be recreating fresh         
#  predictors with default prompts).                                                                                                                                                              
#                                                                                                                                                                                                 
#  The “hen and egg” only exists because your current build_python_repl_tool(self.tracker, ...) bakes the tracker (and REPL state={}) into a closure at construction time. If you switch to       
#  pattern (2), you don’t need tracker at init:                                                                                                                                                   
#                                                                                                                                                                                                 
#  - Keep self.agent = dspy.ReAct(...) created in __init__ with a context-aware python_repl tool that does not capture tracker/state.                                                             
#  - In forward(), create a fresh tracker + callback (+ repl_state) per call and run:                                                                                                             
#      - with dspy.context(callbacks=[run_callback]): pred = self.agent(...)                                                                                                                      
#  - Inside python_repl, resolve “current run state” by looking at dspy.settings.callbacks and picking your callback instance (e.g., a dedicated RunStateCallback that holds tracker and          
#  repl_state).                                                                                                                                                                                   
#                                                                                                                                                                                                 
#  This is actually more aligned with DSPy’s execution model, because Evaluate(num_threads>1) calls the same program instance concurrently across threads — so storing self.tracker/self.callback 
#  on the module is inherently unsafe, whereas a per-call callback in dspy.context(...) is thread-isolated and GEPA-compatible.  
class LogAgentModule(dspy.Module):
    def __init__(self):
        super().__init__()
        self.tracker = ToolUsageTracker()
        self.callback = ToolCallCallback(self.tracker)
        self.tools = [
            build_hacky_python_repl_tool(
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

def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--optimized-program",
        type=str,
        help="Repo-relative path to a combined optimized program JSON.",
    )
    args = parser.parse_args(argv)

    lm = get_lm_for_model_name(MODEL_NAME_GEMINI_3_FLASH_PREVIEW, "disable")
    dspy_configure(lm)
    agent: dspy.Module | None = None
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
        if args.optimized_program:
            agent.load_state(load_optimized_program_state(args.optimized_program))
            print(f"Loaded optimized program from: {args.optimized_program}")
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
