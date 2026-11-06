# Skill Library — Positioning & Collaboration Map

> Three questions this map answers: **what problem each skill solves alone, what you get by installing it into any AI environment, and how skills work together.**
> Interactive companion: `skill-map.html` (Chinese-labeled; English version can be added on request).

## 0. First principle: skills are not bound to any runtime

- Every skill is a **self-contained SKILL.md folder** that relies only on generic host capabilities (read/write, retrieval, conversation). It must stand alone in any host or AI environment.
- Engineering feedback loops, completion gates, plugin runtimes, or flow insertion points provided by some hosts are **optional enhancements, not dependencies**: a skill may be loaded at those points, but removing those environments must not break it.
- When writing a skill: refer to sibling or external skills by neutral descriptions ("critical-reading/argument-analysis methods"), never by a host's proprietary skill names, commands, or tools. State optional capabilities as "use if the host provides it; otherwise degrade."
- The skill repository is the single source of truth; distribution everywhere is handled by `tools/sync_skills.py` (Section 5).

## 1. How to use this map

Run the Section 4 checklist every time a skill is added or changed; keep the table, this map, and both READMEs in sync.

## 2. Skill registry (by thinking/work chain)

Status: ✅ available　🆕 built, pending blind test　⏸ deferred　❌ rejected

### Cluster A · Product formation (discover → evaluate → define → design → document → learn)

| Skill | Unique problem | Input → Output | Standalone value (any host) | Optional enhancement |
| --- | --- | --- | --- | --- |
| ✅ opportunity-radar | Find opportunities with sourced evidence | domain/material → candidates+evidence | One-off opportunity scan | Start of a product workflow |
| ✅ opportunity-scorecard | Score one idea, script-generated | idea+evidence → 10-dim score | Runs independently | Evaluation node of a product workflow |
| ✅ product-brief | Turn idea into verifiable PRD/plan | need/scorecard → PRD+milestones | Writes PRDs alone | Definition node of a product workflow |
| ✅ style-compass | UI design and prototypes | need → wireframes/prototype/spec | Independent design review | Design node of a product workflow |
| ✅ engineering-docs | Engineering docs and decisions | context → doc+diagrams | Writes docs alone | Connects to environments with engineering verification |
| 🆕 reverse-teardown | Learn transferable rules from one external artifact | artifact+goal → rules/context-only/checklist/minimum experiment | Learn from any artifact anywhere | Can mount on any "solution review / design reference" flow point |

### Cluster B · Judgment and thinking

| Skill | Unique problem | Standalone value | Optional enhancement |
| --- | --- | --- | --- |
| ✅ vdd | No "done" without verification | Anti-false-claims anywhere | A completion-gate runtime may carry it |
| ✅ outside-view | Whether a decision needs external evidence, how much, when to stop | Disciplined retrieval standalone | Evidence base for other skills |
| 🆕 steelman-choice | Two plausible options: which one | Strongest-case confrontation, key variable, one flip question | Prevents rash choices in any conversation | Any "user must decide between options" flow point |
| 🆕 claim-check | Is this claim/data trustworthy | Five-level credibility + reasoning-hole audit | Verify claims anywhere | Reuses outside-view discipline when online |
| 🆕 root-rethink | Are we just patching; find the root path | Split fact/assumption/goal/constraint, incl. cross-domain mode | Rederive solutions standalone | Code patches defer to the host's own root-cause flow |
| 🆕 minimum-experiment | Get real feedback at lowest cost | Reversible experiment + metrics + continue/stop signals | Turns speculation into trials | Splits work from the environment's reproducible tests |
| 🆕 argument-reading | Is a whole article's argument sound; what are its hidden premises | Full text → argument chain + evidence grades + fallacy locations | Critical reading in any environment | Discrete fact checks hand off to claim-check |
| ⏸ socratic-clarify (P2) | I can't even state my real question | Multi-turn one-question clarification | Deep clarification entry | Complements any built-in clarify gate |

> Theoretical roots: **steelman-choice** = Principle of Charity + steelman argument (the opposite of a straw man) — restate each side at its strongest before choosing. **root-rethink** = First Principles — reduce to irreducible facts, separate unverified inherited assumptions, rederive. **claim-check** = fact-checking + systematic doubt — split fact/inference/value, verify only the facts, then audit the inference. **argument-reading** = argument analysis, rebuilt without platform bindings.

### Cluster C · Chinese writing (input-type vs output-type boundaries)

✅ feynman-explainer (understand a concept), haohao-shuohua (de-AI lint), cuihuo (opinion essay), tangshan-style (speculative essay), sansi-erhouxing (read full skeleton before editing), talk-smith (talks/slides), haohao-eval (blind evaluation/recall).

