import dspy
from typing import Callable, Any
import functools

from agent_logging import AgentLogConfig, write_agent_logs
from constants import MODEL_NAME_GEMINI_3_FLASH_PREVIEW
from tool_tracker import ToolUsageTracker
from tools.log_tools import fetch_log_data, get_available_files
from utils import dspy_configure, get_lm_for_model_name
from dspy.primitives.python_interpreter import PythonInterpreter

# --- 1. Define the Signature ---
class LogAnalysis(dspy.Signature):
    """
    You are a Log Analysis Agent.
    
    Goal: Analyze log files using Python code.
    
    Instructions:
    1. Use `get_available_files()` to find logs.
    2. Use `fetch_log_data(path)` to read them.
    3. Use Python to process the data (count errors, filter lines, etc.).
    4. SUBMIT your findings using the output fields.
    
    ## POLICY: Data Submission
    - Do NOT manually re-type large data or counts into the `SUBMIT` call.
    - ALWAYS use variables from your Python history.
    - Example: `SUBMIT(summary_text=f"Found {total} errors", ...)`
    - BAD Example: `SUBMIT(summary_text="Found 6 errors", ...)` (Do not hardcode values!)
    
    Important: 
    - Use `llm_query(prompt)` if you need semantic understanding (e.g. "is this error critical?").
    - Do not print huge amounts of text.
    """
    question = dspy.InputField()
    
    # SUBMIT args:
    summary_text = dspy.OutputField(desc="A human-readable summary of the findings, including the total counts.")
    file_counts = dspy.OutputField(desc="A dictionary mapping filenames to their error counts (e.g. {'file1.log': 10}).")

# --- 2. Tool Tracking Wrapper ---
def track_tool(tracker: ToolUsageTracker, func: Callable) -> Callable:
    """Wraps a tool function to log its calls to the tracker."""
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        # We manually log to the tracker.
        # Since RLM doesn't use dspy.Tool in the ReAct sense, we piggyback.
        
        # We need to construct a dict for args to match log_tool_call signature expected by some viewers,
        # but log_tool_call takes (name, args_dict, output).
        
        inputs = {"args": args, "kwargs": kwargs}
        
        try:
            result = func(*args, **kwargs)
            tracker.log_tool_call(func.__name__, inputs, result)
            return result
        except Exception as e:
            tracker.log_tool_call(func.__name__, inputs, f"Error: {e}")
            raise e
            
    return wrapper

# --- 3. Custom Interpreter ---
class ForceRegisterInterpreter(PythonInterpreter):
    """
    Subclass that forces tool re-registration on every execution.
    This works around potential state desync issues in the Deno sandbox.
    """
    def execute(self, code: str, variables: dict[str, Any] | None = None) -> Any:
        self._tools_registered = False
        return super().execute(code, variables)

class LogAgentRLMModule(dspy.Module):
    def __init__(self):
        super().__init__()
        self.tracker = ToolUsageTracker()
        
        # Wrap tools for tracking
        self.tools_dict = {
            "fetch_log_data": track_tool(self.tracker, fetch_log_data),
            "get_available_files": track_tool(self.tracker, get_available_files)
        }
        
        # Initialize Interpreter
        self.interpreter = ForceRegisterInterpreter(tools=self.tools_dict)
        
        # Initialize RLM
        self.agent = dspy.RLM(
            signature=LogAnalysis,
            tools=self.tools_dict,
            max_iterations=10,
            verbose=True,
            interpreter=self.interpreter
        )

    def forward(self, question: str) -> dspy.Prediction:
        # RLM handles its own execution loop.
        pred = self.agent(question=question)
        
        # Shim 'answer' for the logger
        if hasattr(pred, "summary_text"):
            pred.answer = pred.summary_text
        else:
            pred.answer = "No summary returned."

        # Let's populate 'registered_vars' for our logger to see the structured data
        pred.registered_vars = {
            "file_counts": getattr(pred, "file_counts", {}),
            "summary_text": getattr(pred, "summary_text", "")
        }
        pred.registered_var_names = ["file_counts", "summary_text"]
        
        return pred

def main():
    # Setup
    lm = get_lm_for_model_name(MODEL_NAME_GEMINI_3_FLASH_PREVIEW, "disable")
    dspy_configure(lm)
    
    agent = LogAgentRLMModule()
    
    q = (
        "Read the local log files in 'src/optimize_agent/sample_logs'. "
        'For each file, compute how many lines contain the substring "ERROR". ' 
        "Also compute the total across all files. "
        "Return a short explanation plus the per-file counts and the total."
    )
    
    print(f"\nQuestion:\n -> {q}\n")
    
    try:
        pred = agent(question=q)
        
        # Log results
        write_agent_logs(
            agent_name="log_agent_rlm",
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
        print(f"\nFinal Summary: {pred.summary_text}")
        print(f"File Counts: {pred.file_counts}")
        
    except Exception as e:
        print(f"Error during execution: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main()
