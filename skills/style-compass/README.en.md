# Style Compass

Turn requirements into interactive UI/UX prototypes and implementation specifications. Designed for developers who can recognize a good interface but struggle to describe a visual direction. It runs independently of iLoop, Figma, Superdesign, and other design skills.

[简体中文](./README.md)

## Use it

> Use style-compass to design this product. I have requirements but no visual reference. Show interactive, high-fidelity options and refine the selected direction.

> Improve this interface and flow. Keep the candidates, selection reasons, and region comments, then deliver the prototype and specification.

Input can be a PRD, a short requirement, an existing product, or code and screenshots. Without a PRD, the skill establishes the minimum requirements within the current task.

## Design

Confirm structure and interaction semantics, present high-fidelity visual candidates, then finish every page and state in the chosen direction. Grayscale prototypes can support structural exploration; visual decisions require realistic candidates, not recolored wireframes.

Stable `R/P/J/A/S` identifiers track requirements, pages, journeys, actions, and states. Layout and controls may change during visual design; approved functions and outcomes must remain traceable.

Every stage uses the bundled Spatial Studio workbench: stage navigation at the top, project content on the left, designs in the center, explanations and comments on the right, and current objects below. The canvas supports direct panning and side-by-side comparisons.

The model creates the design. Scripts provide the workbench, structural checks, and exports. A generated scaffold is not a finished product.

## Deliverables

| Artifact | Purpose |
| --- | --- |
| `prototype/index.html` | Review entry point and interactive artboards |
| `prototype/index.design.json` | Stage decisions, semantic identifiers, and coverage |
| `prototype/review-framework/` | Bundled workbench CSS and JavaScript |
| `prototype/review-data/comments.json` | Comments tied to pages, modules, and regions |
| `prototype/review-data/workflow.json` | Stage state, selections, and combination decisions |
| Structure, interaction, candidate, and final pages | Inspectable design history |
| `design-spec-<topic>.md` | Specification exported from HTML and stage metadata |

The review server persists comments and selections. Before export, complete page, component, state, interaction, and prototype-index metadata; the exporter cannot infer all business semantics.

## Install and requirements

Copy the complete directory to `~/.trae/skills/style-compass/` or the host's skill directory, including assets, examples, references, and scripts.

Scripts use Python 3.9+ and the standard library. A completed design also requires browser rendering, visual inspection, and interaction checks. External research, font services, and canvases are optional. Bundle distributable resources or disclose remaining network dependencies.

Cloud hosts with Python and a web preview can use the same files. Text-only hosts can deliver drafts and complete code, but must mark runtime verification as pending. Review is incomplete if comments cannot be persisted.

## Local start

Run from the skill directory; `design-output` represents the caller's output location:

```bash
python3 scripts/scaffold_review.py ./design-output/prototype
python3 scripts/validate_review_workspace.py ./design-output/prototype/index.html
python3 scripts/review_server.py --root ./design-output/prototype --port 8823
```

Open `http://127.0.0.1:8823/index.html`. Replace product artboards and the design manifest, keep the shared workbench, and maintain the stage contract.

Check candidate coverage before presentation. For final delivery, replace `direction` with `final` and perform browser verification:

```bash
python3 scripts/validate_stage_contract.py --contract ./design-output/prototype/index.design.json --html ./design-output/prototype/index.html --phase direction
python3 scripts/export_spec.py ./design-output/prototype/index.html --meta ./design-output/prototype/index.design.json --topic example-product --producer standalone -o ./design-output/design-spec-example-product.md
python3 scripts/artifact_io.py pack --input ./design-output/design-spec-example-product.md --attach ./design-output/prototype --out ./design-output/design-result.zip
python3 scripts/artifact_io.py ingest --input ./design-output/design-result.zip --output-root ./received
```

The bundle includes prototypes, candidates, contracts, and saved review data. Import places prototypes under `<topic>/prototype/`; it does not rewrite relative Markdown links. Use the receipt and prototype index to locate files. Structural checks do not replace visual review, interaction tests, or user approval.

## Package and optional integration

[SKILL.md](./SKILL.md) is the agent entry. `references/` covers structure, intake, interaction, visual references, the workbench, stage contracts, and delivery. `scripts/` provides scaffolding, validation, exports, comparison, and the review server. New projects start from the shared workbench under `assets/review-framework/`.

An explicitly active OPC workflow supplies requirements, output locations, and approval rules. Standalone use accepts direct input and does not look up iLoop paths. Outside-view can optionally support decisions that lack external evidence.

The outputs are prototypes and specifications. Production implementation, deployment, and market validation remain separate tasks.