### Cluster D · Data & engineering execution

✅ png-compress (batch PNG compression), video-reader (video → keyframes + timeline).

### Cluster E · Personal context

✅ me-context (portable personal profile with L0–L4 sensitivity gates; data separated from the skill).

### Cluster F · Information & content production

✅ ai-briefing (5-minute AI/tech daily brief, fact/judgment/opportunity cards; channels via config, no internal endpoints in the skill body); content-infographic (deterministic infographics where the image itself makes one point; zero-dependency SVG/PNG renderer); talk-smith (technical talks and slides).

## 3. Collaboration

```text
Product main chain: radar → scorecard → product-brief → style-compass → engineering-docs → build
  reverse-teardown feeds any stage from external artifacts.

Decision cross-chain (enter when stuck, return to the main chain after):
  socratic-clarify → root-rethink → steelman-choice → claim-check / argument-reading → minimum-experiment
  claim-check / steelman-choice call outside-view only when external facts are needed;
  experiment results flow back to product-brief or scorecard.

Writing cross-cut: haohao-shuohua (lint); cuihuo / tangshan-style / talk-smith (output);
  sansi-erhouxing before editing; feynman-explainer for understanding (called one-way by output skills).

Verification: vdd before claiming done; runtimes with a completion gate may carry it automatically.
  Compilable engineering hypotheses use the environment's own test/verification flow;
  minimum-experiment handles product/real-world hypotheses only.
```

Theoretical roots (planned skills): steelman-choice = Principle of Charity + steelman argument (opposite of straw man); root-rethink = First Principles thinking (reduce to basic facts, separate unverified assumptions, rederive); claim-check = fact-checking + Cartesian systematic doubt; argument-reading = argument analysis (rebuild reason → evidence → hidden premise).

Key non-overlap contracts:

- **steelman-choice vs outside-view**: decision structuring (mostly pure reasoning) vs evidence retrieval only.
- **steelman-choice vs scorecard**: confrontation of two given options vs scoring one idea.
- **claim-check vs outside-view**: discrete claim verification vs evidence for a decision.
- **claim-check vs argument-reading**: one discrete claim vs a whole article rebuilt as a reading map.
- **reverse-teardown vs style-compass**: learn from external artifacts vs review/design your own pages.
- **root-rethink vs host root-cause flow**: general solution/process rethinking belongs to the skill; code-patch root-causing belongs to the engineering environment's own flow.
- **feynman vs output writing skills**: one-way handshake only.

## 4. Add / change checklist

1. **One-sentence uniqueness** — one problem it solves that no existing skill does.
2. **Non-overlapping triggers** — 8–10 real queries, no two skills fire on the same one.
3. **Same-thing test** — merge when it is the same problem with a different procedure.
4. **Zero environment coupling** — still valid after removing any runtime/platform name; otherwise write "if available, else degrade."
5. **Upstream/downstream exist** — outputs have consumers; inputs have providers.
6. **Always-on vs on-demand** — only make something always-on if every interaction benefits and no tool-based carrier exists; otherwise keep it an on-demand skill.
7. **No reverse pollution** — referenced skills must not change their positioning or gates; one-way references only.
8. **Four-way delivery** — the Git repo `skills/` is the only source of truth; run `python3 tools/sync_skills.py --apply` to sync both skill runtime directories and the distribution zips. Company-only, third-party, and strongly personal skills are excluded by the manifest.

## 5. Four-way sync

Source of truth: this repository's `skills/`. Whitelist: `tools/skills-manifest.json` (only user-owned, portable, publishable skills). Command: `python3 tools/sync_skills.py` for a dry run, add `--apply` to write. Targets: the two skill runtime directories (folder name from `install_name`) and `~/Downloads/个人技能/<name>.zip`. Any skill added or changed is synced by default.

## 6. This round's decisions (from 12 external prompts + 1 collaboration instruction)

- Built, pending blind test: steelman-choice, claim-check, argument-reading, root-rethink, minimum-experiment. (argument-reading distilled from a platform critical-reading skill with all platform bindings removed; root-rethink merges first-principles + cross-domain borrowing.)
- Deferred: socratic-clarify (P2), landscape/vertical-horizontal study (framework kept, no skill).
- Rejected: expert panel (general part merges into steelman-choice); Johari Window instruction (always-on posture → host preference layer); talent discovery / life design (owner decision: too grand, little value); dual-layer explanation (conflicts with feynman's "scaffolding not printed" rule).
- Every planned/distilled skill passes three gates before release: trigger blind test (≥85%, zero trigger collisions), real-sample end-to-end, adversarial weak-spot cases; any of the five scoring dimensions below 8 blocks release.
