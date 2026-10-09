from langsmith import Client
from langsmith.utils import LangSmithNotFoundError

from agent import ROOT  # Loads the repository .env without running an investigation.


def main() -> None:
    client = Client()

    examples = list(
        client.list_examples(
            dataset_name="incident-investigator-eval",
            splits=["dev"],
        )
    )

    print("Dev examples:", len(examples))

    for example in examples:
        if example.inputs:
            print(example.inputs["scenario_id"])



if __name__ == "__main__":
    main()

# dataset = client.create_dataset(
#     dataset_name="incident-investigator-eval",
#     description=(
#         "Synthetic operational incidents for evaluating "
#         "culprit identification and abstention."
#     ),
# )

# dataset = client.read_dataset(dataset_name="incident-investigator-eval")

# examples = [
#     {
#         "inputs": {
#             "scenario_id": "clear_db",
#             "incident": "Checkout requests became slow immediately after a deployment.",
#             "candidates": ["checkout-api", "payments-db", "redis"],
#         },
#         "outputs": {
#             "culprit": "payments-db",
#             "abstained": False,
#         },
#     },
#     {
#         "inputs": {
#             "scenario_id": "ambiguous",
#             "incident": "Checkout requests are experiencing elevated latency and errors.",
#             "candidates": ["checkout-api", "payments-db", "redis"],
#         },
#         "outputs": {
#             "culprit": None,
#             "abstained": True,
#         },
#     },
#     {
#         "inputs": {
#             "scenario_id": "healthy",
#             "incident": "Investigate the current health of the checkout service and its dependencies.",
#             "candidates": ["checkout-api", "payments-db", "redis"],
#         },
#         "outputs": {
#             "culprit": None,
#             "abstained": True,
#         },
#     },
# ]


# existing_examples = client.list_examples(dataset_id=dataset.id)

# existing_scenarios = {
#     example.inputs.get("scenario_id")
#     for example in existing_examples
#     if example.inputs is not None
# }


# for example in examples:
#     scenario_id = example["inputs"]["scenario_id"]

#     if scenario_id not in existing_scenarios:
#         client.create_example(
#             dataset_id=dataset.id,
#             inputs=example["inputs"],
#             outputs=example["outputs"],
#         )

# print(dataset.id)
