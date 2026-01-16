import dspy


class RecursiveLMSignature(dspy.Signature):
    """
    You are a recursive language model helper.
    You are given a question and optional context data.
    Answer the question based on the context provided.
    """

    question = dspy.InputField(
        desc="The specific question or task to perform on the context."
    )
    context = dspy.InputField(desc="The data or text chunk to process.", optional=True)
    answer = dspy.OutputField(desc="The result of the processing.")


def ask_llm(question: str, context: str = "") -> str:
    """
    Ask a question to an LLM, optionally providing context data.
    This is useful for summarizing chunks of text, extracting specific information,
    or performing semantic reasoning on data that cannot be done with regex.
    """
    # Use ChainOfThought for better reasoning capabilities on the chunk
    predictor = dspy.ChainOfThought(RecursiveLMSignature)

    result = predictor(question=question, context=context)
    return result.answer
