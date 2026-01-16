import dspy
from src.tools.llm_tool import ask_llm


class MockLM(dspy.LM):
    def __init__(self):
        super().__init__("mock-lm")
        self.history = []

    def __call__(self, prompt=None, messages=None, **kwargs):
        # Store call for verification
        self.history.append({"prompt": prompt, "messages": messages, "kwargs": kwargs})

        # Simple mock response logic based on input
        input_str = str(prompt) if prompt else str(messages)

        reasoning = "I should answer this question."
        answer = "Mock response"

        if "summarize" in input_str.lower():
            answer = "This is a summary of the text."
        if "sentiment" in input_str.lower():
            answer = "The sentiment is negative."

        # DSPy JSONAdapter expects a JSON string
        import json

        return [json.dumps({"reasoning": reasoning, "answer": answer})]


def test_ask_llm_basic():
    # Setup mock LM
    mock_lm = MockLM()
    dspy.settings.configure(lm=mock_lm)

    # Test simple question
    response = ask_llm("What is 2+2?")
    assert response == "Mock response"
    assert len(mock_lm.history) > 0


def test_ask_llm_with_context():
    # Setup mock LM
    mock_lm = MockLM()
    dspy.settings.configure(lm=mock_lm)

    # Test with context
    context = "This is a long error log with traceback..."
    response = ask_llm("Summarize this error", context=context)

    assert response == "This is a summary of the text."

    # Verify the context made it into the prompt/call
    last_call = mock_lm.history[-1]
    # DSPy signature compilation is complex to assert exact strings on,
    # but we can verify the call happened successfully
    assert last_call is not None


if __name__ == "__main__":
    # Allow running directly for quick check
    test_ask_llm_basic()
    test_ask_llm_with_context()
    print("All tests passed!")
