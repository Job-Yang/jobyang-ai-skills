# Style Compass

Turn requirements into an interactive UI/UX prototype and an implementation-ready design specification. The result is more than a polished screenshot: structure, interaction, visual choices, review comments, and final delivery remain connected.

[简体中文](./README.md)

## What it can do

| Stage | Capability |
| --- | --- |
| Structure | Confirm pages, content hierarchy, and navigation with grayscale HTML wireframes |
| Interaction | Build clickable core journeys with default, loading, success, failure, disabled, and recovery states |
| Visual exploration | Generate a small set of materially different high-fidelity directions instead of recoloring one wireframe |
| Review | Experience, explain, comment on, and compare designs in one workbench |
| Coverage protection | Track requirements, pages, journeys, actions, and states through stable `R/P/J/A/S` identifiers |
| Final refinement | Expand the selected direction across all pages, real copy, key states, responsive layouts, and motion |
| Developer handoff | Export specifications and tokens from the final HTML and stage contract |

The workbench supports panning, zooming, page filtering, side-by-side comparison, region comments, resolution state, and stage approval. Comments and decisions are saved to files rather than disappearing with the chat session.

## Why the workflow is staged

People often recognize a good interface but cannot specify one in advance. Asking for a radius, font, or style label too early produces weak design input. Starting with a polished mockup has the opposite problem: color distracts from structural and interaction flaws.

Style Compass separates three decisions:

```text
Structure: what exists and where it lives
Interaction: how the user completes a task and receives feedback
Visual design: how the confirmed content and behavior are expressed
```

Each stage uses rendered screens and working interactions. Structure is still cheap to change before detailed visual work begins. During visual exploration, confirmed task semantics cannot silently disappear.

The `R/P/J/A/S` contract also addresses a common failure in AI redesigns: every redraw can lose a feature or change an outcome. Candidates must cover the required journeys, actions, and states before the user is asked to choose a direction.

## How to ask

> Use style-compass to design this product. I have requirements but no visual reference. Show interactive, high-fidelity directions and refine the selected one.

> Improve this existing interface and flow. Preserve each candidate, selection rationale, and region comment, then deliver the prototype and specification.

Input may be a PRD, a short requirement, an existing product, or code and screenshots.

## How a project moves

```text
Requirements and existing product
→ grayscale structure
→ clickable interaction prototype
→ 2–4 high-fidelity directions, or one clearly defined direction
→ full pages and states in the selected direction
→ runnable prototype, specification, and tokens
```

The four formal stages share the bundled Spatial Studio workbench. The top bar holds stage state, the left side holds project content, the center displays artboards, the right side explains or reviews the selected object, and the bottom dock shows the current pages, journeys, variants, or deliverables.

## Why visual exploration does not start with tokens

An early single-interface comparison used three prompting strategies:

| Strategy | Blind score in that comparison |
| --- | ---: |
| A concrete product direction with freedom to design the whole page | 9.0 |
| A fixed list of color, type, radius, and spacing tokens | 7.5 |
| No visual guidance | 5.0 |

That result motivated a practical change: tokens now record a selected direction and maintain cross-page consistency. Early exploration works at page level, where composition, density, hierarchy, image-text relationships, and motion can be considered together.

This was one interface and one small comparison. It does not prove that naming a reference product universally improves design. The current method treats product names as research leads, not aesthetic formulas. Formal comparisons must freeze inputs, isolate generation and judging, retain failures, and allow the original or a tie to win.

## Deliverables

| Artifact | Purpose |
| --- | --- |
| `prototype/index.html` | Unified review entry and interactive artboards |
| `prototype/index.design.json` | Stage decisions, identifiers, and coverage |
| `prototype/review-framework/` | Bundled workbench CSS and JavaScript |
| `prototype/review-data/comments.json` | Comments tied to pages, modules, and regions |
| `prototype/review-data/workflow.json` | Stage state, selections, and combination decisions |
| Structure, interaction, candidate, and final pages | Inspectable design history |
| `design-spec-<topic>.md` | Developer specification exported from HTML and metadata |

## What is verified

- The workspace validator checks the four stages, side panels, context dock, review modes, and artboard manifest.
- The stage-contract validator checks candidate coverage of journeys, actions, outcomes, states, and final pages.
- Specifications and tokens are exported from final HTML to reduce drift between prototype and documentation.
- These checks establish structural completeness, not aesthetic quality. Final delivery still requires rendered inspection, real interaction, and user approval.

There is not yet a broad benchmark across multiple products and models. The 9.0/7.5/5.0 result explains an earlier design decision; it is not a general performance claim.

## Local start

```bash
python3 scripts/scaffold_review.py ./design-output/prototype
python3 scripts/validate_review_workspace.py ./design-output/prototype/index.html
python3 scripts/review_server.py --root ./design-output/prototype --port 8823
```

Before showing a direction and before final handoff:

```bash
python3 scripts/validate_stage_contract.py --contract ./design-output/prototype/index.design.json --html ./design-output/prototype/index.html --phase direction
python3 scripts/export_spec.py ./design-output/prototype/index.html --meta ./design-output/prototype/index.design.json --topic example-product --producer standalone -o ./design-output/design-spec-example-product.md
```

Copy the complete directory into the host's Skills directory. Python 3.9+ runs the bundled standard-library tools; browser rendering and interaction are required for a completed visual review.
