# Haohao Shuohua · Chinese Writing Cleanup

[简体中文](./README.md)

A Chinese writing Skill for AI agents: make generated Chinese sound like a human wrote it.

## What It Does

Haohao Shuohua is both a writing rule that should stay active while drafting and a cleanup pass before delivery. It is meant for Chinese documents, weekly updates, notices, plans, replies, summaries, and rewritten drafts.

Its one-line rule is:

**Keep the facts, remove AI flavor, restore Chinese rhythm, and do not invent words to sound profound.**

## Why Use It

AI-generated Chinese often feels strange even when the meaning is technically correct. The problem is not simply that it is too formal or too long. The deeper problem is that it often carries an English sentence skeleton under Chinese words: noun-heavy phrases, passive structures, suffixes such as "化 / 性 / 度", forced triads, decorative dashes, inflated endings, and abstract words that hide the real action.

This Skill treats that as a writing disease with concrete symptoms. It does not blindly make everything shorter or more casual. It first protects facts, numbers, terms, commands, mechanisms, and citations. Then it removes the patterns that make the text feel machine-made. Finally, it restores what good Chinese relies on: real verbs, concrete scenes, readable breath, and enough silence for the reader to connect the dots.

The most important rule is scale: **edit from meaning, not from isolated sentences.** If the task is to revise a whole article, the whole article is the context. If the task is one paragraph, the paragraph is the unit. Many bad AI sentences are not fixable sentence by sentence because the paragraph itself is badly designed.

The second rule is restraint: **do not rewrite good sentences just to show work.** A sentence that has no AI flavor and says the right thing should be left alone.

## Core Checks

- **Fact preservation**: numbers, terms, command lines, causal direction, mechanisms, and citation-level evidence must not change.
- **AI-flavor scan**: remove translationese, forced structure, empty intensifiers, inflated endings, overused dashes, and artificial balance.
- **Chinese rhythm**: let verbs carry the sentence, use concrete examples where they clarify the point, and fix breathless long sentences without flattening everything into casual speech.
- **Word precision**: verbs and adjectives must fit their subjects. Strong but wrong wording is worse than plain wording.
- **No fake profundity**: do not coin new terms unless there is no existing word and the term is explained immediately.

## Install

```bash
git clone https://github.com/Job-Yang/jobbyang-ai-skills.git
cp -R jobbyang-ai-skills/skills/haohao-shuohua ~/.claude/skills/haohao-shuohua
```

Keep the complete directory. Do not copy only `SKILL.md`, because the Skill relies on the files under `references/`.

## Structure

```text
haohao-shuohua/
├── README.md
├── README.en.md
├── SKILL.md
├── assets/
└── references/
```
