# reverse-teardown

> Don't stop at "this is good": reverse-engineer what a concrete artifact actually got right, and separate transferable rules from details that only work in its context.

[中文](./README.md)

## What it can do

- Reverse-engineer one existing, concrete artifact: UI/interaction, app/web page, code module or architecture, design doc, prompt/skill, process, or dashboard.
- Judge quality first: a mediocre artifact gets "what to learn + what to avoid" instead of forced praise.
- Turn "feels good" into: whose problem it solves, structure and key flows, and the choices that create the quality gap — each choice examined for what it replaces, what problem it removes, and what it costs.
- Force a split between **transferable rules** and **context-only details**; every rule carries its enabling conditions and failure conditions.
- Deliver 3–5 mechanism-level rules, a verifiable action checklist, and one minimum experiment with continue/stop signals.

## Why it exists

People see strong work and feel that it is good, yet cannot say why, and copying it blindly either imports resource-dependent details or reproduces only the surface form.

`reverse-teardown` turns admiration into a fixed analysis chain: observe structure → identify key choices → audit transfer conditions → land concrete actions. It keeps single-sample discipline: one artifact can only show "this worked for them," never "the whole industry should do this."

It is not a praise generator ("elegant", "amazing", "best-in-class" do not count as findings), and it neither makes adoption decisions (`outside-view`) nor writes the new proposal (`product-brief`).

## How to use it

Point it at a concrete artifact and say what you want to take away:

- "Tear down this Netflix home page; I want to move its information hierarchy to a TV app."
- "What makes this technical proposal good, and what should I watch out for if I copy it?"
- "Reverse-engineer this skill and tell me what to learn."

It also works without a specific destination: output degrades to "enabling conditions + first step if you borrow." Dynamic interaction requires a running build or screen recording, not imagined behavior from static screenshots.

## Boundaries

- Abstract concepts and explanations → `feynman-explainer`.
- Judging whether an argument holds → critical-reading / argument-analysis methods, not this skill.
- Finding evidence for your own product idea → `opportunity-radar`; writing a new proposal afterward → `product-brief` / `style-compass`.
- Technology choices and adoption decisions → `outside-view`.
- No teardown from reputation, second-hand summaries, or inaccessible source material.
