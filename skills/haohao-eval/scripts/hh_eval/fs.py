# -*- coding: utf-8 -*-
"""路径与文件读写、配置/状态读写、Lock、技能自带数据定位。

数据根隔离（新增）：设了 data-root（--data-root 参数或 HAOHAO_EVAL_DATA_ROOT）时，
eval_home 和 shuohua_home（发布目录）一起挪到 <root>/ 下，互不污染用户全局目录；
不设时一切照旧（HAOHAO_EVAL_HOME / XDG_DATA_HOME 的老优先级），线上行为不变。
"""
import datetime as dt
import hashlib
import json
import os

from hh_eval.const import DEFAULTS, Stop

# scripts/ 目录（旧 loop.py 的 HERE）与其上一级（技能目录，旧 loop.py 的 SKILL_DIR）
SCRIPTS_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SKILL_DIR = os.path.dirname(SCRIPTS_DIR)
PKG_DATA = os.path.join(SKILL_DIR, "data")

_DATA_ROOT = ""  # 由 cli 在解析参数后 set_data_root()；空串 = 原有行为


def set_data_root(root):
    """把数据目录和发布目录一起挪到一个根下面。测试/云电脑隔离用；空串=恢复原有行为。"""
    global _DATA_ROOT
    _DATA_ROOT = (root or "").strip()


def data_root():
    return _DATA_ROOT or os.environ.get("HAOHAO_EVAL_DATA_ROOT", "")


def lark_cmd():
    """飞书 CLI 的命令名。宿主用别的 CLI 时设 HAOHAO_EVAL_LARK；默认 lark-cli，线上输出不变。"""
    return os.environ.get("HAOHAO_EVAL_LARK") or "lark-cli"


def skill_dir():
    """技能根目录。云/容器里把技能包拷到别处时，可用 HAOHAO_EVAL_SKILL_DIR 指定；默认按文件位置定位。"""
    return os.environ.get("HAOHAO_EVAL_SKILL_DIR") or SKILL_DIR


def xdg_data():
    return os.environ.get("XDG_DATA_HOME") or os.path.join(os.path.expanduser("~"), ".local", "share")


def eval_home():
    root = data_root()
    if root:
        return os.path.join(root, "haohao-eval")
    return os.environ.get("HAOHAO_EVAL_HOME") or os.path.join(xdg_data(), "haohao-eval")


def shuohua_home():
    root = data_root()
    if root:
        return os.path.join(root, "haohao-shuohua")
    return os.path.join(xdg_data(), "haohao-shuohua")


def published_path():
    return os.path.join(shuohua_home(), "daily-learning.md")


def H(*parts):
    return os.path.join(eval_home(), *parts)


def run_dir(date):
    return H("runs", date)


def today_str(args=None):
    if args is not None and getattr(args, "date", None):
        return args.date
    return dt.date.today().isoformat()


def load_json(path, default=None):
    if not os.path.exists(path):
        return default
    with open(path, encoding="utf-8") as f:
        return json.load(f)


read_json = load_json  # 旧名，拆包前 loop.py 里叫 read_json


def save_json(path, obj):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=1)
    os.replace(tmp, path)


def read_jsonl(path):
    if not os.path.exists(path):
        return []
    rows = []
    with open(path, encoding="utf-8") as f:
        for n, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError as e:
                raise Stop(f"{path} 第 {n} 行不是合法 JSON：{e}")
    return rows


def write_jsonl(path, rows):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    os.replace(tmp, path)


def append_jsonl(path, rows):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "a", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")


def read_text(path, default=""):
    if not os.path.exists(path):
        return default
    with open(path, encoding="utf-8") as f:
        return f.read()


def write_text(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(text)
    os.replace(tmp, path)


def sha(text):
    return hashlib.sha256((text or "").encode("utf-8")).hexdigest()[:16]


def file_sha(path):
    return sha(read_text(path)) if os.path.exists(path) else "absent"


def deep_merge(base, over):
    out = json.loads(json.dumps(base))
    for k, v in (over or {}).items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = deep_merge(out[k], v)
        else:
            out[k] = v
    return out


def load_config():
    return deep_merge(DEFAULTS, load_json(H("config.json"), {}))


def badcase_source(cfg):
    """BadCase 母表定位：环境变量优先，其次 config.json 的 sources。
    环境变量：HAOHAO_EVAL_BADCASE_BASE（多维表 base）/ HAOHAO_EVAL_BADCASE_TABLE（table）。
    换机器跑不想把作者自己的表 ID 写进 config.json 时设它们；都没有返回 ("", "")。"""
    src = cfg.get("sources", {})
    base = os.environ.get("HAOHAO_EVAL_BADCASE_BASE") or src.get("badcase_base") or ""
    table = os.environ.get("HAOHAO_EVAL_BADCASE_TABLE") or src.get("badcase_table") or ""
    return base, table


def load_state():
    path = H("state.json")
    if not os.path.exists(path):
        raise Stop("还没初始化。先跑：python3 scripts/loop.py init")
    try:
        st = load_json(path)
    except json.JSONDecodeError as e:
        raise Stop(f"状态文件 {path} 损坏（不是合法 JSON：{e}）。别手改它：先备份出来，"
                   f"把报错告诉作者，再删掉重跑 init 从状态文档恢复。")
    if st is None:
        raise Stop("还没初始化。先跑：python3 scripts/loop.py init")
    return st


def save_state(st):
    save_json(H("state.json"), st)


class Lock:
    """跨天状态机的粗粒度互斥锁。
    有意用 mtime 6 小时粗判而不是 fcntl 锁：平台（Mira）的数据目录每天都是全新容器，
    fcntl 锁跨不住「昨天那个进程」，留一个死锁文件反而永远跑不起来。6 小时判据意味着：
    一轮跑超过 6 小时才会被当成死锁清掉，正常一轮远短于此；真有并发就靠 Stop 提示人删文件。"""

    def __init__(self):
        self.path = H("loop.lock")

    def __enter__(self):
        os.makedirs(eval_home(), exist_ok=True)
        if os.path.exists(self.path):
            age = dt.datetime.now().timestamp() - os.path.getmtime(self.path)
            if age < 6 * 3600:
                raise Stop(f"另一个流程正在跑（{self.path}）。确认没有别的会话在跑，再删掉这个文件重试。")
            os.remove(self.path)
        with open(self.path, "w") as f:
            f.write(str(os.getpid()))
        return self

    def __exit__(self, *exc):
        if os.path.exists(self.path):
            os.remove(self.path)


def days_between(a, b):
    return (dt.date.fromisoformat(b) - dt.date.fromisoformat(a)).days


def log_author(today, text):
    """作者的回话执行过什么，日报里列出来，作者据此知道回话有没有被读到。"""
    append_jsonl(H("inbox.jsonl"), [{"date": today, "text": text}])


def pkg(name, default=None):
    return load_json(os.path.join(PKG_DATA, name), default if default is not None else [])


__all__ = [
    "SCRIPTS_DIR", "SKILL_DIR", "PKG_DATA", "set_data_root", "data_root", "lark_cmd", "skill_dir",
    "xdg_data", "eval_home", "shuohua_home", "published_path", "H", "run_dir", "today_str",
    "load_json", "save_json", "read_jsonl", "write_jsonl", "append_jsonl", "read_text", "write_text",
    "sha", "file_sha", "deep_merge", "load_config", "badcase_source", "load_state", "save_state",
    "Lock", "days_between", "log_author", "pkg", "read_json",
]
