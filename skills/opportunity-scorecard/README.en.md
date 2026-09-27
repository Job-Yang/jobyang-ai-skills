# Opportunity Scorecard

Assess whether a product idea deserves further validation. Start with a direct idea, research, or a radar candidate. Neither iLoop nor a prior radar scan is required.

[简体中文](./README.md)

## Use it

> Use opportunity-scorecard to assess a tool that turns consultants' client interviews into traceable requirements. Here are the budget and source materials. Gather evidence before scoring, and explain the main risks.

> Evaluate the second candidate in this list before we run a willingness-to-pay experiment. Identify unsupported assumptions.

Useful inputs include the audience, problem, product form, market, revenue model, alternatives, and resource limits. Missing details are clarified only when they affect the assessment.

## Design

The model interprets evidence and assigns dimension scores. Python validates input, computes the weighted result, selects the verdict, and renders the card.

First check whether the default solo-product rubric fits the decision, resources, and success criteria. If material dimensions are irrelevant, deliver a qualitative assessment without a composite score. Do not assign low or neutral scores to inapplicable dimensions or invent weights. Missing evidence for a relevant dimension remains an explicit uncertainty within the original scoring method.

- **Foundation:** contradictory value, impossible prerequisites, or a demonstrably empty market force a reject verdict.
- **Ten dimensions:** pain, proximity to revenue, unit economics, solo delivery, organic distribution, defensibility, market trend, testability, timing, and AI-native fit. Revenue, unit economics, and defensibility have weight 1.5; the others have weight 1.0. Total weight is 11.5.
- **Non-consensus review:** a score below 6.5 can receive a dark-horse flag when both a falsifiable claim and a blind-spot explanation are supplied. A failed foundation cannot receive that flag.

| Score | Verdict |
| --- | --- |
| ≥ 6.5 | validate |
| ≥ 5.0 and < 6.5 | refine |
| ≥ 3.5 and < 5.0 | caution |
| < 3.5 | reject |

This is a default rubric for solo products, not a probability of success. Correct arithmetic cannot establish source truth or replace interviews and payment experiments.

## Output

- `_scoring-<topic>.json`: evidence, dimension scores, foundation assessment, and rebuttal.
- `assess-<topic>.md`: computed result, verdict, flag, evidence, and diagnosis.
- An optional ZIP containing both for transfer.

If the rubric does not apply, or material applicability conditions are unknown, deliver `evaluation-<topic>.md` with evidence, counterevidence, relevant economics, unknowns, a recommended action, and validation conditions. It has no default composite, verdict, or dark-horse fields. Transfer it as an ordinary file; the current numerical-card validator and importer do not accept it. An OPC node requiring a standard card must resolve the mismatch before advancing.

The skill does not automatically write a PRD, discard ideas, or make investment decisions.

## Requirements and runnable example

Python 3.9+ with the standard library computes numerical cards; qualitative assessments do not need the scoring script. Evidence can come from supplied material or host search tools. When the rubric applies but Python is unavailable, deliver complete JSON and qualitative analysis marked as awaiting computation.

Copy the whole directory to `~/.trae/skills/opportunity-scorecard/` or another host's skill directory. Run from that directory:

```bash
python3 scripts/score.py --input examples/scoring.synthetic.json --out assess-synthetic-example.md --producer standalone
python3 scripts/artifact_io.py validate --input assess-synthetic-example.md
python3 scripts/artifact_io.py pack --input assess-synthetic-example.md --scoring examples/scoring.synthetic.json --out scorecard-result.zip
python3 scripts/artifact_io.py ingest --input scorecard-result.zip --output-root ./received
```

The synthetic example gives all dimensions 6.75 and explicitly labels every evidence item as an assumption. It tests computation and transfer only. Real tasks use a task-specific JSON file and an explicit output location. Use `--stdout` instead of `--out` when the host saves the output.

## Package and integration

[SKILL.md](./SKILL.md) defines the workflow and JSON input; [scoring-method.md](./references/scoring-method.md) explains the rubric. `scripts/score.py` owns numeric rules. `scripts/scoring-rules.json` is generated from those rules for the bundled artifact validator.

[handoff.md](./references/handoff.md) and `scripts/artifact_io.py` provide portable transfer. The `opc-artifact/v1` name describes a file format, not an iLoop dependency. Standalone import uses an explicit `--output-root`; new imports remain pending human review and conflicting content is not overwritten.

Only an explicitly active OPC workflow controls input locations, approval, and downstream orchestration.
