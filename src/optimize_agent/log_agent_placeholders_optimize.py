from __future__ import annotations

from typing import Any, List, Literal, Optional

import dspy

from constants import MODEL_NAME_GEMINI_2_5_FLASH
from optimize_agent.log_agent_placeholders_examples import (
    prepare_test_data,
    prepare_training_data,
)
from log_agent import AgentSignature, fetch_log_data
from repl.python_tool_repl import build_python_repl_tool
from tool_tracker import ToolCallCallback, ToolUsageTracker
from utils import dspy_configure, get_lm_for_model_name


class LogAgentModule(dspy.Module):
    def __init__(self, lm: dspy.LM):
        super().__init__()
        self.lm = lm

    def forward(self, question: str) -> dspy.Prediction:
        tracker = ToolUsageTracker()
        callback = ToolCallCallback(tracker)
        try:
            with dspy.context(lm=self.lm, callbacks=[callback]):
                tools = [
                    build_python_repl_tool(
                        tracker,
                        sub_tools=[dspy.Tool(fetch_log_data)],
                        track_sub_tools=False,
                    )
                ]
                agent = dspy.ReAct(
                    signature=AgentSignature,
                    tools=tools,
                    max_iters=10,
                )
                pred = agent(question=question)
        finally:
            callback.close()

        registered_vars = tracker.get_final_output_vars()
        pred.registered_vars = registered_vars
        pred.registered_var_names = sorted(registered_vars.keys())
        return pred


def placeholder_metric(example: dspy.Example, pred: dspy.Prediction, trace: Any = None) -> float:
    expected_vars: List[str] = getattr(example, "expected_vars", [])
    if not expected_vars:
        return 1.0

    registered = set(getattr(pred, "registered_var_names", []))
    expected = set(expected_vars)

    registered_score = len(expected & registered) / len(expected)
    placeholder_score = sum(1 for var in expected_vars if f"{{{var}}}" in pred.answer) / len(expected_vars)

    return (registered_score + placeholder_score) / 2.0


def to_percent_int(score: float) -> int:
    return int(round(score * 100))


def optimize_log_agent(
    optimizer_type: Literal["MIPROv2", "GEPA"],
    auto: Literal["light", "medium", "heavy"],
    limit_trainset: int,
    limit_testset: int,
    randomize_sets: bool = False,
    reflection_minibatch_size: int = 8,
) -> None:
    lm = get_lm_for_model_name(MODEL_NAME_GEMINI_2_5_FLASH, "disable")
    dspy_configure(lm)

    trainset = prepare_training_data(limit=limit_trainset)
    testset = prepare_test_data(limit=limit_testset)

    if randomize_sets:
        import random

        random.shuffle(trainset)
        random.shuffle(testset)

    baseline_module = LogAgentModule(lm=lm)
    baseline_score = dspy.Evaluate(
        devset=testset,
        metric=placeholder_metric,
        num_threads=1,
        display_progress=True,
    )(baseline_module)

    if optimizer_type == "MIPROv2":
        optimizer = dspy.MIPROv2(
            metric=placeholder_metric,
            auto=auto,
            num_threads=1,
            max_bootstrapped_demos=4,
            max_labeled_demos=4,
            prompt_model=lm,
        )
    elif optimizer_type == "GEPA":
        from dspy.teleprompt.gepa.gepa import GEPAFeedbackMetric
        from dspy.teleprompt.gepa.gepa_utils import ScoreWithFeedback

        class PlaceholderFeedbackMetric(GEPAFeedbackMetric):  # type: ignore[call-arg]
            def __call__(
                self,
                gold: dspy.Example,
                pred: dspy.Prediction,
                trace: Any = None,
                pred_name: Optional[str] = None,
                pred_trace: Any = None,
            ) -> float | ScoreWithFeedback:
                score = placeholder_metric(gold, pred, trace)
                if pred_name is None:
                    return score
                if score < 1.0:
                    feedback = (
                        "Use placeholders for all computed values and ensure the variables are registered. "
                        "Do not paste computed data directly."
                    )
                else:
                    feedback = "Good: placeholders used and variables registered."
                return ScoreWithFeedback(score=score, feedback=feedback)

        optimizer = dspy.GEPA(
            metric=PlaceholderFeedbackMetric(),
            auto=auto,
            num_threads=1,
            track_stats=True,
            skip_perfect_score=True,
            add_format_failure_as_feedback=True,
            reflection_minibatch_size=reflection_minibatch_size,
            reflection_lm=lm,
        )
    else:
        raise ValueError(f"Unsupported optimizer_type: {optimizer_type}")

    optimized_module = optimizer.compile(
        LogAgentModule(lm=lm),
        trainset=trainset,
        valset=testset,
    )

    optimized_score = dspy.Evaluate(
        devset=testset,
        metric=placeholder_metric,
        num_threads=1,
        display_progress=True,
    )(optimized_module)

    print("\nResults:")
    print(f"Baseline score:  {to_percent_int(baseline_score.score)}%")
    print(f"Optimized score: {to_percent_int(optimized_score.score)}%")


def main() -> None:
    optimize_log_agent(
        optimizer_type="MIPROv2",
        auto="light",
        limit_trainset=20,
        limit_testset=8,
        randomize_sets=False,
        reflection_minibatch_size=8,
    )


if __name__ == "__main__":
    main()
