# Product Brief and Plan

Turn an idea or existing material into a reviewable PRD and delivery plan. Use it to define an MVP, choose a product platform, or organize milestones. iLoop, radar, and scorecard skills are not prerequisites.

[简体中文](./README.md)

## Use it

> Use product-brief to define an MVP and plan for a payment-reminder tool for freelancers. Give each feature a testable acceptance condition and leave unsupported estimates unresolved.

> Write an MVP PRD from these interviews. The platform is already Web; keep that decision.

Inputs can be descriptions, attachments, interviews, existing product material, explicit file paths, or scorecards. Clarify only gaps that change scope, reusing confirmed decisions.

## Design

Define the user's task before proposing features. Stable F identifiers connect each feature to its trigger, expected outcome, and acceptance condition.

The PRD defines product scope; the plan defines delivery. Both reference the same features. Dependencies, parallel work, and join conditions are explicit, while estimates carry evidence and uncertainty.

Recommend a platform when it is undecided; preserve it when the user has chosen. Specialized design or architecture work can consume these outputs later. Completing this skill's work does not require other skills.

## Output

| File | Content |
| --- | --- |
| `prd-<topic>.md` | Problem, audience, journeys, scope, acceptance, platform, metrics, and unresolved decisions |
| `plan-<topic>.md` | Milestones, deliverables, dependencies, parallel work, estimates, resources, and scope changes |

Direct input needs no upstream artifact. Both files share a topic, and the plan may reference the PRD. Unknown gains, schedules, or targets are marked as assumptions or awaiting measurement.

Producing a plan does not automatically start coding or publishing. Existing execution authorization is recorded; the user controls what follows.

## Install and requirements

Copy the entire directory to `~/.trae/skills/product-brief/` or the host's skill directory. Writing requires an agent that can read material and produce text.

Python 3.9+ with the standard library handles envelopes, validation, and bundles. Without Python, deliver complete Markdown and mark machine validation as pending. Without file output, use complete code blocks.

## Transfer

After completing the [PRD](./templates/prd.md) and [plan](./templates/plan.md) bodies, run from the skill directory:

```bash
python3 scripts/artifact_io.py seal --input prd-body.md --node prd --kind prd --topic example-product --producer standalone --out prd-example-product.md
python3 scripts/artifact_io.py seal --input plan-body.md --node prd --kind plan --topic example-product --upstream prd-example-product.md --out plan-example-product.md
python3 scripts/artifact_io.py pack --input prd-example-product.md plan-example-product.md --out product-result.zip
python3 scripts/artifact_io.py ingest --input product-result.zip --output-root ./received
```

The body files contain completed content, not empty templates. In real tasks, use the caller's output directory.

[handoff.md](./references/handoff.md), `scripts/artifact_io.py`, and its bundled rules provide the `opc-artifact/v1` format without requiring OPC. New imports stay pending human review, and conflicting files are not overwritten. Structural validation does not establish product quality or approval.

An explicitly active OPC workflow supplies inputs, output locations, and approval state. Standalone calls complete only the requested work.

[SKILL.md](./SKILL.md) contains the agent workflow. Templates guide writing; scripts handle files and do not make product decisions.
