# Product Brief and Plan

Turn a short requirement, interview set, existing product material, or prior assessment into a reviewable PRD and a delivery plan that design and engineering can continue from.

[简体中文](./README.md)

## What it can do

| Capability | Result |
| --- | --- |
| Define the problem | Identify the audience, situation, current workaround, and desired change |
| Bound the MVP | Give every feature a stable identifier, trigger, outcome, and acceptance condition |
| Protect scope | Separate confirmed decisions, proposals, assumptions, unresolved items, and exclusions |
| Handle platform choices | Compare trade-offs when open and preserve decisions already made |
| Specify edges | Cover required fields, formats, units, precision, boundaries, invalid input, and failure recovery |
| Build a delivery plan | Define milestones, dependencies, parallel work, join conditions, deliverables, and ownership |
| Calibrate estimates | Preserve uncertainty and avoid invented schedules |
| Keep PRD and plan aligned | Every planned task must trace back to a product requirement |

## Why PRD and plan are produced together

Many PRDs list features without observable outcomes. Many plans list tasks without explaining which requirement each task delivers. When the two are generated separately, design invents one scope, engineering implements another, and QA has no stable acceptance rule.

Stable feature identifiers connect both files. The PRD owns user outcomes and scope. The plan owns dependency order, parallel work, and completion evidence. Unsupported schedules, gains, metrics, and platform assumptions remain unresolved rather than becoming precise-looking promises.

## How to ask

> Define an MVP and plan for a payment-reminder tool for freelancers. Give every feature a testable acceptance condition and leave unsupported estimates unresolved.

> Write an MVP PRD from these interviews. The platform is already Web; preserve that decision.

Inputs may be descriptions, attachments, interviews, product material, explicit paths, or an earlier assessment.

## Workflow

```text
Read requirements and prior decisions
→ define the user problem and success criteria
→ narrow the core journey and MVP
→ write testable acceptance for each feature
→ confirm platform and input boundaries
→ organize milestones, dependencies, and parallel work
→ verify that PRD and plan still match
→ deliver for review
```

## Output

| File | Content |
| --- | --- |
| `prd-<topic>.md` | Problem, audience, journeys, scope, acceptance, platform, metrics, and unresolved decisions |
| `plan-<topic>.md` | Milestones, deliverables, dependencies, parallel work, estimates, resources, and scope changes |

Unknown gains, schedules, and targets are marked as assumptions or awaiting measurement. Producing a plan does not authorize coding or publishing.

## Evaluation evidence

Six same-host comparisons were run:

| Stage | Result |
| --- | --- |
| Four development cases | No-skill baseline 19.625, initial skill 19.875 |
| After targeted revision | Initial skill 19.875, revised skill 20.000 |
| Two holdout cases | Baseline, initial, and revised versions all scored 20.000 |

The targeted revision addressed two recurring gaps:

- units, precision, boundary values, and invalid input for fields such as money and time;
- shared examples, interface semantics, and join conditions when design, frontend, and backend work can proceed in parallel.

All holdout outputs tied. The method can repair explicit omissions, but it does not consistently outperform a strong model on already well-specified tasks. The evaluation was small, mostly simulated, and near the scoring ceiling. It also says nothing about whether the underlying product is worth building.

## Install and transfer

Copy the complete directory into the host's Skills directory. Python 3.9+ provides standard-library sealing, validation, and bundling:

```bash
python3 scripts/artifact_io.py seal --input prd-body.md --node prd --kind prd --topic example-product --producer standalone --out prd-example-product.md
python3 scripts/artifact_io.py seal --input plan-body.md --node prd --kind plan --topic example-product --upstream prd-example-product.md --out plan-example-product.md
python3 scripts/artifact_io.py pack --input prd-example-product.md plan-example-product.md --out product-result.zip
```

[PRD](./templates/prd.md) and [plan](./templates/plan.md) templates provide the body structure. File validation does not establish product quality or approval.
