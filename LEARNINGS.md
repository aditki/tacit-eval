# What I learned

The main design lesson was to separate retrieved facts, deterministic checks, and model interpretation. A well-formed model response can still contain an unsupported conclusion.

## Structured output does not guarantee evidence integrity

An earlier `evidence: list[str]` field in `InvestigationResult` asked Qwen to return supporting evidence. It generated interpretations instead, sometimes with objectively incorrect claims. In the healthy scenario, it described 145 ms p95 latency against a 150 ms baseline as an increase, and an unchanged 0.1% error rate as an increase.

Pydantic enforced the response shape, not factual accuracy. Evidence now comes directly from successful `ToolMessage` JSON, with service identity and tool-call IDs preserved. The model interprets retrieved evidence rather than recreating it. This matters because an unsupported interpretation should never be presented as a retrieved fact.

## The application owns context; the model chooses tools

The model chooses which candidate service to investigate. `ToolRuntime` injects the scenario from application state, so the model cannot select which fixture supplies the evidence.

Earlier tool-call text also showed why a tool-shaped answer is not enough: the integration needs structured tool calls and actual execution through `ToolNode`. Inspecting message types and traces makes that distinction visible.

## Arithmetic belongs in deterministic preprocessing

The model was not a reliable metric comparator. Python now normalizes units and computes baseline deviations: 145 ms versus 150 ms is −3.33%; 0.1% versus 0.1% is unchanged; 2,000 ms versus 40 ms is a 4,900% increase.

These observations retain provenance back to the tool result. They reduce opportunities for numeric mistakes, but do not establish correlation, temporal ordering, or causation.

## Contracts need code, not only field descriptions

A Pydantic validator rejects attribution that contradicts the leading candidate. Python checks candidate membership and derives abstention from a null operational bottleneck. Descriptions alone did not enforce those rules, and valid fields can still accompany contradictory or excessively deliberative explanations.

Coverage is also deterministic: every candidate needs evidence before analysis. Final inspection caught a no-tool-call route that bypassed the gate, plus a missing-evidence message that used set intersection instead of difference. Both were application bugs and were fixed with regression coverage. Incomplete collection now abstains before analysis.

## Execution success and decision quality are separate

The three evaluators check culprit matching, abstention matching, and valid execution output. Failed targets may have missing outputs, so evaluator code must handle that case explicitly. A missing output must not accidentally match a null reference and receive credit.

A completed, valid execution can still make the wrong decision. The ambiguous case demonstrates that distinction. These evaluators do not directly measure numerical accuracy or the factual grounding of an explanation; those require separate inspection.

## A plausible hypothesis is weaker than justified attribution

The ambiguous explanation selected `payments-db`, inferred a dependency-based causal story from snapshots, and treated 72% CPU as saturation. Its reference expects abstention. Even the successful clear-db decision included a correlation claim the snapshot could not establish.

Separating `leading_candidate` from `operational_bottleneck` allows a useful next investigative step without requiring attribution. Deterministic preprocessing improves factual comparisons, but cannot manufacture the temporal or causal evidence needed to distinguish competing explanations.

## Evaluation discipline includes runtime and completion

Qwen3.6's reasoning time made iteration and rehearsal slower. Analysis now uses `reasoning=False`; tool selection retains its original configuration. Runtime is part of demo reliability, alongside answer quality.

Check completed rows and evaluator coverage before interpreting an experiment. Interrupted experiments were raised during development, but no specific interrupted run IDs or verified completion counts were supplied for this write-up. They are a reason to verify completion, not a basis for claiming a failure rate.

Prompts and schemas also changed during the earlier normalization work. Those runs are useful development history, but they do not isolate normalization's effect. The final prompt and three dev fixtures are frozen, and the known ambiguous-case failure is preserved. Three familiar development cases do not establish generalization; a future assessment needs held-out examples and controlled comparisons.

See [FRICTION_LOG.md](FRICTION_LOG.md) for actionable product feedback.
