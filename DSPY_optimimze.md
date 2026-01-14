# DSPy optimization notes (MIPROv2, GEPA, etc.)

This repo already uses **DSPy** to run a modular “online replay” agent with multiple **Signatures** (e.g. `KnowledgeConsolidatorSignature`, `DecisionPlannerSignature`, `ActionSelectorSignature`, `OutcomeEvaluatorSignature`, `EvidencePrefilterSignature`).

The key idea: instead of hand-editing our prompt/rule markdowns (e.g. `STEP_BY_STEP_*.md`), we can **optimize the behavior of individual DSPy modules** using:

- a **trainset** + **dev/val set** derived from our recorded bench runs
- a **metric** per module (or end-to-end)
- a DSPy **optimizer** (“teleprompter”) such as **MIPROv2** or **GEPA**

Official references:
- [DSPy Optimizers overview](https://dspy.ai/learn/optimization/optimizers/)
- [MIPROv2 API docs](https://dspy.ai/api/optimizers/MIPROv2/)
- [GEPA overview](https://dspy.ai/api/optimizers/GEPA/overview/)

---

## Which DSPy optimizers exist? What do they optimize?

DSPy “optimizers” typically tune **prompt instructions** and/or **few-shot demonstrations** for one module or an entire multi-module program.

### Optimizers you’ll most likely use

- **`BootstrapFewShot`**
  - **Optimizes**: *demonstrations* (few-shot examples) via bootstrapping from training examples and “teacher” traces.
  - **When it shines**: small datasets (~10 examples), quick lift via better demos.
  - **Tradeoff**: doesn’t deeply search instruction space; quality depends on metric and teacher behavior.

- **`BootstrapFewShotWithRandomSearch`**
  - **Optimizes**: demos + selection via random search over bootstrapped candidates.
  - **When it shines**: medium datasets (often 50+ examples) where exploring demo subsets matters.
  - **Tradeoff**: more evaluations → more cost/time than `BootstrapFewShot`.

- **`COPRO`** (instruction-focused)
  - **Optimizes**: *natural language instructions* (prompt text) for modules.
  - **When it shines**: you mostly need better instruction wording/constraints, not more demos.
  - **Tradeoff**: limited compared to joint instruction+demos search; depends on metric quality.

- **`MIPROv2`**
  - **Optimizes**: *instructions + few-shot demonstrations jointly* using a more systematic search (including Bayesian optimization style exploration).
  - **When it shines**: you have enough training signal and want a strong “general-purpose” optimizer without going full evolutionary/reflection.
  - **Tradeoff**: can be more expensive than bootstrap methods; with tiny datasets it can overfit—use small budgets and a dev set.

- **`GEPA`** (reflective/evolutionary; usually strongest but slowest)
  - **Optimizes**: primarily *instructions* via iterative reflection + proposal + selection (Pareto-style acceptance).
  - **When it shines**: hard reasoning behaviors and nuanced style/constraints; when you can afford longer runs and want best quality.
  - **Tradeoff**: **time/cost**. “Heavy” settings can take a while; reflection requires extra LM calls.

### Other useful DSPy “optimization-adjacent” tools (often used after/beside optimizers)

- **`dspy.Ensemble`**
  - Use when you have multiple good compiled candidates and want robustness.

- **Finetune/distillation flows** (if you go that direction later)
  - DSPy also supports workflows where you **distill** behavior into smaller models (weight updates), but that’s a separate axis from prompt-only optimization.

---

## Which optimizers suit *us* best?

We’re a great fit for DSPy optimization because our runs already log **per-module inputs/outputs** in `agent_run/steps/step_*/..._input.json` and `..._output.json`.

### Recommended “staged” approach (pragmatic)

- **Stage A (fast, cheap): Bootstrap + COPRO**
  - Start with **`BootstrapFewShot`** or **`BootstrapFewShotWithRandomSearch`** for modules whose outputs are fairly “direct” and benefit from examples.
  - Use **`COPRO`** if the module mainly needs better *instruction phrasing* (constraints, formatting, refusal behavior, etc.).

- **Stage B (strong default): MIPROv2**
  - Use **`MIPROv2(auto="light")`** first to validate the metric + dataset + leakage controls.
  - Then increase budget to **`auto="medium"`** (and optionally more trials) once things look stable.

- **Stage C (best, slowest): GEPA**
  - Reserve **`GEPA(auto="heavy")`** for the *highest-leverage bottleneck module(s)*, typically:
    - `ActionSelectorSignature` (choosing the right next action/command)
    - `OutcomeEvaluatorSignature` (correctly deciding if edits “really applied”, what to verify next)
  - GEPA tends to pay off when you care about **behavioral nuance** more than surface matching.

### Module-by-module vs end-to-end optimization

**Module-by-module** is usually the best starting point for us:
- lower cost (you’re compiling one signature at a time)
- easier debugging (metrics are local and interpretable)

But **end-to-end** can be better once you’re happy with metrics because it captures cross-module interactions. A common flow:
- optimize the weakest module(s) first
- then optimize the whole pipeline end-to-end with a holistic metric

---

## How to extract DSPy eval/train data from our bench run artifacts

### Where the data lives

For SWE-bench runs, we already produce rich step logs like:

`data/swebench_eval/<run_timestamp>/instances/<instance_id>/agent_run/steps/step_XXX/`

Inside each `step_XXX/`, the key files are:

- **Knowledge consolidator**
  - `consolidator_input.json`
  - `consolidator_output.json`

- **Action planning**
  - `decision_planner_output.json` (outputs only)
  - `action_selector_output.json` (outputs only)
  - `action_pack.json` (contains the *effective inputs* used for both planner + selector)

- **Outcome evaluation**
  - `outcome_input.json`
  - `outcome_output.json`

- **Evidence prefilter**
  - `evidence_prefilter_input.json`
  - `evidence_prefilter_output.json`

This structure is created by our agent code (see `bench_agents/online_replay_agent.py`).

### What to turn into “eval examples”

DSPy expects examples shaped like:
- **inputs**: fields matching the signature `InputField`s
- **outputs**: gold labels (the target fields you want the module to produce)

In practice, for our signatures:

- **`KnowledgeConsolidatorSignature`**
  - **inputs**: exactly `consolidator_input.json`
  - **labels**: `consolidator_output.json` (fields map to signature outputs: `state_delta`, `state_updated`, etc.)

- **`EvidencePrefilterSignature`**
  - **inputs**: `evidence_prefilter_input.json`
  - **labels**: `evidence_prefilter_output.json`

- **`OutcomeEvaluatorSignature`**
  - **inputs**: `outcome_input.json`
  - **labels**: `outcome_output.json`

- **`DecisionPlannerSignature`**
  - **inputs**: reconstruct from `action_pack.json`:
    - `goal` ← `GOAL`
    - `observation` ← `OBSERVATION`
    - `state` ← `STATE`
    - `history_events_json` ← `HISTORY_EVENTS`
    - `pinned_findings` ← `PINNED_FINDINGS`
    - `active_rules` ← `ACTIVE_RULES`
    - `phase` ← `phase` (if not present, you can infer from run config; otherwise default)
    - `interaction_mode` ← `interaction_mode` (if not present, infer/default)
  - **labels**: `decision_planner_output.json` (`PLAN_HINT`, `DECISION`)

- **`ActionSelectorSignature`**
  - **inputs**: same mapping from `action_pack.json` as above
  - **labels**: `action_selector_output.json` (`action_type`, `TASK`, `SUCCESS_CRITERIA`, `command`)
  - **note**: `ActionSelectorSignature` also has `command_intent` output; today we don’t persist it in `action_selector_output.json`.
    - Option A: extend logging later (recommended if you want to optimize `command_intent`)
    - Option B: approximate `command_intent` from `action_pack.json`’s `command_intent` (but note it’s post-compile/policy)

### “Correcting” bench-run data so it’s usable as evals (critical)

Bench logs are *model outputs*, not guaranteed “gold”.
You generally want to build eval sets from **high-quality traces** and/or **post-validated outcomes**.

Concrete cleaning/labeling tactics that work well with our artifacts:

- **Filter to high-quality steps**
  - Keep steps where `outcome_output.json.success == "true"` and `issues` is empty.
  - For edit actions, optionally require `needs_verification == "false"` to avoid training on ambiguous outcomes.

- **Avoid learning “policy rewrites” unless you intend to**
  - Our system sometimes rewrites commands (e.g., forced environment probe).
  - If you want to optimize the *LLM decision* rather than the *policy*, train on:
    - `action_selector_output.json.command` (the LLM’s proposed command)
  - If you want to optimize “what actually gets executed”, train on:
    - `action_pack.json.command` (post-policy/compile)
  - Pick one and be consistent for both train and eval.

- **Normalize types**
  - Some fields are serialized as strings like `"true"` / `"false"`. Convert to real booleans for metrics.

- **Control leakage**
  - Split train/dev by **instance id** (not by step) to avoid the same task appearing in both.

- **Human-in-the-loop spot checks**
  - For the first iteration, manually inspect ~20 extracted examples for each module:
    - are the inputs complete?
    - are the labels truly “good behavior”?
    - are we accidentally labeling policy rewrites as “ideal”?

### Suggested extraction format (JSONL)

Create a JSONL where each line is one module example:

```json
{"module":"action_selector","inputs":{...},"labels":{...},"meta":{"run":"20260113_190630","instance":"django__django-10914","step":"step_001"}}
```

This keeps things easy to diff/audit and can later be converted into `dspy.Example` objects.

### Minimal extraction script (sketch)

Below is an intentionally “boring” script outline to build the JSONL.
Because `uv.lock` exists in this repo, run scripts via `uv run python ...`.

```python
import json
from pathlib import Path

ROOT = Path("data/swebench_eval")

def load_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))

def iter_steps(agent_run_dir: Path):
    steps_dir = agent_run_dir / "steps"
    for step_dir in sorted(steps_dir.glob("step_*")):
        yield step_dir

def action_pack_to_selector_inputs(action_pack: dict) -> dict:
    return {
        "goal": action_pack.get("GOAL", ""),
        "observation": action_pack.get("OBSERVATION", ""),
        "state": action_pack.get("STATE", ""),
        "history_events_json": action_pack.get("HISTORY_EVENTS", "[]"),
        "pinned_findings": action_pack.get("PINNED_FINDINGS", ""),
        "active_rules": action_pack.get("ACTIVE_RULES", ""),
        "phase": action_pack.get("phase", "autopilot"),
        "interaction_mode": action_pack.get("interaction_mode", "none"),
    }

def main(out_path: Path):
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", encoding="utf-8") as out:
        for run_dir in sorted(ROOT.glob("*")):
            instances_dir = run_dir / "instances"
            if not instances_dir.exists():
                continue
            for inst_dir in sorted(instances_dir.iterdir()):
                agent_run_dir = inst_dir / "agent_run"
                if not agent_run_dir.exists():
                    continue
                for step_dir in iter_steps(agent_run_dir):
                    # Action selector dataset example
                    ap = load_json(step_dir / "action_pack.json")
                    sel = load_json(step_dir / "action_selector_output.json")
                    ex = {
                        "module": "action_selector",
                        "inputs": action_pack_to_selector_inputs(ap),
                        "labels": {
                            "action_type": sel.get("action_type", ""),
                            "task": sel.get("TASK", ""),
                            "success_criteria": sel.get("SUCCESS_CRITERIA", ""),
                            "command": sel.get("command", ""),
                        },
                        "meta": {
                            "run": run_dir.name,
                            "instance": inst_dir.name,
                            "step": step_dir.name,
                        },
                    }
                    out.write(json.dumps(ex, ensure_ascii=False) + "\n")

if __name__ == "__main__":
    main(Path("data/derived/dspy_evals/action_selector.jsonl"))
```

---

## How to run optimization in our codebase (template)

The exact import paths can differ slightly by DSPy version, but conceptually you:
- build `trainset` / `devset` from JSONL
- wrap the signature in a small `dspy.Module`
- compile with an optimizer
- save the compiled program

Example shape (single-module compile):

```python
import dspy

from online_replay_loop import ActionSelectorSignature

class ActionSelectorModule(dspy.Module):
    def __init__(self):
        super().__init__()
        self.sel = dspy.Predict(ActionSelectorSignature)

    def forward(self, **kwargs):
        return self.sel(**kwargs)

def metric(example, pred, trace=None):
    # Start simple: action_type exact match.
    return float(example.action_type == pred.action_type)

# trainset/devset should be lists of dspy.Example(...).with_inputs(...)
# Then compile:
#
# from dspy.teleprompt import MIPROv2   (or similar, depending on version)
# optimizer = MIPROv2(metric=metric, auto="light")
# compiled = optimizer.compile(ActionSelectorModule(), trainset=trainset, devset=devset, requires_permission_to_run=False)
# compiled.save("compiled_action_selector.json")
```

For GEPA, the pattern is similar, but you’ll usually want a metric that returns more than a brittle exact match (or use an LLM-as-judge metric).

---

## Practical metric suggestions per module (what usually works)

- **Action selector**
  - **must**: `action_type` accuracy
  - **often**: `command` scoring via:
    - normalization (strip, collapse whitespace)
    - “contains expected file path” heuristics
    - optional judge-based comparison (safer for semantically equivalent commands)

- **Outcome evaluator**
  - `success` correctness (especially for edit/verify logic)
  - `needs_verification` correctness when evidence is missing
  - “observation” quality usually needs a judge-based metric (or rubric heuristics)

- **Evidence prefilter**
  - `error_type` accuracy (when present)
  - `error_excerpt` contains at least one key line from stdout/stderr

- **Knowledge consolidator**
  - Usually best with judge-based metrics, or heuristic checks that key facts are preserved and verbosity stays bounded.

---

## Notes / gotchas

- **DSPy settings + concurrency**
  - We already use `dspy.context(...)` patterns in `config.py`. Keep optimizations isolated and avoid reconfiguring globals in parallel threads.

- **Don’t optimize on “garbage labels”**
  - If you compile on failed/low-quality traces, you’ll get “better at being wrong.”
  - Prefer “passed” traces or human-validated slices first.

- **GEPA is great, but budget it**
  - It’s easy to burn time/cost if you start with “heavy” before the metric/dataset are stable.

