# Analysis: Porting `src/log_agent.py` to `dspy.RLM`

This document analyzes the feasibility and implications of refactoring the current `LogAgentModule` (which uses `dspy.ReAct` + custom Python REPL) to use the native `dspy.RLM` module.

## 1. Overview of Components

### Current State (`src/log_agent.py`)
*   **Core Module**: `dspy.ReAct`.
*   **Mechanism**: A thought-action-observation loop where "action" is calling a tool.
*   **REPL**: Implemented as a *tool* (`build_hacky_python_repl_tool`). The agent "calls" the REPL with code, and the tool executes it and returns stdout/variables.
*   **State Management**: Handled manually by the `python_tool_repl` closure/object.
*   **Final Answer**: The agent calls `register_for_final_output` (a special function in the REPL) to stash variables, then returns a final text answer that references them.

### Target State (`dspy.RLM`)
*   **Core Module**: `dspy.RLM` (Recursive Language Model).
*   **Mechanism**: A specialized loop where the LLM *writes Python code directly* to interact with the environment.
*   **REPL**: Built-in (`CodeInterpreter` / `PythonInterpreter`). The "action" *is* writing code.
*   **Recursive Capability**: Native support for `llm_query(prompt)` inside the Python code to perform semantic sub-tasks (e.g., "summarize this log chunk").
*   **Final Answer**: The LLM calls `SUBMIT(var1, var2)` in Python to terminate and return structured data.

## 2. Key Differences & Migration Steps

### A. The "Agent Loop"
*   **Current**: `ReAct` decides "Should I use a tool?".
*   **RLM**: `RLM` decides "What code should I write next?".
*   **Migration**: Replace `dspy.ReAct` instantiation with `dspy.RLM`.
    ```python
    # Old
    self.agent = dspy.ReAct(signature=AgentSignature, tools=self.tools, ...)

    # New
    self.agent = dspy.RLM(
        signature="question -> answer", # Simplified signature
        tools=my_tools_dict, # Passed as dict, not list of Tools
        max_iterations=10
    )
    ```

### B. Handling Tools
*   **Current**: Tools (`fetch_log_data`, `get_available_files`) are wrapped in `dspy.Tool` and passed to the REPL tool generator.
*   **RLM**: Tools are passed as a dictionary of callables directly to `RLM`.
    ```python
    # New
    tools = {
        "fetch_log_data": fetch_log_data,
        "get_available_files": get_available_files
    }
    ```
    *Note*: RLM automatically injects `llm_query` and `llm_query_batched`, enabling the "Recursive" part of RLM (e.g., "Count lines with 'error' using Python, but 'classify severity' using `llm_query`").

### C. Signature & Final Output
*   **Current**: `AgentSignature` includes complex instructions about `register_for_final_output` and formatting placeholders.
*   **RLM**: `RLM` uses a standard task signature (e.g., `question -> answer`). It handles the logic of "how to submit" via its internal `ACTION_INSTRUCTIONS_TEMPLATE`, which tells the model to use `SUBMIT(answer=...)`.
*   **Implication**: We can drastically simplify the signature. We remove the "POLICY" instructions from the user code and rely on `RLM`'s built-in system prompt.

### D. Tool Usage Tracking
*   **Current**: `ToolUsageTracker` hooks into the `python_tool_repl` and `dspy.Tool`.
*   **RLM**: `RLM` executes code in a sandbox. It does not natively emit "tool call" events in the same way `ReAct` does.
*   **Migration**: To keep tracking, we must wrap the functions passed to `tools` with a tracking decorator before giving them to `RLM`.
    ```python
    def track_and_call(func):
        def wrapper(*args, **kwargs):
            tracker.log(func.__name__, args, kwargs)
            return func(*args, **kwargs)
        return wrapper
    ```

## 3. Benefits of Migration

1.  **Native Code Execution**: `RLM` is purpose-built for "writing code to solve problems." It avoids the layer of indirection where the agent "calls a tool that runs code."
2.  **Recursive Semantic Operations**: `RLM` exposes `llm_query`. The agent can write:
    ```python
    logs = fetch_log_data("file.log")
    errors = [line for line in logs.splitlines() if "ERROR" in line]
    # Semantic filtering!
    critical_errors = [e for e in errors if llm_query(f"Is this critical? {e}") == "Yes"]
    ```
    The current implementation cannot do this easily inside the REPL loop.
