import dspy
import logging
from typing import Any, Dict, List
from dspy.utils.callback import BaseCallback

logger = logging.getLogger(__name__)


# Tool usage tracker for capturing tool calls
class ToolUsageTracker:
    """Tracks tool calls with inputs and outputs."""
    
    def __init__(self, debug: bool = False):
        self.tool_logs: List[Dict[str, Any]] = []
        self.debug = debug
    
    def log_tool_call(self, tool_name: str, tool_args: Dict[str, Any], tool_output: Any) -> None:
        """Log a tool call with its inputs and output."""
        log_entry = {
            "tool_name": tool_name,
            "inputs": tool_args,
            "output": tool_output,
            "status": "completed"
        }
        self.tool_logs.append(log_entry)
        if self.debug:
            print(f"🔧 Tool '{tool_name}' called with inputs: {tool_args} -> output: {tool_output}")
        else:
            print(f"🔧 Tool '{tool_name}' called.")
    
    def get_tool_logs(self) -> List[Dict[str, Any]]:
        """Get all tracked tool logs."""
        return self.tool_logs

    def _coalesce_if_cutoff(self, value: str, cutoff_length: int | None = None) -> str:
        if cutoff_length is None or len(value) <= cutoff_length:
            return value
        return value[:cutoff_length] + "..."

    
    def get_summary(self, cutoff_input_output_length: int | None = None) -> str:
        """Get a summary of all tool calls as a string."""
        if not self.tool_logs:
            return "No tool calls were tracked."
        
        summary = ""
        for i, log in enumerate(self.tool_logs, 1):
            summary += f"\n{i}. Tool: {log['tool_name']}\n"
            summary += f"   Inputs: {self._coalesce_if_cutoff(str(log['inputs']), cutoff_input_output_length)}\n"
            summary += f"   Output: {self._coalesce_if_cutoff(str(log['output']), cutoff_input_output_length)}\n"
            summary += f"   Status: {log['status']}\n"
        return summary
    
    def print_summary(self, cutoff_input_output_length: int | None = None) -> None:
        """Print a summary of all tool calls."""
        print(self.get_summary(cutoff_input_output_length))



# DSPy-native callback handler for tool tracking
class ToolCallCallback(BaseCallback):
    """
    DSPy-native callback that intercepts and logs tool calls.
    
    This callback is registered with DSPy's callback system to track tool executions
    without modifying tool source code. Works with any tool, even if we don't have
    access to the tool's source code.
    
    Features:
    - Tracks tool start and end events
    - Handles ReAct's argument wrapping (unwraps 'kwargs' dict)
    - Captures both successful executions and exceptions
    - Provides resource cleanup to prevent memory leaks
    
    Note: This callback is not thread-safe. Create a new instance for each request
    or ensure proper synchronization if used in multi-threaded environments.
    
    Usage:
        tracker = ToolUsageTracker()
        callback = ToolCallCallback(tracker)
        with dspy.context(callbacks=[callback]):
            result = agent(query="...")
        tracker.print_summary()
    """
    
    def __init__(self, tracker: ToolUsageTracker):
        """
        Initialize the tool call callback.
        
        Args:
            tracker: The ToolUsageTracker instance to log calls to
        """
        super().__init__()
        self.tracker = tracker
        # Store pending tool calls to match start/end
        self._pending_calls: Dict[str, Dict[str, Any]] = {}
        self._closed = False
    
    def on_tool_start(self, call_id: str, instance: dspy.Tool, inputs: Dict[str, Any]) -> None:
        """
        Called when a tool execution starts.
        
        Args:
            call_id: Unique identifier for this tool call
            instance: The dspy.Tool instance being called
            inputs: Dictionary of tool input arguments (may be wrapped in 'kwargs' by ReAct)
        """
        if self._closed:
            return
        
        try:
            # Extract tool name
            tool_name = instance.name if hasattr(instance, 'name') and instance.name else (
                instance.func.__name__ if hasattr(instance, 'func') else "unknown_tool"
            )
            
            # Unwrap kwargs if present (ReAct wraps arguments in 'kwargs' dict)
            # Create a copy to avoid mutating original inputs
            actual_inputs = inputs
            if isinstance(inputs, dict) and 'kwargs' in inputs:
                kw = inputs.get('kwargs')
                if isinstance(kw, dict):
                    actual_inputs = kw.copy()  # Copy to avoid mutation
                else:
                    actual_inputs = inputs.copy() if isinstance(inputs, dict) else inputs
            elif isinstance(inputs, dict):
                actual_inputs = inputs.copy()  # Copy to avoid mutation
            
            # Store pending call info
            self._pending_calls[call_id] = {
                "tool_name": tool_name,
                "inputs": actual_inputs
            }
        except Exception as e:
            # Log but don't re-raise - callback failures shouldn't break tool execution
            logger.warning("Error in on_tool_start callback for call_id %s: %s", call_id, e, exc_info=True)
    
    def on_tool_end(self, call_id: str, outputs: Any, exception: Exception | None = None) -> None:
        """
        Called when a tool execution ends.
        
        Args:
            call_id: Unique identifier for this tool call
            outputs: The tool's output/result
            exception: Exception if tool failed, None if successful
        """
        if self._closed:
            return
        
        try:
            if call_id not in self._pending_calls:
                # Should not happen, but handle gracefully (idempotency)
                logger.warning("on_tool_end called for unknown call_id: %s", call_id)
                return
            
            call_info = self._pending_calls.pop(call_id)
            tool_name = call_info["tool_name"]
            inputs = call_info["inputs"]
            
            # Create a copy of outputs to avoid mutating original data
            outputs_copy = self._copy_outputs(outputs)
            
            # Log the tool call
            if exception is None:
                self.tracker.log_tool_call(tool_name, inputs, outputs_copy)
            else:
                # Log error case
                error_msg = f"ERROR: {exception}"
                self.tracker.log_tool_call(tool_name, inputs, error_msg)
        except Exception as e:
            # Log but don't re-raise - callback failures shouldn't break tool execution
            logger.warning("Error in on_tool_end callback for call_id %s: %s", call_id, e, exc_info=True)
    
    def _copy_outputs(self, outputs: Any) -> Any:
        """
        Create a copy of outputs to avoid mutating original data.
        
        Args:
            outputs: The outputs to copy
            
        Returns:
            A copy of the outputs
        """
        if isinstance(outputs, dict):
            return outputs.copy()
        elif isinstance(outputs, list):
            return outputs[:]
        else:
            return outputs
    
    def close(self) -> None:
        """
        Explicit cleanup method to release resources.
        
        Cleans up pending calls dictionary and marks callback as closed.
        Should be called when callback is no longer needed.
        """
        if not self._closed:
            # Clean up any orphaned pending calls
            if self._pending_calls:
                logger.warning(
                    "Closing callback with %d pending calls (tool calls may not have completed)",
                    len(self._pending_calls)
                )
            self._pending_calls.clear()
            self._closed = True
    
    def __del__(self) -> None:
        """Fallback cleanup when object is garbage collected."""
        self.close()

