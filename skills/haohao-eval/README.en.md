# Haohao Eval

[简体中文](./README.md)

`haohao-eval` evaluates and continuously improves `haohao-shuohua`. It supports one-off comparison and a daily loop that generates cases, recalls failures, validates candidate guidance, monitors releases, and rolls back regressions.

## Capabilities

- Judge rewrites against the original as harmed, unfinished, acceptable, or uncertain.
- Check both directions: source information must survive, and rewrite information must have a source.
- Blind tool identity and ordering before judging.
- Mix historical regression, clean controls, new cases, probes, and author-supplied material.
- Cluster fabrication, omission, terminology drift, register mismatch, unnecessary editing, and residual AI style.
- Freeze candidate rules before either arm writes its outputs.
- Run in shadow mode for 14 days, then require same-day gates and next-day retesting.
- Monitor a release for seven days and roll back when harm rises materially.
- Ask the author only a few binary questions that the judge cannot resolve.
- Pack state, precedents, releases, and recent runs with hashes for portable recovery.

## Why there is no composite quality score

The previous unified score rewarded inactivity. Across the 50 historical cases, an unchanged source averaged **94.5** and ranked first in **27 of 50** cases, above all three real rewrite variants. It measured regular-expression cleanliness better than semantic fidelity.

The current order is:

```text
fidelity
→ register
→ expression
```

Fabrication, omission, degree changes, or terminology drift make a rewrite harmful. A factually sound rewrite can still be unfinished because of residual AI style, awkward language, or needless edits. Regex and number checks raise flags only; they do not decide quality.

## Daily loop

```text
judge calibration
→ new cases plus regression and clean controls
→ current-version rewrites
→ candidate guidance from accumulated failures
→ frozen candidate
→ blinded judging with quote verification
→ deterministic release gates
→ next-day retest
→ publish or retain the current version
→ post-release monitoring and rollback
```

A single bad case cannot change the writing rules. A cluster needs at least six findings spread across two days or two source types. One candidate may change at most two rules.

Automation publishes only `daily-learning.md` in the user data directory. It cannot modify the writing Skill's core instructions, evaluation code, or historical material.

## Run

```bash
python3 scripts/loop.py init \
  --shuohua-dir /path/to/haohao-shuohua \
  --model "current model"

python3 scripts/loop.py status
python3 scripts/loop.py start --model "current model"
```

`start` prints the run directory and plan. Continue with the [daily loop guide](./references/daily-loop.md).

Author replies such as “keep shadow mode,” “enable automatic publishing,” “roll back,” or “D12 yes” map to deterministic commands. The agent never answers a dispute for the author.

## One-off evaluation

The [judge protocol](./references/judge-protocol.md) applies without running the publishing loop:

1. Remove source identity and judge each rewrite independently.
2. Perform forward and reverse fidelity checks.
3. Quote every reported issue so it can be verified literally.
4. Allow ties, all-bad outcomes, and uncertainty.

Shorter, more casual, or lower-regex text is not automatically better.

## Bundled evidence

| Dataset | Size | Purpose |
| --- | ---: | --- |
| Historical cases | 50 | Originals, three anonymized rewrites, and human feedback |
| Precedents | 150 | One record per case and rewrite |
| Regression seeds | 50 | Rotating daily regression |
| Clean controls | 6 | Detect unnecessary edits to already acceptable text |

The 50 cases influenced the rules and are historical regression, not unseen generalization evidence. New real material is required to establish improvement.

External BadCase sources are disabled by default and configured outside the Skill package. Accounts, internal links, and credentials are not stored here.

## Data and verification

Runtime state is stored under `$HAOHAO_EVAL_HOME`, `$XDG_DATA_HOME/haohao-eval`, or `~/.local/share/haohao-eval`. Published guidance is stored under the corresponding `haohao-shuohua/daily-learning.md`.

The main loop uses only the Python 3 standard library:

```bash
python3 scripts/test_loop.py
```

Tests cover the multi-day lifecycle, candidate rejection, quote verification, disputes, real material, pack/unpack, and path-traversal rejection. `fit_weights.py` is a historical replay tool and additionally requires NumPy and SciPy.
