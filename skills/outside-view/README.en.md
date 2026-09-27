# outside-view

> Bring in the outside evidence needed for consequential decisions without turning every simple task into a research project.

[中文](./README.md)

## What it does

A model can produce a complete answer without having enough information. This is especially risky for architecture choices, large plans, long-term roadmaps, and decisions that are expensive to reverse.

`outside-view` sits above search, RAG, and knowledge-base tools. Those tools retrieve information; this skill decides:

- whether the available evidence is already sufficient;
- which missing fact could change the action;
- whether to run a bounded verification or a deeper investigation;
- how to resolve conflicts across versions, contexts, objectives, and evidence quality;
- when to stop retrieving and preserve uncertainty.

It is not a search engine and does not replace the decision owner.

## Core protocol

```text
Is the existing evidence sufficient?
├─ Yes: DIRECT — execute or use local evidence
└─ No: name the unknown that could change the action
   ├─ Current fact or reversible choice: QUICK — one bounded primary-source check
   └─ High-impact and hard to reverse: DEEP — two rounds by default
```

Evidence is evaluated by directness, independence, recency, and fit to the current context. Conflicts are not decided by counting links. Retrieval stops when new information no longer changes the recommendation, scope, risk, or execution order.

## Relationship to the base model

This is an **encoded-preference skill**. It uses capabilities the model may already have, such as search, reasoning, and tool use, but makes the decision protocol more consistent.

Its benefit therefore varies by model:

| Base-model behavior | Expected effect |
| --- | --- |
| Already strong at search, citations, and conflict handling | Mostly improves consistency, stopping discipline, and auditability; quality uplift may be small |
| Can search but tends to collect or trust too much context | Often improves source selection, conflict handling, and retrieval efficiency |
| Weaker reasoning or small context window | The protocol may add overhead; positive impact must be measured |
| No external tools | DIRECT and uncertainty handling still work, but QUICK and DEEP cannot retrieve evidence |

As models improve, this skill may shift from capability uplift to a durable team decision protocol. If a no-skill baseline already passes your evals, the remaining value is workflow fidelity rather than extra intelligence.

## When to use it

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

No iLoop, OPC, or other skill is required. Input is the current question, available evidence, and constraints. Output is a judgment with applicability, remaining uncertainty, and original sources, integrated into the current task. It does not require a separate report or start another workflow. The host supplies retrieval tools.

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