3.  **Structured Output**: `SUBMIT()` forces the model to return the exact fields defined in the signature, reducing parsing errors.
4.  **Cleaner State**: `RLM` manages `REPLHistory` and variables formally, whereas the "hacky" REPL tool manually maintains a `locals()` dict.

## 4. Risks & Considerations

1.  **Experimental Status**: `dspy.RLM` is marked `@experimental`. API might change.
2.  **Concurrency/Threading**: The `RLM` docstring warns about thread safety with custom interpreters. `LogAgentModule` currently uses `dspy.context` for thread isolation, which should still work if `RLM` initializes its interpreter per `forward` call (which it does by default).
3.  **Prompt Tuning**: `RLM` uses a hardcoded `ACTION_INSTRUCTIONS_TEMPLATE`. If this prompt isn't effective for our specific log analysis tasks, we might need to subclass `RLM` to modify it.

## 5. Proposed Plan

1.  **Prototype**: Create `src/log_agent_rlm.py` as a parallel implementation.
2.  **Refactor Tools**: Extract `fetch_log_data` and others into a pure utility module (if not already) so they can be shared.
3.  **Implement Wrapper**: Create a helper to wrap tools with `ToolUsageTracker` for RLM compatibility.


## 6. The "Placeholder" Pattern vs. RLM Native Execution

The user's current "Placeholder Pattern" (register variable -> return text with `{var}`) solves a critical problem: **Preventing the LLM from manually token-generating large/complex data.**

### How RLM Solves This (Natively)
`dspy.RLM` solves this exact problem but moves the "replacement" logic from *post-processing* to *execution time* (inside the Python REPL).

1.  **Current (ReAct)**:
    *   LLM: "I will return `Found {n} items`."
    *   System: Replaces `{n}` with `str(n_variable)` *after* the LLM finishes.
2.  **Target (RLM)**:
    *   LLM writes Code: `SUBMIT(answer=f"Found {len(items)} items")`
    *   Python REPL: Evaluates the f-string.
    *   Result: `"Found 42 items"`

### Code Example: RLM "Placeholder" via f-strings
In your current agent, you have to "teach" the LLM to use specific syntax like `register_for_final_output` and `{var}`. In RLM, you just ask for the result, and the LLM uses standard Python.

```python
# The signature defines what we want back
class LogAnalysis(dspy.Signature):
    """Analyze logs and return a summary + structured data."""
    question = dspy.InputField()
    
    # These fields map to arguments in SUBMIT()
    summary_text = dspy.OutputField(desc="Human readable summary")
    error_counts = dspy.OutputField(desc="Dictionary of counts per file")

# ... inside the RLM agent execution ...

# The LLM writes this Python code:
logs = fetch_log_data("error.log")
count = logs.count("ERROR")
my_counts = {"error.log": count}

# IT SIMPLY USES PYTHON F-STRINGS FOR "PLACEHOLDERS"
# No special "policy" needed - it's just Python!
SUBMIT(
    summary_text=f"I found {count} errors in the log file.", 
    error_counts=my_counts
)
```

**Key Insight**: In RLM, the LLM *never* types the data. It writes *code* that references the data. The Python interpreter handles the string construction. This achieves the same safety and accuracy goal as the placeholder pattern but is more standard (idiomatic Python).

### Advanced: Keeping Structured Data
If the goal is to pass *structured data* (e.g., a raw list of dicts for a UI table) rather than a string representation:
*   **Signature**: `question -> answer_text, raw_data`
*   **LLM Action**: `SUBMIT(answer_text="Here is the data", raw_data=my_list)`
*   **Result**: `Prediction(answer_text="...", raw_data=[{...}, {...}])`

## 7. Architecture Diagram

![RLM vs ReAct Flow](./rlm_vs_react.svg)

## 8. External Research & Context
Web search confirms `dspy.RLM` implements the "Recursive Language Models" strategy (Zhang, Kraska, Khattab, 2025). 
*   **Core Concept**: Treats the LLM's context as an external environment (REPL) to handle effectively "unbounded" data without stuffing the prompt.
*   **Alignment**: This perfectly matches our use case of analyzing large/multiple log files. Instead of loading logs into the context, the agent explores them via code and only "reads" (queries) relevant chunks recursively.
*   **Status**: The paper and implementation are recent (Dec 2025 / Jan 2026), positioning this as a cutting-edge approach for "Context-Centric" agents.

