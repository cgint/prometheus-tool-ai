import io
import sys
import dspy

def capture_dspy_inspect_history() -> str:
    """
    Captures the output of dspy.inspect_history() and returns it as a string.
    Since dspy.inspect_history() prints to stdout instead of returning a value,
    we need to temporarily redirect stdout to capture the output.
    """
    buf = io.StringIO()
    original_stdout = sys.stdout
    sys.stdout = buf
    try:
        dspy.inspect_history()
    finally:
        sys.stdout = original_stdout
    
    history_text = buf.getvalue()
    buf.close()
    return history_text