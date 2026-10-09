import json
import os
from pathlib import Path
from dotenv import load_dotenv
from langgraph.graph import StateGraph, START, END
from langgraph.graph.message import add_messages
from langgraph.prebuilt import ToolNode
from langchain_core.messages import HumanMessage, ToolMessage, AIMessage
from langchain_ollama import ChatOllama
from langchain.tools import ToolRuntime, tool

from typing import Annotated, TypedDict, Any, Self
from pydantic import BaseModel, Field, model_validator

ROOT = Path(__file__).resolve().parent
load_dotenv(ROOT / ".env")
DEV_SCENARIOS = ("healthy", "clear_db", "ambiguous")

MODEL_NAME = os.getenv(
    "INVESTIGATOR_MODEL",
    "qwen3.6:latest",
)


class Evidence(BaseModel):
    service: str
    metrics: dict[str, Any]
    tool_call_id: str


class Observation(BaseModel):
    service: str
    metric: str
    observed: float
    baseline: float
    deviation_pct: float
    direction: str
    tool_call_id: str
    unit: str


class InvestigationState(TypedDict):
    """Description."""

    incident: str
    candidates: list[str]
    investigation_plan: list[str]
    evidence: list[Evidence]
    culprit: str | None
    operational_bottleneck: str | None
    leading_candidate: str | None
    observations: list[Observation]
    reasoning: str | None
    abstained: bool | None
    messages: Annotated[list, add_messages]
    scenario_id: str


class InvestigationResult(BaseModel):
    leading_candidate: str | None = Field(
        description=(
            "The strongest hypothesis worth investigating next. "
            "May be populated even when abstaining. "
            "Must be None when no candidate has meaningful supporting evidence."
        )
    )

    operational_bottleneck: str | None = Field(
        description=(
            "The service most strongly supported by evidence as the immediate "
            "operational bottleneck constraining system performance. "
            "Multiple corroborating signals, such as resource saturation and "
            "degraded latency, can justify identifying a bottleneck. "
            "Identifying a bottleneck does not require knowing what caused "
            "the degradation. "
            "Set to None when the evidence cannot distinguish a specific "
            "operational bottleneck from competing candidates."
        )
    )

    reasoning: str = Field(
        description=(
            "Explain the observed evidence, competing explanations, "
            "and why attribution is or is not justified."
        )
    )

    @model_validator(mode="after")
    def validate_attribution(self) -> Self:
        if (
            self.operational_bottleneck is not None
            and self.leading_candidate != self.operational_bottleneck
        ):
            raise ValueError("An attributed culprit must match the leading candidate")

        return self


initial_state: InvestigationState = {
    "incident": "Checkout requests became slow immediately after a deployment.",
    "candidates": [
        "checkout-api",
        "payments-db",
        "redis",
    ],
    "investigation_plan": [],
    "evidence": [],
    "culprit": None,
    "operational_bottleneck": None,
    "leading_candidate": None,
    "observations": [],
    "reasoning": None,
    "abstained": None,
    "messages": [],
    "scenario_id": "",
}


def plan_investigation(
    state: InvestigationState,
) -> dict:
    plan_steps = []

    for candidate in state["candidates"]:
        plan_steps.append(f"check metrics for {candidate}")

    return {"investigation_plan": plan_steps}


@tool(parse_docstring=True)
def get_metrics(service: str, runtime: ToolRuntime) -> dict:
    """Retrieve operational metrics for a candidate service during an incident investigation.

    Args:
        service (str): The name of the candidate service

    Returns:
        dict: A dictionary containing operational metrics for the specified service
    """

    scenario = runtime.state.get("scenario_id")
    if not scenario:
        raise ValueError("scenario_id missing from investigation state")
    if scenario not in DEV_SCENARIOS:
        raise ValueError("Unknown development scenario")
    with (ROOT / "data" / f"{scenario}.json").open() as f:
        data = json.load(f)
        return data.get(service, {})


def agent_node(
    state: InvestigationState,
) -> dict:

    model = ChatOllama(
        model=MODEL_NAME,
        temperature=0,
    )
    model_with_tools = model.bind_tools([get_metrics])

    prompt = [HumanMessage(f"""
    Incident:
    {state["incident"]}

    Candidates:
    {state["candidates"]}

    Investigation plan:
    {state["investigation_plan"]}

    Use the available tools to gather the evidence required by the investigation plan.
    """)]

    response = model_with_tools.invoke(prompt)

    return {"messages": prompt + [response]}


