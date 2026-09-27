# Engineering Documentation

> One entry point for context gathering, technical decisions, collaborative drafting, diagrams, and reader validation.

[简体中文](./README.md)

## What It Solves

AI can produce a well-structured technical document while still identifying the wrong system path, missing a critical constraint, or presenting an assumption as a fact.

This skill builds the evidence and decision first, then writes the document. It supports:

- Technical designs and system designs.
- RFCs and architecture decisions.
- Refactoring, migration, and performance proposals.
- Cross-system API, data, and workflow changes.
- Direct drafting from available context or iterative co-authoring with the user.
- Revising engineering decisions when new evidence appears, and reviewing existing proposals.
- Adapting a common decision model to team templates.

It does not own copy-editing, tutorials, operating guides, exhaustive API references, technical explainers, opinion pieces, or speculative essays.

Context gathering, iterative refinement, and independent reader testing are part of this skill. It drafts directly when context is sufficient and switches to collaboration only when key uncertainty or user intent requires it.

The internal decision model is separate from the reader-facing document. Evidence ledgers and G0-G12 gates stay internal by default. The final structure follows the reader's actual questions; goals, boundaries, and option comparisons appear only when they help the decision.

Diagrams are selected by question rather than quota. When boundaries, structure, runtime order, state, data relationships, or schedules are hard to understand in prose, the skill chooses an appropriate view and requires editable source, a real render, and consistency with the document.

## Visual Coverage

[Browse 21 reusable examples and editable sources](assets/visual-examples/README.md). Twelve cover technical views: context, container, component, deployment, flowchart, swimlane, sequence, state, data flow, ER, Gantt, and milestones. Nine cover quantitative views: trend, dumbbell comparison, histogram, ECDF, box plot, scatter, heatmap, stacked composition, and waterfall.

[Browse 26 additional templates](assets/diagram-templates/README.md): layered system architecture, grouped grids, organization and hierarchy trees, mind maps, horizontal and vertical timelines, stage milestones, cycles and flywheels, pyramids, brand houses, matrices, quadrants and bubbles, release trains, development workflows, both swimlane orientations, pie/donut/funnel/radar charts, business canvases, and overlapping or nested sets. These use 20 bounded layout interfaces. The complete collection has 47 synthetic examples with editable SVG and 680px PNG previews.

All renderers share a pastel theme inspired by the Feishu whiteboard classic palette: light grouping areas, white inner entities, dark text, and thin gray relationships. Quantitative marks retain contrast. This is the skill's theme, not a claim to reproduce every Feishu template or editing behavior.

All examples are synthetic. Type-specific recipes cover layout and semantics; visual guidance covers hierarchy, focus, color, labels, and readability. Quantitative charts preserve data, units, scales, and reproducible calculations. BPMN/DMN guidance does not provide an execution engine. Specialized views such as flame graphs require real measurements and suitable tools. Curated examples do not certify arbitrary inputs or platform imports.

Visual revisions preserve a baseline and improve grouping, label placement, and reading order. The optional [comparison method](references/visual-evaluation.md) uses anonymous, equal-size pairs and separates factual correctness, reading-task answers, and visual preference. Ties and regressions remain in the results.

## Platform Independence

The default deliverable is portable Markdown with editable diagram sources and rendered previews. Feishu, MindAI, iLoop, OPC, and other drawing skills are optional. The optional validation tools use Python 3.9+ and its standard library. Reproducing the statistical examples additionally uses Matplotlib and NumPy; these are not dependencies of the skill instructions or existing SVG sources. Visual acceptance requires a renderer and the ability to inspect its output; without them, the document must state that visual verification is pending.

Process modeling distinguishes conditional branches, parallel joins, event races, bounded retries, and terminal outcomes before layout. It selects flowcharts, swimlanes, BPMN, sequence diagrams, state diagrams, or decision tables by the reader's question. Layout must preserve the control semantics.

Body diagrams, zoomable boards, slides, and print output have separate acceptance sizes. Online publishing is a separate adapter step. Relative links, self-contained SVG/PNG previews, and editable sources support offline reading; equivalent output on every host still requires verification.

