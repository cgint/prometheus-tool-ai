from __future__ import annotations

import argparse
import csv
import json
import os
import re
import threading
from dataclasses import asdict, is_dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, List, Literal, Optional
from uuid import uuid4

from pydantic import BaseModel

import logging

import dspy

from constants import MODEL_NAME_GEMINI_3_FLASH_PREVIEW
from optimize_agent.log_agent_placeholders_examples import (
    prepare_test_data,
    prepare_training_data,
)
from utils import dspy_configure, get_lm_for_model_name
from log_agent import LogAgentModule

logger = logging.getLogger(__name__)
run_logger = logging.getLogger("optimize_agent.run_logs")

_CSV_LOCK = threading.Lock()
_CURRENT_RUN_LOG_FILENAME: str | None = None
_PRED_DUMP_SEQ = 0

OptimizerType = Literal["MIPROv2", "GEPA"]
AutoLevel = Literal["light", "medium", "heavy"]
ReasoningEffort = Literal["disable", "low", "medium", "high"]


class Scenario(BaseModel):
    model_name: str
    reasoning_effort: ReasoningEffort
    optimizer_type: OptimizerType
    auto: AutoLevel


def _run_logs_dir() -> Path:
    return Path(__file__).resolve().parent / "run_logs"


def _run_summary_csv_path() -> Path:
    return _run_logs_dir() / "runs.csv"