def route_after_agent(state: InvestigationState) -> str:
    last_message = state["messages"][-1]

    if getattr(last_message, "tool_calls", None):
        return "tool_node"

    return "evidence_node"


def extract_evidence(state: InvestigationState) -> dict:
    evidence_list = []

    tool_map = {}

    for message in state["messages"]:
        if isinstance(message, AIMessage):
            for tool_call in message.tool_calls:
                if (tool_call.get("name") == "get_metrics"
                    and tool_call.get("args", {}).get("service") in state["candidates"]):
                    tool_map[tool_call["id"]] = tool_call["args"]["service"]

        if isinstance(message, ToolMessage):
            # Extract the actual tool result

            if message.status == "error":
                continue
            if message.tool_call_id is None:
                raise ValueError("ToolMessage is missing tool_call_id")
            service = tool_map.get(message.tool_call_id)
            if service is None:
                continue
            if not isinstance(message.content, str):
                raise TypeError(
                    f"Expected string tool output, got {type(message.content).__name__}"
                )

            try:
                metrics = json.loads(message.content)
            except json.JSONDecodeError:
                continue

            if not isinstance(metrics, dict) or not metrics:
                continue

            evidence = Evidence(
                service=service,
                metrics=metrics,
                tool_call_id=message.tool_call_id,
            )
            evidence_list.append(evidence)

    return {"evidence": evidence_list}


def has_complete_evidence(state: InvestigationState) -> bool:
    required = set(state["candidates"])

    collected = {evidence.service for evidence in state["evidence"] if evidence.metrics}

    return required <= collected


def calculate_deviation(observed: float, baseline: float) -> float:
    if baseline == 0:
        raise ValueError("Cannot calculate percentage deviation from zero baseline")

    return round((observed - baseline) / baseline * 100, 2)


def get_direction(deviation_pct: float) -> str:
    if deviation_pct > 0:
        return "increased"
    if deviation_pct < 0:
        return "decreased"
    return "unchanged"


def normalize_evidence(state: InvestigationState) -> dict:
    observations = []

    for evidence in state["evidence"]:
        metrics = evidence.metrics

        for key, baseline_value in metrics.items():
            # Identify baseline metrics
            # Find corresponding observed metrics
            if key.startswith("baseline_"):
                current_metric = key.removeprefix("baseline_")
                observed_value = metrics.get(current_metric)

                if observed_value is None:
                    raise ValueError(
                        f"Missing observed metric {current_metric} for {evidence.service}"
                    )

                observed_number, observed_unit = normalize_unit(
                    *parse_metric_value(observed_value)
                )

                baseline_number, baseline_unit = normalize_unit(
                    *parse_metric_value(baseline_value)
                )

                if observed_unit != baseline_unit:
                    raise ValueError(
                        f"Incompatible units for {current_metric}: "
                        f"{observed_unit} vs {baseline_unit}"
                    )

                deviation = calculate_deviation(
                    observed_number,
                    baseline_number,
                )

                direction = get_direction(deviation)

                observation = Observation(
                    service=evidence.service,
                    metric=current_metric,
                    observed=observed_number,
                    baseline=baseline_number,
                    unit=observed_unit,
                    deviation_pct=deviation,
                    direction=direction,
                    tool_call_id=evidence.tool_call_id,
                )
                observations.append(observation)

    return {"observations": observations}


def parse_metric_value(value: str) -> tuple[float, str]:
    value = value.strip()
    if value.endswith("ms"):
        return (float(value.removesuffix("ms")), "ms")
    elif value.endswith("%"):
        return (float(value.removesuffix("%")), "%")
    elif value.endswith("s"):
        return (float(value.removesuffix("s")), "s")
    else:
        raise ValueError(f"Unsupported metric unit: {value}")


def normalize_unit(value: float, unit: str) -> tuple[float, str]:
    if unit == "s":
        return (value * 1000, "ms")
    if unit in ("ms", "%"):
        return (value, unit)
    raise ValueError(f"Unsupported unit: {unit}")


