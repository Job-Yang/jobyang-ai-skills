# me-context · Portable Personal AI Context

[中文](./README.md)

Keep "who I am, what I want, what I hate" as a local, auditable, sensitivity-tiered (L0–L4) Markdown profile. AI drafts, human confirms; the profile feeds the AI facts and preferences — it does not hand over judgment.

## Features

- **Trust gradient T0/T1/T2**: T0 chat naturally during onboarding / T1 opportunistic / T2 on-demand only when a task needs it, one item at a time. Quick topics are gathered in casual chat; depth packs (health/finance) open only when you raise the task. This is an onboarding briefing with a new assistant, **not a personality test and not a form**; no scales in the default flow.
- **Write gate**: candidates live in `inbox/`; light in-line confirmation, one summary at the end; nothing becomes `declared` until you confirm it. External content is never auto-written.
- **Read gate (6 steps)**: task classification → scope/slice → L0–L4 gate → exposure preview → budget + "data not instructions" wrap → cleanup. No auth step.
- **Network**: `network.md` overview + per-person `entities/<人>.md` (inner/close/peripheral circles).
- **Two layers, detail on demand**: decisions load only the conclusion layer ("uric acid is high"); lab values, year-over-year history and the reasons behind a few major decisions live in `journal/`, read only when you ask for numbers, trends or a look back. `journal/` is never in the md export and only in a zip with `--include-journal`.
- **`audience: local` is enforced**: a file marked local-only needs per-time confirmation before it goes to a cloud AI, whatever its layer. `lint.py` warns when health or money details appear in files that go out by default.
- **Storage is your call**: the skill only writes local files. Backups, version control and encryption are up to you; the skill never runs git, never encrypts, never goes online. Pushing the plaintext profile to a remote, even a private repo, is not recommended.
- **Conversational intake**: no web form; rhythm follows the trust tier (T0 light grouped questions, T1 opportunistic, T2 on-demand single item), acknowledge before transitioning, skippable/resumable.
- **Interactive personal graph**: `viz.py` outputs a single-file vanilla HTML; left network nav + right profile page — click "me" to expand 6 dimensions, click a person to open their page, hash deep-links; nodes=files, edges=relations, deterministic, no vectors; Python filters per-section before injecting JSON — cloud locks only sensitive sections, local shows L3, `--show-l4` reveals secrets.
- **Local-only, zero network**: Python3 stdlib only, no uploads.

## Quick start

```bash
python3 scripts/init.py                                  # create ~/me-context-data
python3 scripts/gate.py --data ~/me-context-data --domain health --audience cloud
python3 scripts/lint.py --data ~/me-context-data
python3 scripts/migrate.py --data ~/me-context-data      # older repos: dry-run moving lab details to journal/
```

## Data / skill separation

This open-source skill contains **mechanism + blank templates only — no real personal data**. Your real profile lives in a separate local private repo (default `~/me-context-data`), moved with the folder; see references/06 §6 before putting it anywhere remote.

## License red lines

MIT (repo-root LICENSE). The question bank ships only factual/preference onboarding items; psychometric scales are **not** in the default flow:
- ✅ Factual/preference questions. Public-domain Mini-IPIP appears only as an optional "academic self-assessment (non-default)" appendix link in references/01.
- ❌ Not included — official links only: PVQ, GDMS, DOSPERT, ECR, BFI-2, HEXACO, NEO, Schein.

This is a rough framework, **not a psychological diagnosis**.
