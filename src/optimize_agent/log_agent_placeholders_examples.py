from __future__ import annotations

from dataclasses import dataclass
from typing import List

import dspy


@dataclass(frozen=True)
class QAExample:
    id: str
    question: str
    expected_var_used_count: int


def _make_example(ex: QAExample) -> dspy.Example:
    return dspy.Example(
        id=ex.id,
        question=ex.question,
        expected_var_used_count=ex.expected_var_used_count,
    ).with_inputs("question")


TRAIN_EXAMPLES: List[QAExample] = [
    QAExample(
        id="train_error_counts_with_files_list",
        question=(
            "Read the three sample logs under src/optimize_agent/sample_logs.\n"
            "First, discover the available files using a tool. Then count how many lines contain the substring \"ERROR\" in each file, "
            "and compute the total across all files.\n"
            "Output format:\n"
            "1) One-sentence explanation\n"
            "2) A bullet list of the files you analyzed\n"
            "3) A per-file counts block\n"
            "4) A final total line"
        ),
        expected_var_used_count=3,
    ),
    QAExample(
        id="train_warn_counts_markdown_table",
        question=(
            "Using the sample logs in src/optimize_agent/sample_logs, count the number of lines containing the substring \"WARN\" per file "
            "and the total across all files.\n"
            "Return a compact Markdown table with columns: file, warn_count, and a separate total line."
        ),
        expected_var_used_count=2,
    ),
    QAExample(
        id="train_info_counts_json",
        question=(
            "Read these exact log files:\n"
            "- src/optimize_agent/sample_logs/file1.log\n"
            "- src/optimize_agent/sample_logs/file2.log\n"
            "- src/optimize_agent/sample_logs/file3.log\n\n"
            "Compute how many lines contain the substring \"INFO\" in each file.\n"
            "Return (a) a short explanation and (b) a JSON object mapping filename -> info_count."
        ),
        expected_var_used_count=1,
    ),
    QAExample(
        id="train_max_error_file",
        question=(
            "From the three sample logs, find which file has the highest number of \"ERROR\" lines.\n"
            "Return a short explanation and then the winning file path on its own line."
        ),
        expected_var_used_count=1,
    ),
    QAExample(
        id="train_unique_error_lines",
        question=(
            "In the three sample logs, list the unique ERROR messages (the full line text) across all files, sorted alphabetically.\n"
            "Return a short explanation plus the list (one message per line)."
        ),
        expected_var_used_count=1,
    ),
    QAExample(
        id="train_log_summary_csv",
        question=(
            "Compute a CSV summary for the sample logs (src/optimize_agent/sample_logs):\n"
            "Columns: file,error_count,warn_count,info_count,total_lines\n"
            "Include a header row.\n"
            "Return only the CSV."
        ),
        expected_var_used_count=1,
    ),
]


TEST_EXAMPLES: List[QAExample] = [
    QAExample(
        id="test_error_counts_total",
        question=(
            "You have access to tools for reading sample logs.\n"
            "Determine which files exist in src/optimize_agent/sample_logs, then compute per-file ERROR counts and the overall total.\n"
            "Return a brief explanation, then a per-file block, then the total."
        ),
        expected_var_used_count=2,
    ),
    QAExample(
        id="test_error_or_warn_total",
        question=(
            "Across the three sample logs, compute the total number of lines that contain any of these substrings: \"ERROR\" or \"WARN\".\n"
            "Return a one-sentence explanation and the total as an integer on its own line."
        ),
        expected_var_used_count=2,
    ),
    QAExample(
        id="test_markdown_report_placeholders",
        question=(
            "Read the three sample logs and produce a Markdown report with two sections:\n"
            "## Totals\n"
            "- total_error\n"
            "- total_warn\n"
            "## Notes\n"
            "- one short observation about the logs\n\n"
            "Do not include any computed numbers directly; use placeholders."
        ),
        expected_var_used_count=3,
    ),
    QAExample(
        id="test_lines_and_errors_per_file",
        question=(
            "For the sample logs, return a per-file breakdown of total lines and ERROR lines, formatted as:\n"
            "<file>: <total_lines> lines, <error_lines> errors\n"
            "One file per line."
        ),
        expected_var_used_count=1,
    ),
]


def prepare_training_data(limit: int | None = None) -> List[dspy.Example]:
    examples = [_make_example(ex) for ex in TRAIN_EXAMPLES]
    if limit is not None:
        return examples[:limit]
    return examples


def prepare_test_data(limit: int | None = None) -> List[dspy.Example]:
    examples = [_make_example(ex) for ex in TEST_EXAMPLES]
    if limit is not None:
        return examples[:limit]
    return examples
