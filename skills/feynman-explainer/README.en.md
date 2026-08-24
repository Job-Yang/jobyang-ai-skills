# Feynman Explainer

[简体中文](./README.md)

Explain a hard thing well enough that a non-expert can actually understand it.

## What It Does

Feynman Explainer is for summaries, research notes, source-code explanations, technical mechanisms, papers, and product logic. Its job is not to replace terminology with loose words. Its job is to make the reader truly understand the thing.

## Why Use It

Model-generated explanations often look rich while staying shallow. They list terms, split content into bullet points, and give the reader many isolated facts. The reader may feel informed, but cannot explain how the parts connect.

Feynman Explainer uses one test to break that pattern: **if you cannot explain it to a non-expert, you do not understand it yet.**

It enforces two rules:

- **Explain one reasoning chain, not a pile of points**: start from the problem, show why the naive answer fails, introduce the real mechanism, explain the new difficulty it creates, and then close the loop.
- **Remove the scaffolding from the final answer**: analogies, difficulty checks, and Feynman self-tests are thinking tools. The delivered text should read like a fluent explanation, not like a worksheet with labels exposed.

The result should be something the reader can retell in their own words. Plain language, grounded analogies, and first-use term translation are all in service of that goal.

## Install

```bash
git clone https://github.com/Job-Yang/jobbyang-ai-skills.git
cp -R jobbyang-ai-skills/skills/feynman-explainer ~/.claude/skills/feynman-explainer
```

## Structure

```text
feynman-explainer/
├── README.md
├── README.en.md
├── SKILL.md
└── references/
    └── style-examples.md
```
