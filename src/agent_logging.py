"""Shared logging utilities for agent runs."""

import json
import os
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Optional

from dspy_utils import capture_dspy_inspect_history
from tool_tracker import ToolUsageTracker


@dataclass
class AgentLogConfig:
    """Configuration for what to log."""
    write_summary: bool = True
    write_usage: bool = False
    write_history: bool = False
    write_final_answer: bool = False
    write_tool_calls: bool = False
    print_summary: bool = True
    print_registered_vars: bool = False
    print_raw_answer: bool = False
    print_final_answer: bool = True
    summary_cutoff_length: int = 100


def write_agent_logs(
    agent_name: str,
    tracker: ToolUsageTracker,
    prediction: Any,
    config: Optional[AgentLogConfig] = None,
) -> str:
    """
    Write logs for an agent run and return the rendered final answer.

    Args:
        agent_name: Name prefix for log files (e.g., 'fib_agent', 'prom_agent')
        tracker: The ToolUsageTracker instance
        prediction: The prediction object from the agent (must have .answer and optionally .get_lm_usage())
        config: Optional logging configuration. Defaults to writing summary only.

    Returns:
        The rendered final answer with placeholders replaced.
    """
    if config is None:
        config = AgentLogConfig()

    run_id = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_dir = f"logs/{agent_name}"
    os.makedirs(log_dir, exist_ok=True)
    log_prefix = f"{log_dir}/{agent_name}_{run_id}"

    # Write summary file
    if config.write_summary:
        with open(f"{log_prefix}.md", "w") as f:
            f.write(tracker.get_summary())

    # Write usage JSON
    if config.write_usage:
        usage = prediction.get_lm_usage()
        if usage:
            with open(f"{log_prefix}_usage.json", "w") as f:
                f.write(json.dumps(usage, indent=2))

    # Write history
    if config.write_history:
        history = capture_dspy_inspect_history()
        with open(f"{log_prefix}_history.md", "w") as f:
            f.write(history)

    # Write tool calls
    if config.write_tool_calls:
        with open(f"{log_prefix}_tool_calls.json", "w") as f:
            f.write(json.dumps(tracker.get_tool_logs(), indent=2, default=str))

    # Print summary
    if config.print_summary:
        tracker.print_summary(cutoff_input_output_length=config.summary_cutoff_length)

    # Render final answer
    final_vars = tracker.get_final_output_vars()
    final_answer = tracker.render_with_final_output_vars(prediction.answer, final_vars)

    # Write final answer
    if config.write_final_answer:
        with open(f"{log_prefix}_final_answer.md", "w") as f:
            f.write(final_answer)

    # Console output
    separator = "=" * 60

    if config.print_registered_vars:
        print(f"\n{separator}")
        print("REGISTERED VARS:")
        for k, v in final_vars.items():
            preview = str(v)[:80] + "..." if len(str(v)) > 80 else str(v)
            print(f"  {k}: {preview}")
        print(separator)

    if config.print_raw_answer:
        if not config.print_registered_vars:
            print(f"\n{separator}")
        print(f"RAW pred.answer:\n{prediction.answer}")
        print(separator)

    if config.print_final_answer:
        if not (config.print_registered_vars or config.print_raw_answer):
            print(f"\n{separator}")
        print(f"RENDERED final_answer:\n{final_answer}")
        print(f"{separator}\n")

    return final_answer
