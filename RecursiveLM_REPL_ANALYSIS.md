# REPL Performance Analysis for Big-Data Use

## Scope and sources
- `src/repl/python_tool_repl.py`
- `src/log_agent.py`
- `tests/test_python_tool_repl.py`
- `src/optimize_agent/runs_docs/20260114_run_33_50.md`
- `RecursiveLanguageModels.txt`
- `github_rlm_ref_impl_code.md`

## Clarifications (from you)
- Current target data is small and primarily for testing (e.g. `src/optimize_agent/sample_logs/`).
- Multi-turn REPL state beyond a single agent run is not a requirement.

## Observed signals from the run log
- The run log is dominated by repeated REPL instruction blocks and repeated `python_repl` call markers, with no captured REPL code or computed outputs. This makes it hard to pinpoint concrete failure modes (see `src/optimize_agent/runs_docs/20260114_run_33_50.md:864` and `src/optimize_agent/runs_docs/20260114_run_33_50.md:875`).
- Metrics fluctuate across trials (Average Metric values like 0.0/1, 1.0/2, 1.5/3), and the baseline/optimized summary is reported in a nonstandard percent format, which suggests unstable evaluation or logging clarity issues (see `src/optimize_agent/runs_docs/20260114_run_33_50.md:874` and `src/optimize_agent/runs_docs/20260114_run_33_50.md:967`).

## Current REPL constraints that conflict with big-data workflows
- Data ingestion is capped at 200,000 bytes per call and has no offset or streaming capability, which blocks full scans of large files (see `src/log_agent.py:14`).
- The REPL environment uses a restricted import allowlist and a minimal builtin set; file system utilities like `os` are explicitly blocked in tests, which prevents direct file access for large data (see `src/repl/python_tool_repl.py:73` and `tests/test_python_tool_repl.py:46`).
- Each REPL call is limited to 30 lines, forcing multi-call orchestration for complex transformations and increasing the chance of partial state or planning errors on big tasks (see `src/repl/python_tool_repl.py:231`).
- Output is aggressively summarized or replaced with "(ok)" when large, and lists/dicts are summarized by size only, which limits inspection of intermediate results at scale (see `src/repl/python_tool_repl.py:259`).
- The agent policy requires all computed outputs to be registered as strings and substituted into the final answer via placeholders, which adds a brittle step for composite big-data results (see `src/log_agent.py:31` and `src/repl/python_tool_repl.py:42`).
- The ReAct loop in the log agent is capped at 10 iterations, which may be too low for large datasets that need multiple fetch-process-validate cycles (see `src/log_agent.py:64`).

## Reframed diagnosis given “small data” scope
If the primary workload is currently small test data, then the “bad performance” is less about big-data storage/manipulation limits and more about the control-plane around the REPL:
- Observability gap: the run artifact does not record the actual Python snippets executed nor their stdout/stderr, which blocks root-causing why an answer was wrong (tool misuse, import restriction, partial computation, formatting/policy failure, etc.).
- Agent friction: the 30-line limit, restricted imports, and output summarization can still degrade performance even on small data by making it harder for the model to iteratively verify its own intermediate results (see `src/repl/python_tool_repl.py:231` and `src/repl/python_tool_repl.py:259`).
- Output-policy fragility: the “register strings, then use placeholders” requirement introduces an extra correctness axis unrelated to the underlying task, so a model can compute correctly but still score poorly if it forgets registration/placeholder usage (see `src/log_agent.py:31` and `src/repl/python_tool_repl.py:42`).

## Likely contributors to the bad performance (evidence + hypothesis)
Evidence-based:
- The limited data ingestion and lack of streaming mean the REPL never sees the full dataset, so large-file tasks are forced to operate on partial data (see `src/log_agent.py:14`).
- The restricted environment eliminates common data tools (pandas, numpy, os, file I/O), which makes large-scale transformations harder and pushes the model into verbose pure-Python code (see `src/repl/python_tool_repl.py:73` and `tests/test_python_tool_repl.py:46`).
- Output truncation prevents validation or debugging of intermediate transformations, which makes error recovery harder for long pipelines (see `src/repl/python_tool_repl.py:259`).

Hypotheses (need verification):
- The strict register-and-placeholder output policy may cause format errors or incomplete final answers under pressure, reducing evaluation scores even when internal computations were correct (see `src/log_agent.py:31` and `src/repl/python_tool_repl.py:42`).
- The run log does not capture REPL code or outputs, so debugging failure patterns may be blocked by logging gaps rather than purely model behavior (see `src/optimize_agent/runs_docs/20260114_run_33_50.md:875`).

## Would the RLM reference implementation likely do better?
What RLM adds (from the reference docs):
- The RLM design stores the full context as a variable inside the REPL and lets the root LM interact with it without stuffing the entire context into the LM input (see `RecursiveLanguageModels.txt:54` and `RecursiveLanguageModels.txt:56`).
- The REPL can trigger recursive LM calls from within code, enabling partition, grep, and multi-hop sub-queries across large contexts (see `RecursiveLanguageModels.txt:58` and `RecursiveLanguageModels.txt:65`).
- The reference implementation supports multiple REPL environments (local, docker, modal, prime), which could allow larger memory or isolation for bigger datasets (see `github_rlm_ref_impl_code.md:996`).

Assessment:
- For long-context reasoning over large in-memory text corpora, the RLM architecture is a closer fit than the current tool-only REPL, and the RLM results reported in the paper suggest it can outperform non-recursive approaches on large-context tasks (see `RecursiveLanguageModels.txt:18` and `RecursiveLanguageModels.txt:149`).
- Given your current “small test data” focus, RLM-style recursion is unlikely to be the primary missing ingredient. The immediate gap is more plausibly: (1) visibility into what the model executed, and (2) making the REPL loop easy for the model to use correctly.
- For big-data storage and manipulation on local files, RLM will only help if the environment can load the data into the REPL or provide efficient chunked access; otherwise, the same ingestion bottlenecks apply (see `RecursiveLanguageModels.txt:54` and `github_rlm_ref_impl_code.md:983`).
- The RLM docs also acknowledge truncated REPL outputs, so inspection limits may still be present unless output logging is extended (see `RecursiveLanguageModels.txt:64`).

Net: RLM is likely to improve long-context reasoning and recursive querying, but it is not a drop-in fix for large local data manipulation without changes to data access and logging.

## Open questions to validate
- For the current small test-data scope: are evaluation failures due to wrong computations, REPL usage mistakes (imports/line cap), or format/registration errors?
- What minimal “data access” surface do you want next (e.g., chunked reads with offsets, directory listing, globbing), given that the main blocker may be observability rather than raw data size?
