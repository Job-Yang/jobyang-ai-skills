# Skill Library — Positioning & Collaboration Map

> Three questions this map answers: **what problem each skill solves alone, what you get by installing it into any AI environment, and how skills work together.**
> Interactive companion: [skill-map.html](./skill-map.html).

## 0. First principle: skills are not bound to any runtime

- Every skill is a **self-contained SKILL.md folder** that relies only on generic host capabilities (read/write, retrieval, conversation). It must stand alone in any host or AI environment.
- Engineering feedback loops, completion gates, plugin runtimes, or flow insertion points provided by some hosts are **optional enhancements, not dependencies**: a skill may be loaded at those points, but removing those environments must not break it.
- When writing a skill: refer to sibling or external skills by neutral descriptions ("critical-reading/argument-analysis methods"), never by a host's proprietary skill names, commands, or tools. State optional capabilities as "use if the host provides it; otherwise degrade."
- The skill repository is the single source of truth; distribution everywhere is handled by `tools/sync_skills.py` (Section 5).

## 1. How to use this map

Run the Section 4 checklist every time a skill is added or changed; keep the table, this map, and both READMEs in sync. See [SKILL-ARCHITECTURE.md](./SKILL-ARCHITECTURE.md) for the single-ownership matrix, L1–L4 layering, and dual-model acceptance gates, and [SKILL-GAP-AUDIT.md](./SKILL-GAP-AUDIT.md) for structural gap audits.

## 2. Skill registry (6 logical groups · 30 skills)

> Note: Physical directories remain flat under `skills/<name>/` for host compatibility; logical groups live in `tools/skills-manifest.json` (`engineering`, `product-opc`, `thinking`, `writing`, `personal-tools`, `governance`) and support `--group` sync.

Status: ✅ available　⏸ deferred　❌ rejected

### Group 1 · Full Engineering Lifecycle (`engineering`: design → spec → battle → execute → CR → bugfix → PR → final gate)

| Skill | Unique problem | Input → Output | Standalone value (any host) | Optional enhancement |
| --- | --- | --- | --- | --- |
| ✅ engineering-docs | Engineering RFC/ADR docs and diagrams | context → doc+diagrams | Writes reviewable tech specs alone | Hands off to `implement-spec` / `spec-battle` |
| ✅ implement-spec | Compile approved proposal/refactor into coding Spec | PRD/RFC/goal → deep modules+1-commit steps | Actionable coding plan anywhere | Auto-routes `repo` / `local` / `ephemeral` |
| ✅ spec-battle | Clean-context adversarial Spec/PRD blind review | doc+code → 4-part objections+hand-off list | Prevents author blind spots | Runs isolated read-only cross-model subagent |
| ✅ go-work | Low-context step-by-step execution, resume & archive | open Spec → commits+archive with `.ignore` | Resumes cleanly across sessions | Up to 3 temporary detached worktrees |
| ✅ diff-review | Read-only deep Code Review + Skeptic false-positive filter | diff/PR → sign-off or paste-ready comments | Worktree test check & severity filter | Multi-team monorepo rollout/concurrency audit |
| ✅ code-bugfix | Red-loop root-cause debugging & Sibling Sweep | bug/error → red repro+3 ranked hypotheses+tests | 10-rung repro ladder + secret redaction | Safe git bisect worktree + Sibling Sweep |
| ✅ pr-prep | PR hygiene check, split advice, description & offline HTML tour | branch → PR summary+`$TMPDIR` HTML report | Catches leaked state & oversized PRs | Rollout toggle & rollback readiness check |
| ✅ vdd | Evidence-based completion gate & multi-turn drift control | done claim → verified proof & clear sign-off | Independent anti-fabrication gate | Clean split from `diff-review` / `code-bugfix`; supports adversarial panel |

### Group 2 · Product Incubation & Prototyping (`product-opc`)

| Skill | Unique problem | Input → Output | Standalone value (any host) | Optional enhancement |
| --- | --- | --- | --- | --- |
| ✅ opportunity-radar | Find opportunities with sourced evidence | domain/material → candidates+evidence | One-off opportunity scan | Start of a product workflow |
| ✅ opportunity-scorecard | Score one idea, script-generated | idea+evidence → 10-dim score | Runs independently | Evaluation node of a product workflow |
| ✅ product-brief | Turn idea into verifiable PRD, plan, or incremental feature card | need/scorecard → PRD/card+`GLOSSARY.md` | Defines scope & acceptance | Hands off to `implement-spec` |
| ✅ style-compass | UI design, 9 craft packs, motion physics & `DESIGN.md` | need → aesthetic prototype/spec | Independent design & motion review | Batched migration via `implement-spec`/`go-work` |
| ✅ minimum-experiment | Get real feedback at lowest cost | hypothesis → reversible test+stop threshold | Turns speculation into trials | Flows back to `product-brief` / `scorecard` |
| ✅ reverse-teardown | Learn transferable rules from one external artifact | artifact+goal → rules/local/checklist/drill | Learn from any artifact anywhere | Feeds product or design nodes |

### Group 3 · Decision & Critical Thinking (`thinking`)

| Skill | Unique problem | Standalone value | Optional enhancement |
| --- | --- | --- | --- |
| ✅ outside-view | Whether a decision needs external evidence, how much, when to stop | Disciplined retrieval standalone | Evidence base for other skills |
| ✅ steelman-choice | Two plausible options: build both strongest cases before deciding | Prevents rash choices in any conversation | Any "user must decide between options" point |
| ✅ claim-check | Verify discrete claims/data with 5-level credibility & fallacy audit | Verifies claims standalone | Reuses outside-view discipline when online |
| ✅ argument-reading | Rebuild an entire article into argument map, premises & failure bounds | Critical reading in any environment | Discrete fact checks hand off to `claim-check` |
| ✅ root-rethink | Break patch loops via First Principles + cross-domain borrowing | Rederives solutions standalone | Code failures defer to `code-bugfix` |
| ⏸ socratic-clarify (P2) | When the real question itself is unclear | Multi-turn one-question clarification | Complements built-in clarify gates |

