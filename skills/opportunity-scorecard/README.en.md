# Opportunity Scorecard

Turn a product idea, existing research, or a candidate lead into a traceable investment recommendation: gather more evidence, run a bounded test, invest further, or stop.

[简体中文](./README.md)

## What it can do

- Reject internally contradictory ideas, impossible prerequisites, or demonstrably empty markets.
- Check whether the default ten-dimension rubric fits the actual decision.
- Gather evidence for pain, revenue proximity, unit economics, delivery, distribution, defensibility, trend, testability, timing, and AI fit.
- Separate stated interest, free trials, payment, and renewal.
- Recalculate costs and sensitivity, including heavy-user losses hidden by averages.
- Name the payment, cost, usage, or technical evidence that would change the recommendation.
- Preserve a falsifiable non-consensus argument without allowing it to override a failed foundation.
- Switch to a qualitative assessment when a numeric rubric would distort the decision.

## Why reasoning and calculation are separated

Evidence quality, rubric applicability, and uncertainty require contextual judgment. Weights, thresholds, composite scores, and verdict labels should remain deterministic and reproducible.

```text
Model: applicability, evidence, dimension rationale, counterargument
Script: schema validation, weighted calculation, verdict rendering
```

An all-model workflow can drift between runs. An all-spreadsheet workflow forces irrelevant dimensions onto every decision. The two-stage design keeps contextual judgment flexible while making arithmetic stable.

The score is a compressed view of current evidence, not the first line of the answer. Delivery starts with the next action, what should remain paused, and what evidence would change the recommendation.

## How to ask

> Assess a tool that turns consultants' interviews into traceable requirements. Here are the budget and source materials. Gather evidence before scoring and explain the main risks.

> Evaluate the second candidate before a willingness-to-pay test. Identify unsupported assumptions.

Useful input includes the audience, problem, product form, market, revenue model, alternatives, and resource limits.

## Workflow

```text
Define the decision
→ check rubric applicability
→ test the foundation
→ gather evidence for relevant dimensions
→ calculate unit economics and sensitivity
→ record a non-consensus case
→ render the card with the script
→ propose the smallest test and stopping conditions
```

When the default solo-product rubric applies:

| Score | Verdict |
| --- | --- |
| ≥ 6.5 | validate |
| ≥ 5.0 and < 6.5 | refine |
| ≥ 3.5 and < 5.0 | caution |
| < 3.5 | reject |

Revenue proximity, unit economics, and defensibility have weight 1.5; the other seven dimensions have weight 1.0. A failed foundation overrides the composite.

When material dimensions do not fit the decision, the skill produces `evaluation-<topic>.md` without a composite, verdict, or dark-horse flag.

## Output

- `_scoring-<topic>.json`: evidence, scores, foundation result, and non-consensus argument.
- `assess-<topic>.md`: computed score, verdict, evidence, diagnosis, and next action.
- `evaluation-<topic>.md`: qualitative assessment when the rubric does not apply.
- An optional ZIP containing the card and source scoring data.

## Evaluation evidence

The most important observed defect was rubric applicability. Earlier versions continued to include solo-delivery and AI-fit scores in organizational decisions even after adding a disclaimer.

After introducing an applicability branch:

| Comparison stage | Previous version | Current version |
| --- | ---: | ---: |
| Four targeted development cases | 19.50 / 20 | 20.00 / 20 |
| Two targeted holdout cases | 18.75 / 20 | 20.00 / 20 |
| Two independent reserve cases | 19.50 / 20 | 19.75 / 20 |

The revised method more clearly required actual renewals, controlled familiarity effects in time comparisons, compared like-for-like workloads, and exited the solo-product composite for organizational decisions.

The reserve cases did not establish a stable single winner. The evidence supports correction of a known bias, not universal superiority. The larger product-skill evaluation covered 20 cases, 60 outputs, and 34 comparisons, mostly with simulated material and near-ceiling scores.

## Runnable example

```bash
python3 scripts/score.py --input examples/scoring.synthetic.json --out assess-synthetic-example.md --producer standalone
python3 scripts/artifact_io.py validate --input assess-synthetic-example.md
python3 scripts/artifact_io.py pack --input assess-synthetic-example.md --scoring examples/scoring.synthetic.json --out scorecard-result.zip
```

The bundled synthetic example scores every dimension at 6.75 and labels its evidence as assumptions. It validates calculation and transfer only.

Copy the complete directory into the host's Skills directory. Numeric cards require Python 3.9+ and the standard library. Structural and arithmetic validation do not establish evidence truth or product success.
