# outside-view

> Bring in the outside evidence needed for consequential decisions without turning every simple task into a research project.

[中文](./README.md)

## What it can do

- Decide whether existing evidence is already sufficient before retrieving more.
- Route work through `DIRECT`, `QUICK`, or `DEEP` to control research depth.
- Match API, pricing, standards, architecture, schedule, and high-risk decisions to different evidence.
- Separate primary sources, empirical results, failure cases, and comparable reference classes.
- Explain whether conflicts come from versions, contexts, metrics, or incentives.
- Detect when many pages repeat one upstream source.
- Preserve counterarguments and falsification conditions.
- Stop when more retrieval no longer changes the action.

## Why it exists

A model can produce a complete answer without having enough information. This is especially risky for architecture choices, large plans, long-term roadmaps, and decisions that are expensive to reverse.

`outside-view` sits above search, RAG, and knowledge-base tools. Those tools retrieve information; this skill decides:

- whether the available evidence is already sufficient;
- which missing fact could change the action;
- whether to run a bounded verification or a deeper investigation;
- how to resolve conflicts across versions, contexts, objectives, and evidence quality;
- when to stop retrieving and preserve uncertainty.

Search and RAG answer where material is. This skill answers whether research is worth doing, what to trust, how to handle conflicts, and when to stop. Its goal is not a longer answer; external evidence must change or constrain the decision.

## How to use it

Ask with the decision and constraints:

- “Should we migrate this monolith entirely to microservices?”
- “Is this three-month rewrite estimate credible? Use comparable projects.”
- “Two authoritative sources disagree. Which one applies to this version?”
- “We already have logs and regression results. Is external research still useful?”

The agent then follows this protocol:

```text
Is the existing evidence sufficient?
├─ Yes: DIRECT — execute or use local evidence
└─ No: name the unknown that could change the action
   ├─ Current fact or reversible choice: QUICK — one bounded primary-source check
   └─ High-impact and hard to reverse: DEEP — two rounds by default
```

Evidence is evaluated by directness, independence, recency, and fit to the current context. Conflicts are not decided by counting links. Retrieval stops when new information no longer changes the recommendation, scope, risk, or execution order.

Results are integrated into the original task: recommendation, the correction introduced by external evidence, applicability, remaining disagreement, uncertainty, and original sources.

## Why three routes

This is an **encoded-preference skill**. It uses capabilities the model may already have, such as search, reasoning, and tool use, but makes the decision protocol more consistent.

Its benefit therefore varies by model:

| Base-model behavior | Expected effect |
| --- | --- |
| Already strong at search, citations, and conflict handling | Mostly improves consistency, stopping discipline, and auditability; quality uplift may be small |
| Can search but tends to collect or trust too much context | Often improves source selection, conflict handling, and retrieval efficiency |
| Weaker reasoning or small context window | The protocol may add overhead; positive impact must be measured |
| No external tools | DIRECT and uncertainty handling still work, but QUICK and DEEP cannot retrieve evidence |

As models improve, this skill may shift from capability uplift to a durable team decision protocol. If a no-skill baseline already passes your evals, the remaining value is workflow fidelity rather than extra intelligence.

## Evaluation evidence

The initial same-host evaluation compared a no-skill baseline, an early 19 KB protocol, and the current thin protocol:

| Check | Result |
| --- | --- |
| Trigger classification | 20 cases × 2 runs, 20/20 in both |
| `DIRECT / QUICK / DEEP` routing | 15 cases × 3 runs, 15/15 in all |
| Planned retrieval | Early protocol 8/15 on average; thin protocol 5/15, a 37.5% reduction |
| One open-ended decision | Baseline 56.254 s; thin protocol 73.177 s |
| Blind judging with swapped order | Thin protocol won 8:7 and 8:6 |

The open task evaluated a fixed `top-10` RAG design. The baseline included unsupported universal release thresholds. The thin protocol cited primary sources and left parameters to local experiments, improving evidence quality at roughly 30% higher latency.

This supports routing consistency and reduced over-retrieval on the fixed cases. It does not establish universal accuracy gains, unseen-prompt generalization, or cross-model performance. Trigger and route labels were derived from the protocol, and only one open-ended task was tested.

## Boundaries

Use for:

- architecture, core dependency, and data-model choices;
- large plans, roadmaps, and schedule credibility;
- security, privacy, compliance, financial, or other high-risk decisions;
- multi-option trade-offs requiring a recommendation;
- requests for industry consensus, mature approaches, failure cases, or contrary evidence.

Do not use for:

- translation, faithful summarization, formatting, or pure creation;
- execution of an approved plan;
- issues already resolved by code, tests, logs, or direct primary evidence;
- simple current-fact lookup with a user-specified source.

## Installation

Copy the complete directory into a compatible Agent Skills location.

TRAE:

```bash
cp -R outside-view ~/.trae/skills/outside-view
```

Claude Code:

```bash
cp -R outside-view ~/.claude/skills/outside-view
```

Other compatible hosts may use `~/.agents/skills/` or their documented project-level skills directory.

Start a new session after installation and confirm that `outside-view` appears in the host's skill list.

## Validation

Validate the package:

```bash
uvx --from skills-ref agentskills validate .
```

## Version

Current version: `0.1.0`

This is the first public release. The core protocol is stable; actual results still depend on the model, host tools, and task.

## License

[MIT](./LICENSE)
