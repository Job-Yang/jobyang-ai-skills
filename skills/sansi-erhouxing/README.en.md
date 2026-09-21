# Sansi Erhouxing · Read Before Editing

[简体中文](./README.md)

Before editing any mature document, read the whole structure first.

## What It Does

This Skill sits in front of document editing. Whether the task is to revise one paragraph, add a section, apply review feedback, or "polish the whole thing", it requires the agent to understand the document skeleton before changing words. It applies to written artifacts such as essays, research notes, plans, specifications, and Skill documents. It is not for code changes.

## Why Use It

The most common document-editing failure is local editing without global understanding.

A reviewer points at one paragraph, so the agent fixes only that paragraph. A user says "add a section", so the agent appends it at the end. The local patch may look fine, but a real document has a skeleton: each section carries one job, evidence belongs in a specific place, and the conclusion needs to close the argument that came before it.

When the agent edits without reading the whole structure, the damage is predictable:

- The revised paragraph no longer connects with the previous or next section.
- A new section hangs at the end as a patch instead of joining the main line.
- Material removed in an earlier review gets added back because history was not checked.
- "Polishing" fixes sentences while missing structural problems such as misplaced evidence or an incomplete conclusion.
- The agent keeps editing and re-reading in loops because it never formed a stable view of the whole piece.

Agents are especially prone to this failure. Their default response is **see one issue, fix one issue**: a review points at one paragraph, so they edit that paragraph; a check reports one hit, so they remove that hit. Each local change may look reasonable, while the accumulated result becomes repetitive, revives decisions that were deliberately removed, and drifts further from the original structure. This Skill turns "think before editing" into an executable pause: inspect the whole piece, map the impact area, and only then decide whether to change it.

Sansi Erhouxing turns four established engineering and writing ideas into a document-editing workflow:

- **Shotgun Surgery**: one local change may require related changes elsewhere, so list the impact area first.
- **Chesterton's Fence**: before removing or changing something, understand why it is there.
- **Kent Beck: Make the change easy, then make the easy change**: if the current structure makes a change awkward, do not force in a patch. Adjust the skeleton first, then make the now-simple change.
- **Outline-First**: build or inspect the skeleton before filling prose.

The operational loop is: **read the whole piece -> list the impact area -> pass three gate questions**. Has this point been changed before? Is the fix riskier than the problem? Will the change break the document skeleton?

If any gate fails, the correct result is not to force a patch. The right move is to leave it alone or redesign at the skeleton level.

## Install

```bash
git clone https://github.com/Job-Yang/jobyang-ai-skills.git
cp -R jobyang-ai-skills/skills/sansi-erhouxing ~/.claude/skills/sansi-erhouxing
```

## Structure

```text
sansi-erhouxing/
├── README.md
├── README.en.md
├── SKILL.md
└── references/
    ├── doc-scope.md
    └── prior-art.md
```
