from __future__ import annotations

from typing import Any, List, Literal, Optional

import logging

import dspy

from constants import MODEL_NAME_GEMINI_2_5_FLASH
from optimize_agent.log_agent_placeholders_examples import (
    prepare_test_data,
    prepare_training_data,
)
from log_agent import AgentSignature, fetch_log_data, get_available_files
from repl.python_tool_repl import build_python_repl_tool
from tool_tracker import ToolCallCallback, ToolUsageTracker
from utils import dspy_configure, get_lm_for_model_name

logger = logging.getLogger(__name__)


class LogAgentModule(dspy.Module):
    def __init__(self, lm: dspy.LM):
        super().__init__()
        self.lm = lm
        self.tracker = ToolUsageTracker()
        self.callback = ToolCallCallback(self.tracker)
        self.tools = [
            build_python_repl_tool(
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

    def forward(self, question: str) -> dspy.Prediction:
        try:
            with dspy.context(lm=self.lm, callbacks=[self.callback]):
                pred = self.agent(question=question)
        finally:
            self.callback.close()

        registered_vars = self.tracker.get_final_output_vars()
        pred.registered_vars = registered_vars
        pred.registered_var_names = sorted(registered_vars.keys())
        return pred


def placeholder_metric(example: dspy.Example, pred: dspy.Prediction, trace: Any = None) -> float:
    example_id: str = getattr(example, "id", "unknown")
    expected_vars: List[str] = getattr(example, "expected_vars", [])
    expected_count = len(expected_vars) if expected_vars else 0

    registered_vars = list(getattr(pred, "registered_var_names", []))
    registered_count = len(registered_vars) if registered_vars else 0

    count_diff = abs(registered_count - expected_count)
    count_score = max(0.0, 1.0 - 0.5 * count_diff)
    used_placeholder_count: int | None = None
    if registered_vars:
        used_placeholder_count = sum(
            1 for var in registered_vars if f"{{{var}}}" in pred.answer
        )
        placeholder_in_answer_score = used_placeholder_count / registered_count
    else:
        placeholder_in_answer_score = 1.0

    final_score = (count_score + placeholder_in_answer_score) / 2.0
    print(
        f"test_id={example_id} placeholder_metric final_score={final_score} expected_count={expected_count} "
        f"registered_count={registered_count} used_placeholder_count={used_placeholder_count} "
        f"count_score={count_score} placeholder_in_answer_score={placeholder_in_answer_score}"
    )
    return final_score


def to_percent_int(score: float) -> int:
    return int(round(score * 100))


def optimize_log_agent(
    optimizer_type: Literal["MIPROv2", "GEPA"],
    auto: Literal["light", "medium", "heavy"],
    limit_trainset: int,
    limit_testset: int,
    randomize_sets: bool = False,
    reflection_minibatch_size: int = 3,
    num_threads: int = 2,
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
        num_threads=num_threads,
        display_progress=True,
    )(baseline_module)

    if optimizer_type == "MIPROv2":
        optimizer = dspy.MIPROv2(
            metric=placeholder_metric,
            auto=auto,
            num_threads=num_threads,
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
            num_threads=num_threads,
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
        num_threads=num_threads,
        display_progress=True,
    )(optimized_module)

    print("\nResults:")
    print(f"Baseline score:  {to_percent_int(baseline_score.score)}%")
    print(f"Optimized score: {to_percent_int(optimized_score.score)}%")


def main() -> None:
    optimize_log_agent(
        optimizer_type="GEPA",
        auto="light",
        limit_trainset=20,
        limit_testset=8,
        randomize_sets=False,
        reflection_minibatch_size=8,
        num_threads=1, # REPL concurrent possible ?
    )


if __name__ == "__main__":
    main()
