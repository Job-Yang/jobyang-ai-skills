# Job Yang AI Skills

AI Agent Skills by Job Yang.

This is a long-term Skill repository: a place to turn repeated judgment, workflow, scripts, and boundaries from real work into reusable Agent Skills.

In the AI era, the most valuable things are not always one-off answers. They are the working patterns that survive repetition. A writing decision, a way to inspect a video, a habit of separating observation from guesswork: if they stay inside one chat, they disappear quickly. A Skill turns that experience into something installable, callable, and open to further refinement.

This repository is not a prompt cheat sheet. Each Skill should be a compact piece of practice: it knows when to trigger, what material to inspect, where its limits are, and when it should stop and let a human decide.

[简体中文](./README.md)

## Skills

| Skill | What it does |
| --- | --- |
| [vdd](./skills/vdd/) | Verification-driven development: run a verification pass before claiming "done" or "no problem" — no false optimism, no forced nitpicking, and the confidence to say it's fine. |
| [haohao-shuohua](./skills/haohao-shuohua/) | Cleans Chinese writing so it sounds like a person wrote it: keeps facts, removes AI flavor, restores Chinese rhythm, and blocks fake profundity. |
| [cuihuo](./skills/cuihuo/) | An opinion-hardening engine: turn a technical point into a plain, restrained op-ed with one idea per section, or distill it into a short note. |
| [tangshan-style](./skills/tangshan-style/) | A writing engine for future-facing speculative essays with historical depth and lines worth chewing on. |
| [feynman-explainer](./skills/feynman-explainer/) | Uses the Feynman technique to truly explain hard things: one reasoning chain, derived step by step, so non-experts actually get it. |
| [sansi-erhouxing](./skills/sansi-erhouxing/) | Think before you edit: read the whole skeleton of an existing document before changing it, instead of patching one paragraph at a time. |
| [video-reader](./skills/video-reader/) | Turns video into timestamped keyframes and a motion timeline, so an image-only LLM can reason about what happened at which second. |

## Why This Repo Exists

Many AI capabilities look like one-off conversational tricks. Underneath them, there is often a structure worth preserving.

Writing is not just "polish this." It is a set of decisions about facts, tone, rhythm, and editing boundaries. Reading a video is not just "look at this clip." It is a way to break motion into keyframes, timelines, and inspectable observations. When patterns like these repeat, they should leave the chat and become standalone Skills.

The Skills in this repository should follow a few rules:

- **Concrete**: solve a real problem, not a vague promise to improve productivity.
- **Bounded**: know what it should do, and what it must not decide for the user.
- **Reusable**: be more than a spark of inspiration; it should work again next time.
- **Tool-friendly**: if text rules are not enough, include scripts, references, and workflow.
- **Compounding**: new experience should make the Skill thicker over time.

## Install

Clone the repository and copy the Skill directory you need into your agent's Skills directory.

```bash
git clone https://github.com/Job-Yang/jobbyang-ai-skills.git
cp -R jobbyang-ai-skills/skills/haohao-shuohua ~/.claude/skills/haohao-shuohua
cp -R jobbyang-ai-skills/skills/video-reader ~/.claude/skills/video-reader
```

Claude Code's default user-level directory is:

```text
~/.claude/skills/
```

Keep each Skill directory intact. Do not copy only `SKILL.md`, because some Skills read files under `references/`, `scripts/`, or `assets/`.

## Repository Layout

```text
.
├── README.md
├── README.en.md
└── skills/
    ├── vdd/
    ├── haohao-shuohua/
    ├── cuihuo/
    ├── tangshan-style/
    ├── feynman-explainer/
    ├── sansi-erhouxing/
    └── video-reader/
```

Each Skill directory uses `SKILL.md` as its entry point; some also ship `references/`, `scripts/`, or `assets/`.

## License

MIT