## Use it

> Use engineering-docs to write a migration proposal from this code and runtime evidence. Explain the decision, affected systems, validation, and rollback.

> Update the existing design for this API change. Read the full document and diagrams first, preserving decisions that still hold.

Provide source material and the decision the reader needs to make; a prior PRD is not required. Ordinary tasks deliver the document and necessary diagram sources and previews. Strict mode adds structured records. Use the caller's output directory or the host's attachment area.

## Decision Flow

```text
context and reader action
→ evidence and current state
→ problem
→ goals and boundaries
→ constraints
→ candidate options
→ decision and accepted costs
→ implementation design
→ impact and risks
→ validation, rollout, and rollback
→ open questions
```

The skill keeps facts, inferences, assumptions, decisions, and open questions distinct. Missing critical evidence blocks an implementable result. A high-risk proposal without validation, detection, or mitigation remains a draft.

Full gates and structured records belong to strict mode. Ordinary technical documents do not need JSON setup or G0-G12 validation by default.

## Structure

```text
engineering-docs/
├── SKILL.md
├── README.md
├── README.en.md
├── references/
│   ├── decision-model.md
│   ├── collaboration-workflow.md
│   ├── diagram-guidance.md
│   ├── diagram-recipes.md
│   ├── visual-design.md
│   ├── visual-evaluation.md
│   ├── data-charts.md
│   ├── diagram-sources.md
│   ├── process-modeling.md
│   ├── portable-delivery.md
│   ├── handoff.md
│   ├── quality-gates.md
│   └── template-adaptation.md
├── assets/visual-examples/
│   ├── README.md
│   ├── render_diagrams.py
│   ├── render_charts.py
│   ├── plan.json
│   ├── chart-data.json
│   ├── theme.json
│   └── gallery/             # Editable SVG and body-size PNG
├── assets/diagram-templates/
│   ├── README.md            # Selection, input schema, and limits
│   ├── examples.json
│   └── gallery/
├── templates/
│   ├── decision-record.json
│   └── engineering-doc.md
├── scripts/
│   ├── engineering_docs.py
│   ├── artifact_io.py
│   ├── render_templates.py
│   └── scoring-rules.json
└── tests/
    ├── test_engineering_docs.py
    └── test_render_templates.py
```

## Strict Mode

Initialize a structured workspace only when lifecycle state, machine validation, or an audit trail is required.

### Initialize a Workspace

```bash
python3 scripts/engineering_docs.py init \
  --title "Session Storage Migration" \
  --author "Author" \
  --type technical-design \
  --output /tmp/session-storage-design
```

The command creates:

- `document.md` for human review.
- `decision-record.json` for evidence, decisions, risks, gates, and lifecycle state.

### Validate

Validate the current state:

```bash
python3 scripts/engineering_docs.py validate \
  --record /tmp/session-storage-design/decision-record.json
```

Check readiness for implementation:

```bash
python3 scripts/engineering_docs.py validate \
  --record /tmp/session-storage-design/decision-record.json \
  --target implementable
```

The script checks machine-verifiable structure, gate status, evidence metadata, risk controls, state rules, reader testing, and unfinished template markers. It does not verify that technical claims are true or approve the decision.

### Transition State

```bash
python3 scripts/engineering_docs.py transition \
  --record /tmp/session-storage-design/decision-record.json \
  --to in_review \
  --actor "Tech Lead" \
  --reason "Author checks completed"
```

Every transition is validated before the record is written, and every accepted transition is appended to `history`.

## Tests

```bash
python3 -m unittest discover -s tests -v
```

## Install

Copy the complete skill directory into your host's Skills directory, or have a file-capable agent read `SKILL.md` and its routed references. Discovery and installation paths vary by host. For TRAE:

```bash
git clone https://github.com/Job-Yang/jobyang-ai-skills.git
cp -R jobyang-ai-skills/skills/engineering-docs ~/.trae/skills/engineering-docs
```
