#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""haohao-eval 每日召回的确定性入口。

实现已拆到 hh_eval/ 包（const/fs/judge/seed/fp/rules/gates/statedoc/docdoc/pipeline/preflight/cli）。
这个文件只剩两件事：把包里的全部公共名字再导出一遍（测试和老脚本直接 `import loop` 照旧），
把 main 交给 hh_eval.cli。`python3 scripts/loop.py <任意旧命令>` 的行为和输出与拆包前一致。
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

from hh_eval.const import *  # noqa: F401,F403
from hh_eval.fs import *  # noqa: F401,F403
from hh_eval.judge import *  # noqa: F401,F403
from hh_eval.seed import *  # noqa: F401,F403
from hh_eval.fp import *  # noqa: F401,F403
from hh_eval.rules import *  # noqa: F401,F403
from hh_eval.gates import *  # noqa: F401,F403
from hh_eval.statedoc import *  # noqa: F401,F403
from hh_eval.docdoc import *  # noqa: F401,F403
from hh_eval.pipeline import *  # noqa: F401,F403

from hh_eval.cli import main  # noqa: E402

if __name__ == "__main__":
    sys.exit(main())
