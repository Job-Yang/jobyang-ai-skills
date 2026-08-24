# VDD · Verification-Driven Development

[简体中文](./README.md)

Before saying "done", "no problem", or "I understand", make the agent verify itself.

VDD is both a method and a proof. Install this Skill and an otherwise plain agent can immediately behave differently: less false optimism, less forced nitpicking, and more willingness to say "this is fine" when the evidence supports it. That matters because the method does not depend on any external tool or special runtime. Its force comes from the loop itself.

## What It Guards Against

**Failure one: optimistic completion.**

Models are trained to be helpful. That instinct often turns into premature confidence: "done", "fixed", "understood", "should be fine" appear before the work has been checked. The model is not necessarily lying. It has followed one chain of reasoning to the end and now feels coherent.

The problem is that the same reasoning process that produced the answer cannot reliably certify the answer. The author and the reviewer are the same mind. Human engineering already knows this: code review and QA exist because people are poor judges of their own output. Models have an extra problem: each new sentence continues from the previous context, so a "self-check" after a conclusion often reinforces the same path instead of escaping it.

**Failure two: forced problem-finding.**

If you ask a model to review a large change with the mood of "find issues", it can almost always manufacture issues, even when the design is already sound. Then it over-edits. If the user pushes back, it may immediately agree that it over-edited. The scale keeps drifting because the model is measuring against the latest sentence in the conversation, not against a stable standard.

Both failures are forms of pleasing the moment. One pleases the desire for completion. The other pleases the desire to see effort.

## How VDD Fixes It

VDD has two pillars.

**Pillar one: single-pass self-proof.**

Before claiming completion, the agent runs three checks:

- **Expose assumptions**: what hidden assumptions are inside the request, what information is missing, and where do tasks like this usually fail?
- **Attach evidence to every action**: every change and every claim needs a reason grounded in evidence. Inference must be labeled as inference; it must never be presented as observation.
- **Pass four gates**: time matches, scope matches, mechanism explains the result, and there is counter-evidence or a contrast case.

The key is to switch roles. "I will check my work" is not enough if the same chain of thought is still defending itself. The agent must behave like a fresh reviewer who only sees the artifact and the acceptance standard.

**Pillar two: anti-drift standards.**

Single-pass proof checks one step. Large work and long conversations need a stable ruler. Before starting, write down the task contract:

- System constraints: rules that must not be broken across tasks.
- Task contract: what this task is trying to achieve, what design choices have been made, and what is explicitly out of scope.
- Step acceptance: the local check for the current action.

After that, every review has only three valid outcomes:

- It matches the ruler, so do not change it.
- It violates the ruler, so fix it with evidence.
- The ruler does not cover this case, so stop and update the standard before changing the work.

This is the part that prevents both over-editing and fake issue lists. A reported "problem" must map to the ruler. If it cannot, it is not a defect; at most, it is a missing standard.

## Why This Is the Minimal Reproducible Proof of VDD

VDD should not only sound right. It should be testable. This Skill is the smallest runnable form of the idea: no special tools, no platform integration, just a disciplined verification loop. Use it once and you can observe the behavior change directly. That is the point: **do not argue that verification matters; run the loop and get evidence.**

## Install

```bash
git clone https://github.com/Job-Yang/jobbyang-ai-skills.git
cp -R jobbyang-ai-skills/skills/vdd ~/.claude/skills/vdd
```

## Structure

```text
vdd/
├── README.md
├── README.en.md
└── SKILL.md
```
