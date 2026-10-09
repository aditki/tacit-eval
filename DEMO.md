# Ten-minute demo

## Before the meeting

Open this README, `agent.py`, the three fixture files, and the existing LangSmith dataset/experiment pages in the AWS US workspace. Run the tests and warm the local model with the clear-db command. Check the actual completed rows and scores before choosing an experiment to show. Do not create new scenarios or tune the prompt tonight.

```sh
cd ~/src/tacit-eval
uv run python -m unittest discover -s tests -v
uv run python agent.py --scenario clear_db
```

If credentials are configured, run `EVAL_SPLIT=dev uv run python evaluate.py` ahead of time. Use a completed experiment during the presentation rather than waiting on all three live runs.

## 0:00–1:30 — Problem and boundaries

“I built a small incident investigator for checkout latency. It gathers synthetic service metrics and either identifies an immediate operational bottleneck or abstains. A bottleneck is not necessarily the initiating root cause.”

Show the three candidates and scenarios. State that this is three development cases, not a held-out benchmark. The model chooses which service to inspect; the application injects the fixture context.

## 1:30–4:00 — Graph and evidence integrity

Use the README graph. Show `get_metrics`, `extract_evidence`, the coverage branch, and `normalize_evidence`. Explain that tool-call IDs link observations back to actual tool results. If no tools run, or a dependency is missing, the graph abstains before analysis.

Show the healthy fixture: 145 ms compared with 150 ms is a decrease. Explain the earlier error where the model claimed an increase, and why arithmetic moved into Python. Structured output alone did not protect factual accuracy.

## 4:00–6:00 — One investigation

Run `uv run python agent.py --scenario clear_db` if it was responsive in rehearsal. Show DB latency 2,000 ms versus 40 ms (4,900% increase), 95% CPU, and 98 of 100 connections. Then show the actual returned leading candidate, bottleneck, abstention, and explanation.

Describe the result shown, even if it differs from rehearsal. Explain that schema and candidate validation catch malformed decisions but cannot guarantee correct attribution. Do not claim the deployment caused the DB problem.

## 6:00–8:30 — LangSmith and the useful failure

Open a completed experiment. Show the dev examples, a trace from tool selection through analysis, and the three evaluators. Explain the difference between execution success and matching the expected decision.

Open an ambiguous run that actually demonstrates the failure. The earlier recorded run chose payments-db while the reference requires abstention. It inferred correlation without time-series evidence. If the latest run abstains correctly, show the earlier failure and identify its experiment; do not mislabel it as the latest result.

Do not present 2/3 as a new final score unless the displayed completed experiment verifies it. The evaluators do not directly score explanation accuracy.

## 8:30–10:00 — Lessons and scope

“Structured output enforces form, not truth. Facts need provenance and deterministic comparisons. Evaluation should distinguish a working execution from a justified decision.”

Use `LEARNINGS.md` for the design and evaluation takeaways. If asked for product feedback, use `FRICTION_LOG.md`: the docstring error lacked a specific diagnosis, and regional endpoint setup was easy to miss. Discuss model latency as a runtime lesson. Future work would need temporal evidence and held-out cases to assess causal claims. That is future work, not part of tonight's demo.

## Fallback

- **Local generation takes more than roughly 30 seconds:** stop narrating the wait and move to a completed trace. Cancel the local command if necessary. Do not repeatedly restart it during the meeting.
- **LangSmith is unavailable or credentials are missing:** show the local graph, fixture, tests, evaluator code, and the historical observation below. Say explicitly that the final hosted experiment was not verified.
- **No model or network:** run the offline tests, show the healthy arithmetic and coverage-abstention checks, and explain that these validate deterministic behavior, not model quality.
- **Different model answer:** preserve it. Explain that dev runs can vary and use the observed output to discuss the limitations.

Historical fallback, from the supplied development conversation (not a saved final experiment): healthy → null/abstain; clear_db → payments-db/no abstention; ambiguous → payments-db/no abstention, contrary to its reference. The ambiguous explanation claimed correlation and saturation not established by the supplied snapshot. Use this as a recorded learning example, never as newly measured evidence.

A recorded local fallback is available in `DEMO_RESULTS.json`, which includes its configuration and scope. It reproduces the healthy / clear-db / ambiguous decision pattern above. It is a local model check, not a hosted experiment, and its explanations contain the documented unsupported claims.
