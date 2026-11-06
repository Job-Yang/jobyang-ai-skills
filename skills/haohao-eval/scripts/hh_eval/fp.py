# -*- coding: utf-8 -*-
"""haohao-shuohua 底线指纹与技能指纹。从 loop.py 原样搬来。"""
import glob
import json
import os

from hh_eval.const import MARK_END, MARK_START
from hh_eval.fs import file_sha, published_path, read_text, sha, skill_dir


def constitution_text(skill_md):
    text = read_text(skill_md)
    parts, pos = [], 0
    while True:
        s = text.find(MARK_START, pos)
        if s < 0:
            break
        e = text.find(MARK_END, s)
        if e < 0:
            break
        parts.append(text[s:e])
        pos = e + len(MARK_END)
    return "\n".join(parts)


def find_shuohua_dir(cfg):
    """找 haohao-shuohua 技能目录，按优先级：
    1. 环境变量 HAOHAO_SHUOHUA_DIR（换机器/包结构变了时的兜底，最可靠）；
    2. config.json 的 shuohua_skill_dir（init 时记录）；
    3. 本包的兄弟目录（../haohao-shuohua），并从技能目录逐级向上找同名兄弟，
       应对技能包整体被挪到别的父目录；
    4. 各家已知的技能根目录（.agents/.claude/.cursor/.trae/.codex/.mira/skills、~/skills）。
    都找不到返回空串：fingerprints 只是少了底线哈希，流程不致命。"""
    cands = [os.environ.get("HAOHAO_SHUOHUA_DIR") or "", cfg.get("shuohua_skill_dir") or ""]
    # 从本技能目录逐级向上，找兄弟目录 haohao-shuohua（技能包整体搬家时仍能定位）
    p = skill_dir()
    for _ in range(6):
        p = os.path.dirname(p)
        if p and p != os.path.dirname(p):
            cands.append(os.path.join(p, "haohao-shuohua"))
    home = os.path.expanduser("~")
    for root in (".agents/skills", ".claude/skills", ".cursor/skills", ".trae/skills", ".trae-cn/skills",
                 ".codex/skills", "skills", ".mira/skills"):
        cands.append(os.path.join(home, root, "haohao-shuohua"))
    for c in cands:
        if c and os.path.exists(os.path.join(c, "SKILL.md")):
            return os.path.abspath(c)
    return ""


def fingerprints(cfg):
    fp = {}
    sd = find_shuohua_dir(cfg)
    fp["shuohua_dir"] = sd
    if sd:
        fp["shuohua_skill"] = sha(read_text(os.path.join(sd, "SKILL.md")))
        refs = sorted(glob.glob(os.path.join(sd, "references", "*.md")))
        fp["shuohua_refs"] = sha("".join(read_text(p) for p in refs))
        fp["constitution"] = sha(constitution_text(os.path.join(sd, "SKILL.md")))
    skill = skill_dir()
    files = [os.path.join(skill, "SKILL.md")] + sorted(glob.glob(os.path.join(skill, "references", "*.md"))) \
        + sorted(glob.glob(os.path.join(skill, "scripts", "*.py"))) \
        + sorted(glob.glob(os.path.join(skill, "scripts", "hh_eval", "*.py")))
    fp["eval_skill"] = sha("".join(read_text(p) for p in files))
    fp["config"] = sha(json.dumps(cfg, ensure_ascii=False, sort_keys=True))
    fp["published"] = file_sha(published_path())
    return fp


__all__ = ["constitution_text", "find_shuohua_dir", "fingerprints"]