### Group 4 · Chinese Writing, Research & Infographics (`writing`)

| Skill | Unique problem | Standalone value |
| --- | --- | --- |
| ✅ feynman-explainer | Deep tech/repo/paper research & objective mechanism explanations | Standalone research reports and upstream feed |
| ✅ haohao-shuohua | De-AI Chinese lint preserving facts & natural cadence | Lints any Chinese draft |
| ✅ writing-craft | Single-branch writer across `sharing` (talks/retros/slides), `opinion` (plain essays/notes ≤120 chars), `tangshan` (column essays) | Prevents conflicting hybrid style rules |
| ✅ sansi-erhouxing | Reads full skeleton before structural edits (light edits bypass) | Prevents patchy edits without blocking typos |
| ✅ haohao-eval | Blind evaluation, daily recall & regression gating for rewrites | Independent eval bench |
| ✅ content-infographic | Zero-dependency SVG/PNG infographics & covers tightly locked to text | Standalone explanatory diagrams |

### Group 5 · Personal Intelligence, Context & Media (`personal-tools`)

| Skill | Unique problem | Standalone value |
| --- | --- | --- |
| ✅ ai-briefing | 5-minute daily AI/tech brief with facts, judgments, opportunity scores | Channels via config, zero internal endpoints |
| ✅ me-context | Portable personal profile with L0–L4 sensitivity gates | Data separated from skill, human-confirmed |
| ✅ png-compress | Local batch PNG compression with cache & quality gates | Works in any local project |
| ✅ video-reader | Converts video to timestamped keyframes + motion timeline | Understands timing on image-only models |

### Group 6 · Library Governance (`governance`)

| Skill | Unique problem | Standalone value |
| --- | --- | --- |
| ✅ skill-library-keeper | Five-question admission gate, static health audit & external skill distillation | Auto-discovers library root, zero host lock-in |

## 3. Collaboration Chains

```text
Pre-code OPC incubation:
  opportunity-radar → opportunity-scorecard → product-brief → style-compass → engineering-docs
    ↑ reverse-teardown feeds transferable lessons into any stage

In-repo full engineering lifecycle (personal `docs/` | monorepo `.agent-work/` zero-pollution):
  1→N feature card (product-brief) / RFC (engineering-docs)
    → implement-spec (deep modules + Source hash + 1-commit steps)
    → spec-battle (clean-context prosecution → 4-way defense → 1 press → human ruling)
    → go-work (light coordinator + subagents/worktrees + resume + archive)
    → diff-review (layered CR + Skeptic filter) / code-bugfix (red loop + 3 hypotheses)
    → pr-prep (hygiene + split + PR summary + $TMPDIR HTML tour) → vdd (final evidence gate)

Decision cross-chain:
  socratic-clarify → root-rethink → steelman-choice → claim-check / argument-reading → minimum-experiment
  (external facts via outside-view; experiment outcomes flow back to product-brief / scorecard)

Writing cross-cut:
  writing-craft (single-branch sharing / opinion / tangshan) → haohao-shuohua (de-AI base)
  structural edits → sansi-erhouxing first; tech research → feynman-explainer
```

Key non-overlap boundaries:

- **steelman-choice vs outside-view**: decision structuring vs evidence retrieval only.
- **claim-check vs argument-reading**: single discrete claim verification vs full-article argument reconstruction.
- **root-rethink vs code-bugfix**: design/process rethinking vs reproducible red-loop debugging.
- **engineering-docs vs implement-spec**: reviewable RFC/ADR for humans vs module signatures, seams & 1-commit steps for coding agents.
- **spec-battle vs diff-review vs vdd vs pr-prep**: `spec-battle` challenges pre-code docs; `diff-review` performs read-only line-level CR with Skeptic filtering; `vdd` enforces completion proof & anti-drift (plus optional multi-role adversarial panels); `pr-prep` packages PR descriptions, splits & offline HTML tours.

## 4. Add / Change Checklist

1. **One-sentence uniqueness** — solves one clear problem no existing skill owns.
2. **Non-overlapping triggers** — 8–10 real queries without cross-skill collisions.
3. **Same-thing test** — merge procedures solving the same problem.
4. **Zero environment coupling** — optional host enhancements degrade cleanly.
5. **Upstream/downstream consumers** — clear inputs and outputs on the map.
6. **Always-on vs on-demand** — keep domain methods as on-demand skills and CLI tools; expose lightweight first-principles guidance (`plugins/engineering-flow/rules/AGENTS.md`, zero hooks) so the model decides when to invoke tools instead of mechanical background blocking.
7. **No reverse pollution** — one-way references only.
8. **Portable multi-target sync** — `skills/` is the sole authority; `shared/` distributes common files via `--sync-shared`; run `tools/sync_skills.py --apply` (and `--sync-agy-plugin` when using Antigravity guardrails).

## 5. Sync & Portable Guardrails

- **Authority**: `skills/` (skills) and `shared/` (common contracts/scripts).
- **Manifest**: `tools/skills-manifest.json` defines the 30-skill whitelist and 6 logical groups (`--group engineering --apply`).
- **Antigravity plugin**: `plugins/engineering-flow/` packages lifecycle hooks (`PreInvocation`, `PreToolUse`, `PostToolUse`, `Stop`) and plain-language routing rules using relative paths only, registered via `tools/sync_skills.py --apply --sync-agy-plugin` without altering `hooks.json`.
