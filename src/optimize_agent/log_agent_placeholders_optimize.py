from __future__ import annotations

import argparse
import csv
import json
import os
import threading
from dataclasses import asdict, is_dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, List, Literal, Optional
from uuid import uuid4

import logging

import dspy

from constants import MODEL_NAME_GEMINI_2_5_FLASH
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


def _append_metric_csv_row(
    *,
    test_id: str,
    final_score: float,
    expected_count: int,
    registered_count: int,
    used_placeholder_count: int | None,
    count_score: float,
    placeholder_in_answer_score: float,
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
        "full_run_log_filename",
    ]

    write_header = (not csv_path.exists()) or csv_path.stat().st_size == 0
    row: dict[str, Any] = {
        "test_id": test_id,
        "final_score": f"{final_score:.2f}",
        "expected_count": expected_count,
        "registered_count": registered_count,
        "used_placeholder_count": used_placeholder_count,
        "count_score": f"{count_score:.2f}",
        "placeholder_in_answer_score": f"{placeholder_in_answer_score:.2f}",
        "full_run_log_filename": full_run_log_filename,
    }

    with _CSV_LOCK:
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
        return _jsonable(asdict(value))

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


def placeholder_metric(
    example: dspy.Example, pred: dspy.Prediction, trace: Any = None
) -> float:
    """
    Evaluate how well the prediction uses expected placeholders.

    Scoring semantics:
    | Scenario                      | count_score | placeholder_in_answer_score   |
    |-------------------------------|-------------|-------------------------------|
    | expected=0, registered=0      | 1.0         | 1.0                           |
    | expected=2, registered=0      | 0.0         | 0.0                           |
    | expected=2, registered=2      | 1.0         | ratio of used/registered      |
    | expected=2, registered=4      | 1.0         | ratio of used/registered      |
    | expected=4, registered=2      | 0.0         | ratio of used/registered      |

    - count_score: Penalizes only if registered FEWER than expected.
      Registering MORE is acceptable (no penalty, but no bonus).
    - placeholder_in_answer_score: Of the placeholders registered,
      how many are actually used in the answer?
    """
    example_id: str = getattr(example, "id", "unknown")
    expected_vars: List[str] = getattr(example, "expected_vars", [])
    expected_count = len(expected_vars) if expected_vars else 0

    registered_vars = list(getattr(pred, "registered_var_names", []))
    registered_count = len(registered_vars) if registered_vars else 0

    if registered_count >= expected_count:
        count_score = 1.0
    else:
        missing_count = expected_count - registered_count
        count_score = max(0.0, 1.0 - 0.5 * missing_count)

    used_placeholder_count: int | None = None
    if registered_count == 0 and expected_count == 0:
        placeholder_in_answer_score = 1.0
    elif registered_count == 0 and expected_count > 0:
        placeholder_in_answer_score = 0.0
    else:
        used_placeholder_count = sum(
            1 for var in registered_vars if f"{{{var}}}" in pred.answer
        )
        placeholder_in_answer_score = used_placeholder_count / registered_count

    final_score = (count_score + placeholder_in_answer_score) / 2.0
    msg = (
        f"test_id={example_id} placeholder_metric final_score={final_score} expected_count={expected_count} "
        f"registered_count={registered_count} used_placeholder_count={used_placeholder_count} "
        f"count_score={count_score} placeholder_in_answer_score={placeholder_in_answer_score}"
    )
    print(msg)
    run_logger.info(msg)

    pred_json_full = _prediction_json(pred)
    pred_json_head, pred_json_tail = _head_tail(pred_json_full, n_chars=100)
    pred_dump_filename = _write_prediction_dump_json(
        test_id=example_id,
        pred=pred,
        full_run_log_filename=_CURRENT_RUN_LOG_FILENAME,
    )
    run_logger.info(
        "test_id=%s prediction_json_head=%s prediction_json_tail=%s prediction_json_file=%s",
        example_id,
        pred_json_head,
        pred_json_tail,
        pred_dump_filename,
    )
    _append_metric_csv_row(
        test_id=example_id,
        final_score=final_score,
        expected_count=expected_count,
        registered_count=registered_count,
        used_placeholder_count=used_placeholder_count,
        count_score=count_score,
        placeholder_in_answer_score=placeholder_in_answer_score,
        full_run_log_filename=_CURRENT_RUN_LOG_FILENAME,
    )
    return final_score


def to_percent_int(score: float) -> int:
    if score <= 1.0:
        return int(round(score * 100))
    if score <= 100.0:
        return int(round(score))
    return int(round(score))


def to_human_Readable_run_metadata(run_metadata: dict[str, Any]) -> str:
    return json.dumps(run_metadata, sort_keys=True, indent=4)


def optimize_log_agent(
    optimizer_type: Literal["MIPROv2", "GEPA"],
    auto: Literal["light", "medium", "heavy"],
    limit_trainset: int,
    limit_testset: int,
    randomize_sets: bool = False,
    reflection_minibatch_size: int = 3,
    num_threads: int = 2,
    baseline_only: bool = False,
    model_name: str = MODEL_NAME_GEMINI_2_5_FLASH,
    reasoning_effort: Literal["disable", "low", "medium", "high"] = "disable",
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
    args = parser.parse_args(argv)

    optimize_log_agent(
        optimizer_type="MIPROv2",
        auto="light",
        limit_trainset=20,
        limit_testset=8,
        randomize_sets=False,
        reflection_minibatch_size=8,
        num_threads=2,  # REPL concurrent possible ?
        baseline_only=args.x,
    )


if __name__ == "__main__":
    main()
