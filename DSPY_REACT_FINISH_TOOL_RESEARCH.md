# DSPy ReAct Finish Tool Research

## Research Date

2025-01-14

## Query

Investigation into known issues with DSPy ReAct framework where models try to use the "finish" tool even when told not to, creating "behavioral tension" and parsing errors. Also exploring the recommendation to provide a custom finish tool that accepts the final answer instead of forbidding finish.

---

## Key Findings

### 1. DSPy ReAct Finish Tool Mechanism

**How ReAct Works:**

- `dspy.ReAct` follows the "Reasoning + Acting" pattern: model iteratively decides to call a tool or finish
- DSPy **automatically adds** a special `"finish"` tool to all ReAct instances
- The `finish` tool has no arguments and returns `"Completed."`
- When the agent picks `finish` as `next_tool_name`, it signals completion and the loop terminates
- After finishing (or hitting `max_iters`), DSPy uses an "extract" logic (fallback signature/ChainOfThought) to produce final outputs

**Behavioral Tension:**

- The central decision is: balance between calling additional tools (gathering info) vs deciding you're done
- If agent calls `finish` too early → may miss needed information → wrong answers
- If agent waits too long → wastes resources and may accumulate irrelevant steps
- This tension is inherent to the ReAct pattern

### 2. Custom Finish Tool vs Built-in Finish

**Important Constraint:**

- DSPy's built-in `"finish"` tool is **reserved**
- Custom tools **should NOT** be named `"finish"` - they may be excluded from optimizations (like GEPA) or conflict with built-in behavior
- If you want custom finalization, name it something else (e.g., `finish_custom`)

**Custom Finish Tool Strategy:**

- Instead of forbidding `finish`, provide a custom finish tool that accepts the final answer
- This works **with** the model's biases rather than against them
- The model is strongly biased to use `finish` because the ReAct framework implies its existence
- By providing a custom finish tool that accepts the answer, you align with this bias

### 3. Framework Conflict Issue

**The Problem:**

- Despite being told not to use the finish tool, models frequently try to call it
- This creates "behavioral tension" because:
  - The ReAct framework strongly implies the existence of a finish tool
  - The model sees `finish` in the tool list/prompt
  - Forbidding it creates a conflict between framework expectations and instructions
- This leads to:
  - Parsing errors (model tries to call finish in unexpected ways)
  - Formatting failures (model generates finish calls that don't match expected format)
  - Invalid tool name errors

**Why This Happens:**

- DSPy automatically includes `finish` in the tool list shown to the model
- The ReAct pattern inherently suggests a termination mechanism
- Models are trained on patterns that include finish/stop mechanisms
- Instructions to "not use finish" conflict with framework design

### 4. Solutions and Workarounds

**Recommended Approach: Custom Finish Tool**

1. Create a custom finish tool (e.g., `finish_custom`) that accepts the final answer as a parameter
2. Give it a clear description that guides when to use it
3. Make it semantically meaningful (e.g., "Signal task is complete and provide final answer")
4. Ensure it's appealing in the tool list (good name, clear description)
5. Guide the model via instructions to use the custom finish when ready

**Alternative Strategies:**

1. **Subclass ReAct**: Override the forward method to manage the loop yourself
2. **Modify Instructions**: Adjust signature instructions to guide when finish should be used
3. **Post-process**: Run default ReAct but override when it picks `finish` if conditions aren't met
4. **Adjust max_iters**: Ensure termination mechanism even if finish isn't called

**Considerations:**

- The LLM may still choose built-in `finish` if it thinks it's appropriate
- Must ensure custom finish tool is usable and appealing in tool list
- If disabling `finish`, ensure some termination mechanism exists (max_iters or fallback)
- The extract phase still runs after finishing to produce final output

### 5. Parsing Errors and Framework Conflicts

**Common Error Sources:**

1. **Malformed Output**: LM generates malformed JSON or unexpected tool names
2. **Signature Mismatch**: Tool argument schemas don't align with what LM produces
3. **Finish Tool Issues**: LM doesn't properly output `tool_name="finish"` or gives incompatible args
4. **Adapter Misconfiguration**: Native function calling vs text-based tool-calling conflicts

**Prevention Strategies:**

1. Define signatures and tools very precisely with type hints
2. Provide in-context examples showing expected structure
3. Test tool arguments and names separately before using in ReAct
4. Check adapter/model support for native function calling
5. Monitor and log trajectory outputs to spot parsing issues
6. Adjust `max_iters` and ensure finish is part of tools

### 6. GEPA Optimization Considerations

- GEPA (DSPy's optimizer) **excludes custom tools named `"finish"`** from optimization
- GEPA watches trajectories and sees when agent calls tools (including `finish`)
- It tunes predictor instructions and tool descriptions to encourage correct usage
- Custom tools named `finish` may not benefit from GEPA optimization

---

## Is This a Known Issue?

**Direct GitHub Issues:**

- No exact match found for "finish tool forbidden model tries to call anyway"
- Related issues found about LM configuration and Predict behavior, but not specifically about finish tool conflicts

**However:**

- The behavior is **documented** in DSPy's API documentation
- The framework design inherently includes `finish` as a built-in tool
- The "behavioral tension" is a known aspect of the ReAct pattern
- The recommendation to use custom finish tools (rather than forbidding) aligns with framework design

**Conclusion:**
This appears to be a **known design characteristic** of DSPy ReAct rather than a bug. The framework is designed to always include `finish`, and the recommended approach is to work with this design (custom finish tools) rather than against it (forbidding finish).

---

## References

- DSPy ReAct API Documentation: https://dspy.ai/api/modules/ReAct
- DSPy Tools Documentation: https://dspy.ai/learn/programming/tools/
- DSPy GEPA Optimizer: https://dspy.ai/api/optimizers/GEPA/GEPA_Advanced/
- DSPy.org.cn (Chinese docs): https://dspy.org.cn/api/modules/ReAct/

---

## Recommendations

1. **Don't forbid finish** - Instead, provide a custom finish tool that accepts the final answer
2. **Name custom finish tools differently** - Use `finish_custom`, `complete_task`, etc., not `finish`
3. **Make custom finish semantically meaningful** - Give it a clear description and purpose
4. **Guide the model via instructions** - Tell it when to use the custom finish tool
5. **Monitor trajectories** - Log and inspect tool calls to understand model behavior
6. **Work with framework design** - Align with ReAct's built-in patterns rather than fighting them
