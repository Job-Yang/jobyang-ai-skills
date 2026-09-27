# Opportunity Radar

Search public discussions, open-source projects, product launches, negative reviews, and trend data for product leads, then turn them into candidates backed by original evidence.

[简体中文](./README.md)

## What it can do

| Capability | Action |
| --- | --- |
| Focused scans | Search by domain, audience, skill set, or resource constraint |
| Weak-signal discovery | Read comments, issues, reviews, and workarounds for recurring unresolved pain |
| Supply checks | Inspect existing products, free tools, and manual alternatives before claiming a gap |
| Source deduplication | Trace reposts and repeated statements back to their upstream source |
| Signal assessment | Separate pain, payment behavior, trend direction, switching cost, and supply |
| Counterevidence | Drop a lead when an existing tool is sufficient or users reject payment |
| Portable output | Preserve links, quotations, signal rationale, evidence status, and a stable topic slug |

## Why it exists

Opportunity discovery often starts with an idea and searches backward for support, or treats a trending term as proof of demand. Radar reverses the order.

It first asks who has the problem, in which situation, and how they solve it today. Search results are only leads. A candidate must return to the original post, repository, review, or trend source and retain the evidence that could also disprove it.

The goal is not a long list of ideas. It is to discard unsupported ideas early and preserve the questions worth testing.

## How to ask

> Use opportunity-radar to explore personal knowledge management. Find recurring complaints that existing products have not addressed, and keep original links and quotations.

> Extract opportunities from these interviews and reviews. Use only the supplied material.

Inputs may include a domain, audience, skills, resource limits, competitor links, or source documents.

## How it works

```text
Define the search scope
→ collect signals from five source families
→ use high-signal queries to find direct complaints
→ open original material and deduplicate citation chains
→ check alternatives and counterevidence
→ screen demand, payment, supply, and timing
→ publish candidates and the next validation question
```

Community discussions reveal language and unmet needs. GitHub and Show HN reveal technical feasibility and missing product layers. Product Hunt comments expose gaps in recent launches. Low-star product reviews show where active or paying users are dissatisfied. Trends data shows direction, not willingness to pay.

## Output

Each Markdown candidate includes:

- the opportunity and target audience;
- original links, quotations, or data;
- signal strength and rationale;
- existing alternatives and counterevidence;
- `real` or `assumption` evidence state;
- the next question that could invalidate it;
- a stable topic slug.

Radar discovers and substantiates leads. It does not turn them into investment conclusions.

## Evaluation evidence

Six same-host comparisons covered simulated interviews, public official material, and one live-retrieval case:

| Stage | No-skill baseline | Radar |
| --- | ---: | ---: |
| Four development cases | 20.00 / 20 | 20.00 / 20 |
| Two holdout cases | 19.75 / 20 | 20.00 / 20 |

All six overall pairwise decisions were ties. Both arms caught reposts, existing exporters, free alternatives, and the distinction between trial and payment. The evaluation found no stable quality uplift and no clear regression.

This result suggests that strong models may already perform much of the method on tightly specified tasks. Radar's clearer current value is consistent source handling, evidence records, and invalidation criteria across repeated scans. The benchmark is small and near the scoring ceiling, so it does not establish general improvement.

## Install and validate

Copy the complete directory into the host's Skills directory. Current public research requires host-provided search or page access; supplied material can be analyzed offline.

Python 3.9+ provides structural validation and transfer:

```bash
python3 scripts/artifact_io.py validate --input candidates.md
python3 scripts/artifact_io.py pack --input candidates.md --out radar-result.zip
python3 scripts/artifact_io.py ingest --input radar-result.zip --output-root ./received
```

Package references cover source selection, high-signal queries, screening criteria, and file handoff. Structural validation does not establish source truth or commercial potential.
