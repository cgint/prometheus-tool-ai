import dspy
import logging
from utils import get_lm_for_model_name, dspy_configure
from constants import MODEL_NAME_GEMINI_2_5_FLASH
from tool_tracker import ToolUsageTracker, ToolCallCallback

logger = logging.getLogger(__name__)

# Define the tools (without any tracking code - clean functions)
def add_numbers(a: float, b: float) -> float:
    """Add two numbers together.
    
    Args:
        a: First number
        b: Second number
        
    Returns:
        The sum of a and b
    """
    return a + b


def multiply_numbers(a: float, b: float) -> float:
    """Multiply two numbers together.
    
    Args:
        a: First number
        b: Second number
        
    Returns:
        The product of a and b
    """
    return a * b


def main():
    """Main function demonstrating DSPy ReAct agent with native tool logging."""
    # Configure DSPy (already sets track_usage=True)
    lm = get_lm_for_model_name(MODEL_NAME_GEMINI_2_5_FLASH, "disable")
    dspy_configure(lm)
    
    # Initialize tool tracker
    tool_tracker = ToolUsageTracker()
    
    # Create DSPy-native callback handler
    tool_callback = ToolCallCallback(tool_tracker)
    
    try:
        # Use dspy.context() for scoped callback registration (best practice)
        # This ensures callbacks are only active during agent execution
        with dspy.context(lm=lm, callbacks=[tool_callback]):
            # Create tool instances (clean - no wrapping needed)
            # DSPy's callback system will intercept calls automatically
            add_tool = dspy.Tool(add_numbers)
            multiply_tool = dspy.Tool(multiply_numbers)
            
            # Create ReAct agent with tools
            # Use string signature as DSPy ReAct supports it
            react_agent = dspy.ReAct(
                signature="question -> answer",  # type: ignore[arg-type]
                tools=[add_tool, multiply_tool],
                max_iters=10
            )
            
            # Example queries
            questions = [
                "What is 3 + 5?",
                "What is 4 * 7?",
                "Calculate 10 + 15 and then multiply the result by 2"
            ]
            
            print("\n" + "="*60)
            print("🤖 ReAct Agent with Tool Logging")
            print("="*60 + "\n")
            
            prediction = None
            for question in questions:
                print(f"❓ Question: {question}")
                prediction = react_agent(question=question)
                print(f"💡 Answer: {prediction.answer}\n")
        
        # Display tool usage summary
        tool_tracker.print_summary()
        
        # Also show LM usage if available
        if prediction:
            try:
                # Try to get usage from the last prediction
                if hasattr(prediction, 'get_lm_usage'):
                    usage = prediction.get_lm_usage()
                    if usage:
                        print("📈 LM Usage Statistics:")
                        print(f"   {usage}\n")
            except Exception:
                pass  # Usage stats might not be available in all cases
    
    finally:
        # Explicit cleanup of callback resources
        tool_callback.close()


if __name__ == "__main__":
    main()

