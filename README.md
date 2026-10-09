# Incident investigator — Tacit take-home

A small LangGraph agent investigates synthetic checkout incidents using local Ollama tool calling. It gathers service metrics, extracts evidence from tool responses, checks coverage, computes baseline comparisons in Python, then asks the model for a leading candidate and an operational bottleneck—or abstention.

The demo is frozen at Qwen3.6 (`qwen3.6:latest`), temperature 0, with `reasoning=False` in analysis. Tool selection retains its existing reasoning configuration. Prompts, the three development fixtures, and reference labels are unchanged. This is a learning exercise with synthetic snapshots, not a production root-cause detector.

## Run locally

Prerequisites: Python 3.12+, uv, and a running Ollama service with enough memory for the installed 23 GB model.

```sh
cd ~/src/tacit-eval
uv sync --locked
ollama pull qwen3.6:latest  # only if not already installed
uv run python agent.py --scenario clear_db
uv run python agent.py    # healthy, clear_db, ambiguous
uv run python -m unittest discover -s tests -v
```

Start Ollama first if it is not running (`ollama serve`, or the Ollama app). The model is already installed on the demo machine. Fixture paths resolve relative to `agent.py`, so invocation from another directory works too. Tests use mocks and require neither Ollama nor LangSmith.

## How the graph works

```text
START → plan → model selects tools
                    ├─ tool calls → execute tools → extract evidence
                    └─ no tool calls ────────────→ extract evidence
                                                     ↓
                                               coverage gate
                                         missing ↙        ↘ complete
                                            abstain       normalize
                                               ↓             ↓
                                              END          analyze → END
```

The model controls which candidate services it investigates. `ToolRuntime` injects the scenario from application state; the model cannot select a fixture through tool arguments. Evidence is parsed from successful `ToolMessage` JSON, tied to the original tool-call ID and candidate service. Missing, empty, or unsuccessful evidence does not satisfy coverage. There is one tool-selection pass; incomplete collection abstains rather than retrying.

Python computes metric deviations and preserves units and provenance. Pydantic rejects inconsistent attribution; Python rejects service names outside the candidates. `abstained` is derived from a null `operational_bottleneck`. The legacy `culprit` field remains an alias for LangSmith compatibility. A leading candidate may be present while the agent abstains from attribution.

## LangSmith evaluation

Use the existing `incident-investigator-eval` dataset and `dev` split. Do not rerun dataset creation or change labels to improve scores. `create_dataset.py` is a read-only inventory helper; importing it does not contact LangSmith.

Copy `.env.example` to `.env` and set your key locally. `.env` is ignored by Git. The AWS US workspace requires `https://aws.api.smith.langchain.com`; see [LangChain's regional endpoint guidance](https://support.langchain.com/articles/6271700631-pointing-the-langsmith-sdk-and-cli-at-a-non-us-regional-endpoint).

```sh
cp .env.example .env  # only when you do not already have a configured .env
# Edit .env locally with your LangSmith key and, if required, workspace ID.
uv run python create_dataset.py
EVAL_SPLIT=dev uv run python evaluate.py
```

The final experiment uses prefix `final-qwen36-normalized`, one concurrent run, three existing examples, and model/configuration metadata. It prints per-scenario scores after completion. No examples or historical experiments are overwritten.

| Evaluator | What it checks |
|---|---|
| `culprit_correct` | Exact match to the reference culprit, including null |
| `abstention_correct` | Boolean abstention matches the reference |
| `execution_success` | Required output fields, types, and decision consistency |

Missing output or missing reference fields return failure scores instead of evaluator exceptions. Target exceptions remain failed runs; they are not converted into apparently successful abstentions. These evaluators do not grade factual accuracy of the explanation or prove causal grounding.

| Existing scenario | Expected culprit | Expected abstention |
|---|---|---|
| healthy | null | true |
| clear_db | payments-db | false |
| ambiguous | null | true |

The earlier conversation recorded correct healthy and clear-db decisions and an overconfident ambiguous attribution (2/3 decision matches). That is a historical observation, not a verified final LangSmith score. The three development examples are too small and too familiar to establish generalization. Temperature 0 does not guarantee identical repeated results.

## Demo material

Read [DEMO.md](DEMO.md) for a ten-minute walkthrough and fallback, [LEARNINGS.md](LEARNINGS.md) for design and evaluation lessons, and [FRICTION_LOG.md](FRICTION_LOG.md) for actionable feedback to the team.