def abstain_node(state: InvestigationState) -> dict:
    required = set(state["candidates"])

    collected = {evidence.service for evidence in state["evidence"] if evidence.metrics}

    return {
        "culprit": None,
        "operational_bottleneck": None,
        "leading_candidate": None,
        "reasoning": f"Insufficient evidence to complete the investigation. Missing evidence for: {sorted(required - collected)}.",
        "abstained": True,
    }


def analyze_evidence(
    state: InvestigationState,
) -> dict:

    model = ChatOllama(
        model=MODEL_NAME,
        temperature=0,
        reasoning=False,
    )
    model_with_structured_output = model.with_structured_output(InvestigationResult)

    observations_json = json.dumps(
        [observation.model_dump() for observation in state["observations"]],
        indent=2,
    )

    messages = state["messages"] + [HumanMessage(content=f"""
        Normalized operational observations:
        {observations_json}

        Analyze the gathered operational evidence using both the
        original tool results and the normalized observations.

        Treat normalized observations as authoritative for numerical
        comparisons against baselines.

        Distinguish between:
        1. Observed service degradation.
        2. The leading hypothesis explaining the incident.
        3. Evidence sufficient to identify an immediate operational bottleneck.

        An operational bottleneck is a component whose resource saturation
        or degraded performance is constraining the system. Identifying
        that bottleneck does not establish what initiated the degradation.

        Identify a leading candidate when evidence supports investigating
        one candidate before others.

        A leading candidate does not automatically justify bottleneck
        attribution.

        Multiple corroborating signs of resource saturation may justify
        identifying an operational bottleneck even when its initiating
        cause remains unknown.

        If competing explanations remain plausible and the evidence
        cannot distinguish a specific bottleneck, abstain from attribution.

        Do not infer temporal ordering, correlation, or causation from
        metric snapshots alone.

        If no candidate has meaningful supporting evidence,
        set leading_candidate to None.

        Provide a concise explanation based only on observed evidence.
        """)]

    response = model_with_structured_output.invoke(messages)

    if not isinstance(response, InvestigationResult):
        raise TypeError(f"Expected InvestigationResult, got {type(response).__name__}")

    for service in (response.leading_candidate, response.operational_bottleneck):
        if service is not None and service not in state["candidates"]:
            raise ValueError("Analysis returned a service outside the candidate set")

    return {
        "operational_bottleneck": response.operational_bottleneck,
        "culprit": response.operational_bottleneck,
        "leading_candidate": response.leading_candidate,
        "reasoning": response.reasoning,
        "abstained": response.operational_bottleneck is None,
    }


tools = [get_metrics]
tool_node = ToolNode(tools, handle_tool_errors=True)
builder = StateGraph(InvestigationState)
builder.add_edge(START, "plan_investigation")
builder.add_node("plan_investigation", plan_investigation)
builder.add_edge("plan_investigation", "agent_node")
builder.add_node("agent_node", agent_node)
builder.add_conditional_edges(
    "agent_node",
    route_after_agent,
    {
        "tool_node": "tool_node",
        "evidence_node": "evidence_node",
    },
)
builder.add_node("tool_node", tool_node)
builder.add_edge("tool_node", "evidence_node")
builder.add_node("evidence_node", extract_evidence)
builder.add_conditional_edges(
    "evidence_node",
    has_complete_evidence,
    {
        True: "normalize_node",
        False: "abstain_node",
    },
)
builder.add_node("abstain_node", abstain_node)
builder.add_edge("abstain_node", END)
builder.add_node("normalize_node", normalize_evidence)
builder.add_edge("normalize_node", "analysis_node")
builder.add_node("analysis_node", analyze_evidence)
builder.add_edge("analysis_node", END)


graph = builder.compile()


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description="Investigate synthetic checkout incidents")
    parser.add_argument("--scenario", choices=DEV_SCENARIOS, help="Omit to run all three")
    args = parser.parse_args()
    for scenario in [args.scenario] if args.scenario else DEV_SCENARIOS:
        print(f"\nScenario: {scenario}", flush=True)
        state: InvestigationState = {**initial_state, "scenario_id": scenario, "messages": []}
        result = graph.invoke(state)
        for field in ("leading_candidate", "operational_bottleneck", "abstained", "reasoning"):
            print(f"{field}: {result[field]}", flush=True)


if __name__ == "__main__":
    main()
