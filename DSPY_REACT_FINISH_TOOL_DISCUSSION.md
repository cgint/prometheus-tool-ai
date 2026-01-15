# Discussion Section

## Q1: Regarding "Signature Mismatch: Tool argument schemas don't align with what LM produces"

Do you think this is coming from the mix of producing Python code and the need to return it within JSON?

Answer: yes, that mix is a common trigger. If the model is asked to emit Python, it often produces raw code or prose, while the tool schema expects strict JSON (with escaped newlines, quotes, and a specific shape), so you get malformed JSON or type mismatches. It is not the only cause though; overly strict schemas, missing in-context examples, and adapter/function-calling mismatches can all produce the same error. A clean fix is to make the code a plain string field with explicit JSON examples or split code generation from tool invocation (generate code in one step, call tools in another).

## Q2: Regarding "Custom Finish Tool":

I still think this is a workaround, a bad one.

Maybe we should just ignore this one as it's only a warning.In the current situation, when Finnish is called with an argument, it doesn't hurt or break.

And a custom finish tool could introduce one more step in the iteration, which is useless.

Answer: if your adapter tolerates extra args on `finish`, you can ignore the warning, but it is brittle: stricter parsers or a different adapter can turn that into a hard failure. The custom finish tool is less about adding a step and more about giving the model a valid place to put the final answer when it wants to "finish." You can still keep iterations minimal by letting it call the custom finish only once at the end. If you want to avoid a custom tool, the alternatives are to (a) allow `finish` and explicitly ignore extra args, (b) adjust parsing to coerce/strip args, or (c) remove the "don't use finish" rule and rely on `max_iters` plus the extract phase.
