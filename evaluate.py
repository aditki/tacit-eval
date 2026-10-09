"""Evaluate the existing LangSmith development split; never modifies its examples."""

from typing import Any
import os

from agent import graph, initial_state, InvestigationState, MODEL_NAME, DEV_SCENARIOS
from langsmith import Client


def target(inputs: dict[str, Any]) -> dict[str, Any]:
    state: InvestigationState = {
        **initial_state,
        "scenario_id": inputs["scenario_id"],
        "incident": inputs["incident"],
        "candidates": inputs["candidates"],
        "messages": [],
        "evidence": [],
        "observations": [],
    }
    result = graph.invoke(state)
    return {
        field: result[field]
        for field in (
            "leading_candidate",
            "operational_bottleneck",
            "culprit",
            "reasoning",
            "abstained",
        )
    }


def culprit_correct(
    outputs: dict[str, Any] | None, reference_outputs: dict[str, Any] | None
) -> dict[str, Any]:
    if not isinstance(outputs, dict) or "culprit" not in outputs:
        return {
            "key": "culprit_correct",
            "score": False,
            "comment": "Target produced no culprit field.",
        }
    if not isinstance(reference_outputs, dict) or "culprit" not in reference_outputs:
        return {
            "key": "culprit_correct",
            "score": False,
            "comment": "Reference culprit is missing.",
        }
    return {
        "key": "culprit_correct",
        "score": outputs["culprit"] == reference_outputs["culprit"],
    }


def abstention_correct(
    outputs: dict[str, Any] | None, reference_outputs: dict[str, Any] | None
) -> dict[str, Any]:
    if not isinstance(outputs, dict) or type(outputs.get("abstained")) is not bool:
        return {
            "key": "abstention_correct",
            "score": False,
            "comment": "Target produced no valid abstention decision.",
        }
    if (
        not isinstance(reference_outputs, dict)
        or type(reference_outputs.get("abstained")) is not bool
    ):
        return {
            "key": "abstention_correct",
            "score": False,
            "comment": "Reference abstention decision is missing or invalid.",
        }
    return {
        "key": "abstention_correct",
        "score": outputs["abstained"] == reference_outputs["abstained"],
    }


def execution_success(outputs: dict[str, Any] | None) -> dict[str, Any]:
    if not isinstance(outputs, dict):
        return {"key": "execution_success", "score": False}
    required_fields = {"leading_candidate", "culprit", "reasoning", "abstained"}
    if not required_fields.issubset(outputs):
        return {"key": "execution_success", "score": False}
    valid = (
        type(outputs["abstained"]) is bool
        and isinstance(outputs["reasoning"], str)
        and bool(outputs["reasoning"].strip())
        and all(
            outputs[k] is None or isinstance(outputs[k], str)
            for k in ("leading_candidate", "culprit")
        )
        and outputs["abstained"] == (outputs["culprit"] is None)
        and (
            outputs["culprit"] is None
            or outputs["leading_candidate"] == outputs["culprit"]
        )
        and (
            "operational_bottleneck" not in outputs
            or outputs["operational_bottleneck"] == outputs["culprit"]
        )
    )
    return {"key": "execution_success", "score": bool(valid)}


def main() -> None:
    if not (os.getenv("LANGSMITH_API_KEY") or os.getenv("LANGCHAIN_API_KEY")):
        raise SystemExit(
            "LangSmith API key is missing. Set it in .env or your shell; no experiment was started."
        )
    os.environ.setdefault("LANGSMITH_ENDPOINT", "https://aws.api.smith.langchain.com")
    split = os.getenv("EVAL_SPLIT", "dev")
    if split != "dev":
        raise SystemExit("This frozen demo evaluates the dev split only.")
    client = Client()
    examples = list(
        client.list_examples(dataset_name="incident-investigator-eval", splits=[split])
    )
    if len(examples) != 3 or {
        (e.inputs or {}).get("scenario_id") for e in examples
    } != set(DEV_SCENARIOS):
        raise SystemExit(
            "Expected the existing three dev scenarios; dataset left unchanged."
        )
    results = client.evaluate(
        target,
        data=examples,
        evaluators=[culprit_correct, abstention_correct, execution_success],
        experiment_prefix="final-qwen36-normalized",
        metadata={
            "model": MODEL_NAME,
            "analysis_reasoning": False,
            "temperature": 0,
            "normalized_observations": True,
            "split": split,
        },
        max_concurrency=1,
        blocking=True,
    )
    rows = list(results)
    print(f"Completed rows: {len(rows)}")
    for row in rows:
        scenario = (row["example"].inputs or {}).get("scenario_id")
        scores = {
            item.key: item.score
            for item in row["evaluation_results"].get("results", [])
        }
        print(scenario, scores, "run_failed:", bool(row["run"].error))


if __name__ == "__main__":
    main()
