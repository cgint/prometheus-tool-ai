from __future__ import annotations

from typing import List

import dspy


EXPECTED_VARS = ["per_file_counts_text", "total_error_lines_str"]


TRAIN_QUESTIONS: List[str] = [
    'Read these local log files: ["src/optimize_agent/sample_logs/file1.log", "src/optimize_agent/sample_logs/file2.log", "src/optimize_agent/sample_logs/file3.log"]. '
    'For each file, compute how many lines contain the substring "ERROR". Also compute the total across all files. '
    "Return a short explanation plus the per-file counts and the total.",
    "Count ERROR lines per file for: src/optimize_agent/sample_logs/file1.log, src/optimize_agent/sample_logs/file2.log, src/optimize_agent/sample_logs/file3.log. "
    "Include a short explanation, then the per-file list, then the total.",
    "From these logs (file1.log, file2.log, file3.log in src/optimize_agent/sample_logs), count lines containing ERROR per file "
    "and the overall total. Provide a short explanation and the counts.",
    "Please read src/optimize_agent/sample_logs/file1.log, src/optimize_agent/sample_logs/file2.log, src/optimize_agent/sample_logs/file3.log and compute "
    'how many lines include "ERROR" for each file. Also compute the grand total.',
    "Compute ERROR-line counts per file for the three sample logs and the total across files. "
    "Return a brief explanation, then the counts.",
    "Analyze src/optimize_agent/sample_logs/file1.log, src/optimize_agent/sample_logs/file2.log, src/optimize_agent/sample_logs/file3.log. "
    'For each file, count lines containing "ERROR" and report the total across all files.',
    "For each of these logs, count lines with ERROR: "
    '["src/optimize_agent/sample_logs/file1.log", "src/optimize_agent/sample_logs/file2.log", "src/optimize_agent/sample_logs/file3.log"]. '
    "Also compute the total and provide a short explanation.",
    "Read the three sample logs in src/optimize_agent/sample_logs and count ERROR lines per file. "
    "Then compute the total and respond with a short explanation plus the counts.",
    "Please compute the ERROR line count for each log file in src/optimize_agent/sample_logs (file1.log, file2.log, file3.log). "
    "Also compute the total across all files.",
    "Count ERROR lines per file for the three sample logs and include a concise explanation of the result.",
    "From src/optimize_agent/sample_logs/file1.log, file2.log, and file3.log, count ERROR lines per file and total them. "
    "Return explanation + per-file counts + total.",
    "Check the three sample logs and report the number of ERROR lines per file and the total. "
    "Keep the explanation short.",
    "Summarize ERROR-line counts for file1.log, file2.log, file3.log under src/optimize_agent/sample_logs, and compute the total. "
    "Provide a short explanation.",
    "Read src/optimize_agent/sample_logs/file1.log, src/optimize_agent/sample_logs/file2.log, src/optimize_agent/sample_logs/file3.log and calculate "
    "per-file ERROR line counts and the total across all files.",
    "Compute how many lines contain ERROR in each of the three sample log files and the overall total. "
    "Provide a short explanation first.",
    "Please analyze the three sample logs and report ERROR line counts per file and total. "
    "Return a brief explanation followed by the counts.",
    "For the sample logs under src/optimize_agent/sample_logs, count ERROR lines per file and provide the overall total. "
    "Add a short explanation.",
    "Count lines containing ERROR in each sample log file (file1.log, file2.log, file3.log). "
    "Also compute the total across all files.",
    "Compute ERROR line counts per file for the three sample logs, and include a short explanation plus the total.",
    "Read the three sample logs and produce the per-file ERROR counts and the overall total with a brief explanation.",
]


TEST_QUESTIONS: List[str] = [
    "Count ERROR lines in the three sample logs and return per-file counts plus the total.",
    'Read ["src/optimize_agent/sample_logs/file1.log", "src/optimize_agent/sample_logs/file2.log", "src/optimize_agent/sample_logs/file3.log"] and count ERROR lines '
    "per file and in total.",
    "Analyze the sample logs and report ERROR-line counts per file and the overall total.",
    "For each sample log file, count lines containing ERROR, then compute the total across all files.",
    "Provide a short explanation and the per-file ERROR counts plus the total for the three sample logs.",
    "Summarize ERROR lines for file1.log, file2.log, file3.log (under src/optimize_agent/sample_logs) and include the total.",
    "Count ERROR lines per file for the sample logs and report the overall total.",
    "Check the three sample log files and return per-file ERROR counts and the total.",
]


def _make_example(question: str) -> dspy.Example:
    answer = (
        "Here are the error counts for each file:\n"
        "{per_file_counts_text}\n\n"
        "Total error lines across all files: {total_error_lines_str}"
    )
    return dspy.Example(
        question=question,
        answer=answer,
        expected_vars=list(EXPECTED_VARS),
    ).with_inputs("question")


def prepare_training_data(limit: int | None = None) -> List[dspy.Example]:
    examples = [_make_example(q) for q in TRAIN_QUESTIONS]
    if limit is not None:
        return examples[:limit]
    return examples


def prepare_test_data(limit: int | None = None) -> List[dspy.Example]:
    examples = [_make_example(q) for q in TEST_QUESTIONS]
    if limit is not None:
        return examples[:limit]
    return examples