def _append_run_summary_csv(
    *,
    run_metadata: dict[str, Any],
    baseline_score_percent: int | None,
    optimized_score_percent: int | None,
    full_run_log_filename: str,
) -> None:
    run_dir = _run_logs_dir()
    run_dir.mkdir(parents=True, exist_ok=True)

    csv_path = _run_summary_csv_path()

    # Most human-relevant parameters on the left.
    fieldnames = [
        "optimizer_type",
        "auto",
        "model_name",
        "reasoning_effort",
        "limit_trainset",
        "limit_testset",
        "num_threads",
        "reflection_minibatch_size",
        "randomize_sets",
        "baseline_only",
        "baseline_score_percent",
        "optimized_score_percent",
        "full_run_log_filename",
    ]

    def fmt2(value: int | float | None) -> str:
        return "" if value is None else f"{float(value):.2f}"

    row: dict[str, Any] = {
        "optimizer_type": run_metadata.get("optimizer_type"),
        "auto": run_metadata.get("auto"),
        "model_name": run_metadata.get("model_name"),
        "reasoning_effort": run_metadata.get("reasoning_effort"),
        "limit_trainset": run_metadata.get("limit_trainset"),
        "limit_testset": run_metadata.get("limit_testset"),
        "num_threads": run_metadata.get("num_threads"),
        "reflection_minibatch_size": run_metadata.get("reflection_minibatch_size"),
        "randomize_sets": run_metadata.get("randomize_sets"),
        "baseline_only": run_metadata.get("baseline_only"),
        "baseline_score_percent": fmt2(baseline_score_percent),
        "optimized_score_percent": fmt2(optimized_score_percent),
        "full_run_log_filename": full_run_log_filename,
    }

    write_header = (not csv_path.exists()) or csv_path.stat().st_size == 0
    with csv_path.open("a", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        if write_header:
            writer.writeheader()
        writer.writerow(row)


def _run_metrics_csv_path() -> Path:
    return _run_logs_dir() / "metrics.csv"


def _ensure_metric_csv_header(csv_path: Path, fieldnames: list[str]) -> None:
    if not csv_path.exists() or csv_path.stat().st_size == 0:
        return

    with csv_path.open("r", encoding="utf-8", newline="") as f:
        reader = csv.reader(f)
        existing_header = next(reader, None)
        if not existing_header or existing_header == fieldnames:
            return

        tmp_path = csv_path.with_suffix(".tmp")
        with tmp_path.open("w", encoding="utf-8", newline="") as tmp_file:
            writer = csv.DictWriter(tmp_file, fieldnames=fieldnames)
            writer.writeheader()
            dict_reader = csv.DictReader(f, fieldnames=existing_header)
            for row in dict_reader:
                writer.writerow(row)
        tmp_path.replace(csv_path)


def _append_metric_csv_row(
    *,
    test_id: str,
    final_score: float,
    expected_count: int,
    registered_count: int,
    used_placeholder_count: int | None,
    count_score: float,
    placeholder_in_answer_score: float,
    tool_error_count: int,
    tool_error_score: float,
    tool_error_categories: dict[str, int],
    full_run_log_filename: str | None,
) -> None:
    run_dir = _run_logs_dir()
    run_dir.mkdir(parents=True, exist_ok=True)

    csv_path = _run_metrics_csv_path()
    fieldnames = [
        "test_id",
        "final_score",
        "expected_count",
        "registered_count",
        "used_placeholder_count",
        "count_score",
        "placeholder_in_answer_score",
        "tool_error_count",
        "tool_error_score",
        "tool_error_categories",
        "full_run_log_filename",
    ]

    row: dict[str, Any] = {
        "test_id": test_id,
        "final_score": f"{final_score:.2f}",
        "expected_count": expected_count,
        "registered_count": registered_count,
        "used_placeholder_count": used_placeholder_count,
        "count_score": f"{count_score:.2f}",
        "placeholder_in_answer_score": f"{placeholder_in_answer_score:.2f}",
        "tool_error_count": tool_error_count,
        "tool_error_score": f"{tool_error_score:.2f}",
        "tool_error_categories": json.dumps(tool_error_categories, sort_keys=True),
        "full_run_log_filename": full_run_log_filename,
    }

    with _CSV_LOCK:
        _ensure_metric_csv_header(csv_path, fieldnames)
        write_header = (not csv_path.exists()) or csv_path.stat().st_size == 0
        with csv_path.open("a", encoding="utf-8", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            if write_header:
                writer.writeheader()
            writer.writerow(row)


def _start_run_file_logging(
    run_metadata: dict[str, Any],
) -> tuple[Path, logging.Handler]:
    run_dir = _run_logs_dir()
    run_dir.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    run_id = f"{timestamp}_pid{os.getpid()}_{uuid4().hex[:8]}"
    log_path = run_dir / f"{run_id}.log"

    handler = logging.FileHandler(log_path, encoding="utf-8")
    handler.setLevel(logging.INFO)
    handler.setFormatter(
        logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s")
    )

    run_logger.setLevel(logging.INFO)
    run_logger.propagate = False
    run_logger.addHandler(handler)

    # Ensure logs still show up on the terminal even if the environment doesn't
    # configure logging for this module.
    if not any(
        isinstance(h, logging.StreamHandler) and not isinstance(h, logging.FileHandler)
        for h in run_logger.handlers
    ):
        stream_handler = logging.StreamHandler()
        stream_handler.setLevel(logging.INFO)
        stream_handler.setFormatter(
            logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s")
        )
        run_logger.addHandler(stream_handler)

    run_logger.info("run_log_path=%s", log_path)
    run_logger.info("run_config=%s", json.dumps(run_metadata, sort_keys=True))
    return log_path, handler


def _jsonable(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value

    if isinstance(value, dict):
        return {str(k): _jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(v) for v in value]
    if isinstance(value, set):
        return [_jsonable(v) for v in sorted(value, key=lambda x: str(x))]

    if is_dataclass(value):
        return _jsonable(asdict(value))  # type: ignore[arg-type]

    model_dump = getattr(value, "model_dump", None)
    if callable(model_dump):
        try:
            return _jsonable(model_dump())
        except Exception:
            return str(value)

    to_dict = getattr(value, "to_dict", None)
    if callable(to_dict):
        try:
            return _jsonable(to_dict())
        except Exception:
            return str(value)

    as_dict = getattr(value, "dict", None)
    if callable(as_dict):
        try:
            return _jsonable(as_dict())
        except Exception:
            return str(value)

    try:
        return _jsonable(vars(value))
    except Exception:
        return str(value)


def _prediction_json(pred: Any) -> str:
    try:
        return json.dumps(_jsonable(pred), sort_keys=True, ensure_ascii=False)
    except Exception:
        return json.dumps({"repr": repr(pred)}, ensure_ascii=False)


def _head_tail(text: str, *, n_chars: int = 100) -> tuple[str, str]:
    if n_chars <= 0:
        return "", ""
    head = text[:n_chars]
    tail = text[-n_chars:] if len(text) > n_chars else text
    return head, tail


def _safe_filename_component(text: str) -> str:
    safe = []
    for ch in text:
        if ch.isalnum() or ch in ("-", "_", "."):
            safe.append(ch)
        else:
            safe.append("_")
    out = "".join(safe).strip("._")
    return out or "unknown"


def _write_prediction_dump_json(
    *,
    test_id: str,
    pred: Any,
    full_run_log_filename: str | None,
) -> str:
    global _PRED_DUMP_SEQ
    run_dir = _run_logs_dir()
    run_dir.mkdir(parents=True, exist_ok=True)

    run_stem = (
        Path(full_run_log_filename).stem if full_run_log_filename else "unknown_run"
    )
    safe_test_id = _safe_filename_component(test_id)

    with _CSV_LOCK:
        _PRED_DUMP_SEQ += 1
        seq = _PRED_DUMP_SEQ

    filename = f"{run_stem}__pred_{seq:04d}__{safe_test_id}.json"
    path = run_dir / filename

    payload = {
        "intent": "Full DSPy prediction object passed into placeholder_metric for debugging and analysis.",
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "test_id": test_id,
        "full_run_log_filename": full_run_log_filename,
        "prediction": _jsonable(pred),
    }
    path.write_text(
        json.dumps(payload, sort_keys=True, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return filename


class PlaceholderMetricDetails(BaseModel):
    example_id: str
    expected_count: int
    registered_count: int
    used_placeholder_count: int
    count_score: float
    placeholder_in_answer_score: float
    tool_error_count: int
    tool_error_score: float
    tool_error_categories: dict[str, int]
    final_score: float
    unregistered_placeholders: list[str]


_TOOL_ERROR_PATTERNS: list[tuple[str, str, str]] = [
    (
        "register_for_final_output_non_string",
        r"register_for_final_output only accepts string values",
        "register_for_final_output expects strings; convert non-strings with str(...) and format structured outputs.",
    ),
    (
        "syntax_error",
        r"SyntaxError:",
        "Fix Python syntax; use proper quoting and avoid invalid eval-only statements.",
    ),
    (
        "restricted_import",
        r"ImportError: Import '.*' not allowed",
        "Use only the allowed imports inside python_repl.",
    ),
    (
        "finish_arg_mismatch",
        r"Arg .* is not in the tool's args",
        "The finish tool takes no arguments; call it without any parameters.",
    ),
    (
        "file_not_found",
        r"FileNotFoundError:",
        "Verify log file paths via get_available_files() before reading.",
    ),
    (
        "json_decode_error",
        r"JSONDecodeError:",
        "Ensure JSON strings are valid and use double quotes for keys/strings.",
    ),
    (
        "name_error",
        r"NameError:",
        "Avoid undefined names; rely on provided helpers and declared variables.",
    ),
    (
        "type_error",
        r"TypeError:",
        "Check argument types passed to helpers/tools.",
    ),
    (
        "value_error",
        r"ValueError:",
        "Check argument names/values passed to helpers/tools.",
    ),
]


def _extract_trajectory_observations(pred: dspy.Prediction) -> list[str]:
    trajectory = getattr(pred, "trajectory", None)
    if trajectory is None:
        store = getattr(pred, "_store", None)
        if isinstance(store, dict):
            trajectory = store.get("trajectory")
    if isinstance(trajectory, dict):
        return [
            str(value)
            for key, value in trajectory.items()
            if key.startswith("observation_")
        ]
    if isinstance(trajectory, list):
        return [str(value) for value in trajectory]
    return []


def _classify_tool_error(observation: str) -> tuple[str, str]:
    for category, pattern, hint in _TOOL_ERROR_PATTERNS:
        if re.search(pattern, observation):
            return category, hint
    return "unknown_error", "Review the traceback and correct the tool usage or code."


def _tool_error_summary(
    pred: dspy.Prediction,
) -> tuple[int, float, dict[str, int], list[str]]:
    observations = _extract_trajectory_observations(pred)
    error_categories: dict[str, int] = {}
    hints: list[str] = []

    for observation in observations:
        if "Traceback" not in observation and "Execution error" not in observation:
            continue
        category, hint = _classify_tool_error(observation)
        error_categories[category] = error_categories.get(category, 0) + 1
        if hint not in hints:
            hints.append(hint)

    error_count = sum(error_categories.values())
    if error_count == 0:
        error_score = 1.0
    else:
        error_score = max(0.0, 1.0 - 0.25 * error_count)
    return error_count, error_score, error_categories, hints


def _placeholder_metric_details(
    example: dspy.Example, pred: dspy.Prediction
) -> tuple[PlaceholderMetricDetails, str]:
    """
    Evaluate how well the prediction uses expected placeholders.

    final_score = average(count_score, placeholder_in_answer_score, tool_error_score)

    Scoring semantics:
    | Scenario                      | count_score | placeholder_in_answer_score       |
    |-------------------------------|-------------|-----------------------------------|
    | expected=0, registered=0      | 1.0         | 1.0                               |
    | expected=2, registered=0      | 0.0         | ratio of used/expected            |
    | expected=2, registered=2      | 1.0         | ratio of used/expected            |
    | expected=2, registered=4      | 1.0         | ratio of used/expected (capped)   |
    | expected=4, used=2            | 0.0         | ratio of used/expected            |

    Additional examples (expressive, no table format):
    - Expected=3, Registered=5, Used=3
      -> count_score=1.0 (registered >= expected)
      -> placeholder_in_answer_score=1.0 (used capped to expected)
    - Expected=3, Registered=5, Used=1
      -> count_score=1.0
      -> placeholder_in_answer_score=1/3
    - Expected=1, Registered=0, Used=0
      -> count_score=0.0
      -> placeholder_in_answer_score=0.0
    - Expected=0, Registered=2, Used=2
      -> count_score=1.0
      -> placeholder_in_answer_score=1.0 (expected_count=0 is not penalized)
    - Expected=4, Registered=4, Used=6
      -> count_score=1.0
      -> placeholder_in_answer_score=1.0 (used capped to expected)

    - count_score: Penalizes only if registered FEWER than expected.
      Registering MORE is acceptable (no penalty, but no bonus).
    - placeholder_in_answer_score: Of the REGISTERED placeholders,
      how many are actually used in the answer, capped by expected_count.
      Placeholder names do not need to match expected names.
      If expected_count is zero, placeholder usage is not penalized.
    - tool_error_score: Starts at 1.0 and is reduced by 0.25 per tool traceback
      observed in the trajectory (floored at 0.0).
    - final_score: Average of count_score, placeholder_in_answer_score,
      and tool_error_score.
    """
    example_id: str = getattr(example, "id", "unknown")
    expected_count = int(getattr(example, "expected_var_used_count", 0) or 0)

    registered_vars = list(getattr(pred, "registered_var_names", []))
    registered_count = len(registered_vars) if registered_vars else 0

    if registered_count >= expected_count:
        count_score = 1.0
    else:
        missing_count = expected_count - registered_count
        count_score = max(0.0, 1.0 - 0.5 * missing_count)

    answer_text = pred.answer or ""
    used_placeholder_count = sum(
        1 for var in registered_vars if f"{{{var}}}" in answer_text
    )

    if expected_count == 0:
        placeholder_in_answer_score = 1.0
    else:
        capped_used_count = min(used_placeholder_count, expected_count)
        placeholder_in_answer_score = capped_used_count / expected_count

    tool_error_count, tool_error_score, tool_error_categories, tool_error_hints = (
        _tool_error_summary(pred)
    )

    final_score = (
        count_score + placeholder_in_answer_score + tool_error_score
    ) / 3.0

    placeholder_matches = set(re.findall(r"\{([^\}]+)\}", answer_text))
    unregistered_placeholders = sorted(
        var for var in placeholder_matches if var not in registered_vars
    )

    details = PlaceholderMetricDetails(
        example_id=example_id,
        expected_count=expected_count,
        registered_count=registered_count,
        used_placeholder_count=used_placeholder_count,
        count_score=count_score,
        placeholder_in_answer_score=placeholder_in_answer_score,
        tool_error_count=tool_error_count,
        tool_error_score=tool_error_score,
        tool_error_categories=tool_error_categories,
        final_score=final_score,
        unregistered_placeholders=unregistered_placeholders,
    )

    unregistered_text = (
        ", ".join(unregistered_placeholders) if unregistered_placeholders else "none"
    )

    if expected_count == 0:
        expected_vs_used_msg = (
            "Expected vs used: expected 0 placeholders; usage is not required."
        )
    elif used_placeholder_count == expected_count:
        expected_vs_used_msg = (
            f"Expected vs used: expected {expected_count}, used {used_placeholder_count} (ok)."
        )
    elif used_placeholder_count < expected_count:
        expected_vs_used_msg = (
            f"Expected vs used: expected {expected_count}, used {used_placeholder_count} (missing {expected_count - used_placeholder_count})."
        )
    else:
        expected_vs_used_msg = (
            f"Expected vs used: expected {expected_count}, used {used_placeholder_count} (some extra use of placeholders is ok)."
        )

    if registered_count >= expected_count:
        registered_msg = (
            f"Registration: registered {registered_count} placeholders (ok; expected at least {expected_count})."
        )
    else:
        registered_msg = (
            f"Registration: registered {registered_count} placeholders (missing {expected_count - registered_count})."
        )

    if unregistered_placeholders:
        unregistered_msg = (
            f"Answer placeholders not registered: {unregistered_text}."
        )
    else:
        unregistered_msg = "Answer placeholders all registered (ok)."

    if tool_error_count == 0:
        tool_error_msg = "Tool errors: none."
    else:
        categories_text = ", ".join(
            f"{name}={count}"
            for name, count in sorted(tool_error_categories.items())
        )
        hints_text = "; ".join(tool_error_hints) if tool_error_hints else "Review tracebacks."
        tool_error_msg = (
            f"Tool errors: {tool_error_count} ({categories_text}). Hints: {hints_text}."
        )

    if final_score < 1.0:
        feedback_prefix = (
            "Use placeholders for all computed values and ensure variables are registered. "
            "Do not paste computed data directly."
        )
    else:
        feedback_prefix = "Good: placeholder usage and registration look correct within the expectations."

    feedback = (
        f"{feedback_prefix} {expected_vs_used_msg} {registered_msg} "
        f"{unregistered_msg} {tool_error_msg}"
    )

    return details, feedback


def placeholder_metric(
    example: dspy.Example, pred: dspy.Prediction, trace: Any = None
) -> float:
    details, _feedback = _placeholder_metric_details(example, pred)

    msg = (
        f"test_id={details.example_id} placeholder_metric final_score={details.final_score} expected_count={details.expected_count} "
        f"registered_count={details.registered_count} used_placeholder_count={details.used_placeholder_count} "
        f"count_score={details.count_score} placeholder_in_answer_score={details.placeholder_in_answer_score} "
        f"tool_error_count={details.tool_error_count} tool_error_score={details.tool_error_score}"
    )
    print(msg)
    run_logger.info(msg)

    pred_json_full = _prediction_json(pred)
    pred_json_head, pred_json_tail = _head_tail(pred_json_full, n_chars=100)
    pred_dump_filename = _write_prediction_dump_json(
        test_id=details.example_id,
        pred=pred,
        full_run_log_filename=_CURRENT_RUN_LOG_FILENAME,
    )
    run_logger.info(
        "test_id=%s prediction_json_head=%s prediction_json_tail=%s prediction_json_file=%s",
        details.example_id,
        pred_json_head,
        pred_json_tail,
        pred_dump_filename,
    )
    _append_metric_csv_row(
        test_id=details.example_id,
        final_score=details.final_score,
        expected_count=details.expected_count,
        registered_count=details.registered_count,
        used_placeholder_count=details.used_placeholder_count,
        count_score=details.count_score,
        placeholder_in_answer_score=details.placeholder_in_answer_score,
        tool_error_count=details.tool_error_count,
        tool_error_score=details.tool_error_score,
        tool_error_categories=details.tool_error_categories,
        full_run_log_filename=_CURRENT_RUN_LOG_FILENAME,
    )
    return details.final_score


def to_percent_int(score: float) -> int:
    if score <= 1.0:
        return int(round(score * 100))
    if score <= 100.0:
        return int(round(score))
    return int(round(score))


def to_human_Readable_run_metadata(run_metadata: dict[str, Any]) -> str:
    return json.dumps(run_metadata, sort_keys=True, indent=4)


def optimize_log_agent(
    optimizer_type: OptimizerType,
    auto: AutoLevel,
    limit_trainset: int,
    limit_testset: int,
    randomize_sets: bool = False,
    reflection_minibatch_size: int = 3,
    num_threads: int = 2,
    baseline_only: bool = False,
    model_name: str = MODEL_NAME_GEMINI_3_FLASH_PREVIEW,
    reasoning_effort: ReasoningEffort = "disable",
) -> None:
    run_metadata: dict[str, Any] = {
        "optimizer_type": optimizer_type,
        "auto": auto,
        "limit_trainset": limit_trainset,
        "limit_testset": limit_testset,
        "randomize_sets": randomize_sets,
        "reflection_minibatch_size": reflection_minibatch_size,
        "num_threads": num_threads,
        "baseline_only": baseline_only,
        "model_name": model_name,
        "reasoning_effort": reasoning_effort,
    }

    log_path, handler = _start_run_file_logging(run_metadata)
    global _CURRENT_RUN_LOG_FILENAME
    _CURRENT_RUN_LOG_FILENAME = log_path.name
    try:
        lm = get_lm_for_model_name(model_name, reasoning_effort)
        dspy_configure(lm)

        trainset = prepare_training_data(limit=limit_trainset)
        testset = prepare_test_data(limit=limit_testset)

        if randomize_sets:
            import random

            random.shuffle(trainset)
            random.shuffle(testset)

        baseline_module = LogAgentModule()
        baseline_score = dspy.Evaluate(
            devset=testset,
            metric=placeholder_metric,
            num_threads=num_threads,
            display_progress=True,
        )(baseline_module)
        baseline_score_percent = to_percent_int(baseline_score.score)
        run_logger.info("baseline_score_percent=%s", baseline_score_percent)
        print(f"\nBaseline score:  {baseline_score_percent}%")

        if baseline_only:
            print(f"\nRun metadata: {to_human_Readable_run_metadata(run_metadata)}")
            _append_run_summary_csv(
                run_metadata=run_metadata,
                baseline_score_percent=baseline_score_percent,
                optimized_score_percent=None,
                full_run_log_filename=log_path.name,
            )
            return

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
                    details, feedback = _placeholder_metric_details(gold, pred)
                    score = details.final_score
                    if pred_name is None:
                        return score
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

        optimized_module = optimizer.compile(
            LogAgentModule(),
            trainset=trainset,
            valset=testset,
        )

        optimized_score = dspy.Evaluate(
            devset=testset,
            metric=placeholder_metric,
            num_threads=num_threads,
            display_progress=True,
        )(optimized_module)

        optimized_score_percent = to_percent_int(optimized_score.score)
        run_logger.info("optimized_score_percent=%s", optimized_score_percent)
        run_logger.info("run_metadata=%s", to_human_Readable_run_metadata(run_metadata))
        _append_run_summary_csv(
            run_metadata=run_metadata,
            baseline_score_percent=baseline_score_percent,
            optimized_score_percent=optimized_score_percent,
            full_run_log_filename=log_path.name,
        )
        print("\nResults:")
        print(f"Baseline score:  {baseline_score_percent}%")
        print(f"Optimized score: {optimized_score_percent}%")

        # Save a combined metadata + program JSON
        combined_save_path = (
            _run_logs_dir()
            / f"optimized_log_agent_{int(datetime.now(timezone.utc).timestamp())}_{baseline_score_percent}_to_{optimized_score_percent}_combined.json"
        )
        combined_data = {
            "metadata": {
                "model_name": model_name,
                "reasoning_effort": reasoning_effort,
                "optimizer_type": optimizer_type,
                "auto": auto,
                "baseline_score_percent": baseline_score_percent,
                "optimized_score_percent": optimized_score_percent,
                "timestamp": int(datetime.now(timezone.utc).timestamp()),
                "trainset_size": limit_trainset,
                "testset_size": limit_testset,
                "num_threads": num_threads,
                "reflection_minibatch_size": reflection_minibatch_size,
                "randomize_sets": randomize_sets,
            },
            "program": optimized_module.dump_state(),
        }
        with open(combined_save_path, "w") as f:
            json.dump(combined_data, f, indent=2)
        print(f"💾 Combined format saved to: {combined_save_path}")
        run_logger.info("combined_program_saved=%s", combined_save_path)
    finally:
        run_logger.info("run_end run_log_path=%s", log_path)
        run_logger.removeHandler(handler)
        handler.close()
        _CURRENT_RUN_LOG_FILENAME = None


def main(argv: Optional[list[str]] = None) -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "-x",
        action="store_true",
        help="Only compute baseline metrics and exit (skip optimization).",
    )
    parser.add_argument("--model-name", type=str)
    parser.add_argument(
        "--reasoning-effort",
        choices=["disable", "low", "medium", "high"],
    )
    parser.add_argument(
        "--optimizer-type",
        choices=["MIPROv2", "GEPA"],
    )
    parser.add_argument(
        "--auto",
        choices=["light", "medium", "heavy"],
    )
    parser.add_argument(
        "--repeat",
        type=int,
        default=1,
        help="Repeat the selected scenario(s) this many times in the same process.",
    )
    args = parser.parse_args(argv)

    override_values = [
        args.model_name,
        args.reasoning_effort,
        args.optimizer_type,
        args.auto,
    ]
    if any(value is not None for value in override_values) and not all(
        value is not None for value in override_values
    ):
        parser.error(
            "Provide either none or all of --model-name, --reasoning-effort, "
            "--optimizer-type, and --auto."
        )

    if all(value is not None for value in override_values):
        scenarios = [
            Scenario(
                model_name=args.model_name,
                reasoning_effort=args.reasoning_effort,
                optimizer_type=args.optimizer_type,
                auto=args.auto,
            )
        ]
    else:
        model_config: List[tuple[str, List[ReasoningEffort]]] = [
            (MODEL_NAME_GEMINI_3_FLASH_PREVIEW, ["disable"]),
            # (MODEL_NAME_GEMINI_2_5_FLASH_LITE, ["low", "medium", "high"]),
            # (MODEL_NAME_GEMINI_2_5_FLASH, ["disable", "low", "medium", "high"]),
            # (MODEL_NAME_GEMINI_2_5_PRO, ["low", "medium", "high"]),
        ]
        optimizer_types: List[OptimizerType] = ["GEPA"]
        autos: List[AutoLevel] = ["light"]
        scenarios = [
            Scenario(
                model_name=model_name,
                reasoning_effort=reasoning_effort,
                optimizer_type=optimizer_type,
                auto=auto,
            )
            for model_name, reasoning_efforts in model_config
            for reasoning_effort in reasoning_efforts
            for optimizer_type in optimizer_types
            for auto in autos
        ]

    repeat_count = max(1, args.repeat)
    for _ in range(repeat_count):
        for scenario in scenarios:
            try:
                optimize_log_agent(
                    optimizer_type=scenario.optimizer_type,
                    auto=scenario.auto,
                    limit_trainset=20,
                    limit_testset=8,
                    randomize_sets=False,
                    reflection_minibatch_size=8,
                    num_threads=1,  # REPL concurrent possible ?
                    baseline_only=args.x,
                    model_name=scenario.model_name,
                    reasoning_effort=scenario.reasoning_effort,
                )
            except Exception as e:
                import traceback
                traceback.print_exc()
                print(f"Error in scenario {scenario}: {e}")


if __name__ == "__main__":
    main()
