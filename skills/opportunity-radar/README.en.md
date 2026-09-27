# Opportunity Radar

Turn a domain or a set of user observations into product leads with source evidence. Install it on its own in TRAE, Mira, or another agent that can read skill files. iLoop and the scorecard skill are not required.

[简体中文](./README.md)

## Use it

> Use opportunity-radar to explore personal knowledge management. Find recurring complaints that existing products have not addressed, and keep the original links and quotations.

> Extract opportunities from these interviews and reviews. Use only the supplied material.

Inputs may include a domain, audience, skills, resource limits, competitor links, or source documents. Without a direction, the default scope is AI-native products a solo developer could build. The user can change that scope.

## Design

Look for signals in discussions, open-source projects, product launches, negative reviews, and trend data; then cross-check relevant claims. Each candidate explains who has a problem, where existing solutions fall short, and what evidence supports that conclusion.

Keep links, quotations or data, signal strength, and reasoning. Mark unsupported claims as assumptions. Popularity alone does not establish willingness to pay, and reposts do not count as independent sources.

The skill discovers and screens leads. A person or an optional scorecard can assess investment potential later; no downstream workflow starts automatically.

## Output

A Markdown candidate list with metadata. Each entry includes its domain, source, evidence, signal strength, fact/assumption label, and suggested topic identifier.

The bundled `opc-artifact/v1` metadata is an interchange format, not a runtime dependency. Import derives the standard filename from the date and topic, even if the downloaded file was renamed.

## Requirements

- An agent that can read the skill and input material.
- Host-provided search or page access for current public research. No crawler, account, or paid data service is included.
- Without network access, work from supplied material and disclose the coverage limits.
- Python 3.9+ and its standard library for validation and transfer tools. Without Python, deliver complete text and mark machine validation as pending.

## Install and transfer

Copy the whole `opportunity-radar/` directory to `~/.trae/skills/` or the host's skill directory.

Run these commands from the skill directory. `candidates.md` is the completed output; the receiving directory is explicit:

```bash
python3 scripts/artifact_io.py validate --input candidates.md
python3 scripts/artifact_io.py pack --input candidates.md --out radar-result.zip
python3 scripts/artifact_io.py ingest --input radar-result.zip --output-root ./received --dry-run
python3 scripts/artifact_io.py ingest --input radar-result.zip --output-root ./received
```

Deliver a downloadable Markdown/ZIP file, or a complete Markdown code block when attachments are unavailable. New imports remain pending human review. Conflicting content is not overwritten.

An explicitly active OPC workflow supplies inputs, output location, and approval rules. Standalone calls do not search for iLoop directories.

## Package

- [SKILL.md](./SKILL.md): agent instructions and output format.
- [sources.md](./references/sources.md), [search-queries.md](./references/search-queries.md), [golden-signals.md](./references/golden-signals.md): source selection and screening.
- [handoff.md](./references/handoff.md): standalone and cross-platform delivery.
- `scripts/artifact_io.py` and `scripts/scoring-rules.json`: bundled transfer and validation tools.

Validation checks file structure, not source truth or commercial potential.
