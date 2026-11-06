# -*- coding: utf-8 -*-
"""
compress_images.py 回归测试。
全部在 /tmp 临时目录里造素材, 不碰用户目录; 通过子进程跑 main() 验证退出码语义、
原地覆盖护栏、--output-dir、坏缓存兜底、坏图持久化等 Agent 场景防呆行为。

跑法:
    python3 -m unittest discover -s tests -v      # 或
    python3 tests/test_compress_images.py -v
"""
import hashlib
import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from PIL import Image

MODULE_PATH = Path(__file__).resolve().parents[1] / "compress_images.py"
SPEC = importlib.util.spec_from_file_location("compress_images", MODULE_PATH)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def md5(p: Path) -> str:
    return hashlib.md5(p.read_bytes()).hexdigest()


def make_png(path: Path, size=(800, 600)):
    """画一张 UI 截图风格的图: 大色块+卡片文字条。实测这类图 pngquant 量化后
    体积稳定下降(2466B→847B), 避免渐变/纯噪点图导致 pngquant rc=98/99 放弃。"""
    from PIL import ImageDraw
    path.parent.mkdir(parents=True, exist_ok=True)
    w, h = size
    im = Image.new("RGB", size, (245, 245, 248))
    d = ImageDraw.Draw(im)
    d.rectangle([0, 0, w, 56], fill=(30, 120, 220))
    for i in range(12):
        y = 80 + i * 42
        d.rectangle([20, y, w - 20, y + 30], fill=(255, 255, 255))
        d.rectangle([36, y + 8, int(w * 0.6), y + 16], fill=(90, 90, 100))
        d.rectangle([36, y + 22, int(w * 0.4), y + 26], fill=(180, 180, 190))
    im.save(path)


def run_main(root: Path, *extra: str, expect=None):
    """子进程跑 compress_images.py, 返回 CompletedProcess。"""
    cmd = [sys.executable, str(MODULE_PATH), str(root), *extra]
    return subprocess.run(cmd, capture_output=True, text=True, timeout=300)


def git_init(root: Path):
    subprocess.run(["git", "init", "-q", str(root)], check=True)
    subprocess.run(["git", "-C", str(root), "config", "user.email", "t@t"], check=True)
    subprocess.run(["git", "-C", str(root), "config", "user.name", "t"], check=True)


class ExcludeRuleTests(unittest.TestCase):
    """P2-3: 构建产物目录只在顶层排除, 不再静默误杀嵌套同名资源目录。"""

    def test_top_level_build_excluded_but_nested_included(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d) / "App"
            top_build = root / "build" / "x.png"            # 顶层构建产物 → 排除
            nested_build = root / "Resources" / "build" / "y.png"  # 嵌套同名 → 保留
            icons = root / "Resources" / "build_icons" / "z.png"    # 合法资源目录 → 保留
            for p in (top_build, nested_build, icons):
                p.parent.mkdir(parents=True, exist_ok=True)
                Image.new("RGB", (8, 8)).save(p)

            found = {p.resolve() for p in MODULE.find_pngs(root)}
            self.assertNotIn(top_build.resolve(), found)
            self.assertIn(nested_build.resolve(), found, "嵌套 build/ 不应再被静默误杀")
            self.assertIn(icons.resolve(), found, "Resources/build_icons/ 应被处理")

    def test_extra_exclude_flag_works_any_depth(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d) / "App"
            keep = root / "a.png"
            junk = root / "tmp_out" / "j.png"
            keep.parent.mkdir(parents=True, exist_ok=True)
            junk.parent.mkdir(parents=True, exist_ok=True)
            Image.new("RGB", (8, 8)).save(keep)
            Image.new("RGB", (8, 8)).save(junk)
            found = {p.resolve() for p in MODULE.find_pngs(root, extra_exclude=frozenset({"tmp_out"}))}
            self.assertEqual(found, {keep.resolve()})


class ApngTests(unittest.TestCase):
    """旧行为保留: APNG 原样保护。"""

    def test_apng_is_kept_before_external_compression(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "spinner.png"
            Image.new("RGB", (16, 16), "red").save(
                path, save_all=True,
                append_images=[Image.new("RGB", (16, 16), "blue")],
                duration=[100, 100], loop=0,
            )
            self.assertEqual(MODULE.apng_frame_count(path), 2)
            result = MODULE.compress_one(path, Path("spinner.png"), set(), set(),
                                         False, False, {"hard_gate": True,
                                                         "quality_gate": True}, None)
            self.assertEqual(result["status"], "kept_animated")
            with Image.open(path) as im:
                self.assertEqual(im.n_frames, 2)


class GuardrailTests(unittest.TestCase):
    """P1-1: 非 git 目录原地覆盖默认拒绝; --output-dir 原图零改动。"""

    def test_non_git_dir_refused_exit1_and_untouched(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d) / "proj"
            img = root / "normal.png"
            make_png(img)
            before_md5 = md5(img)
            r = run_main(root)  # 不加 --allow-non-git, 非 git 目录
            self.assertNotEqual(r.returncode, 0,
                                f"非 git 目录原地覆盖必须被拒绝: rc={r.returncode}\n{r.stdout}\n{r.stderr}")
            self.assertEqual(r.returncode, 1, "护栏拒绝必须 exit 1")
            self.assertIn("git", r.stderr + r.stdout)
            self.assertIn("--output-dir", r.stderr + r.stdout)
            self.assertEqual(md5(img), before_md5, "被拒绝的运行不得改动任何文件")

    def test_git_dir_allows_in_place(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d) / "proj"
            img = root / "normal.png"
            make_png(img)
            git_init(root)
            before_md5 = md5(img)
            r = run_main(root)  # git 工作树内, 无需显式放行
            self.assertEqual(r.returncode, 0, f"git 工作树内应放行原地覆盖: {r.stdout}\n{r.stderr}")
            self.assertNotEqual(md5(img), before_md5, "git 工作树内应真实完成原地压缩")

    def test_output_dir_leaves_originals_untouched(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d) / "proj"
            img = root / "sub dir" / "我的 图片 .png"   # 含空格+中文名
            make_png(img)
            out = Path(d) / "out"
            before_md5 = md5(img)
            r = run_main(root, "--output-dir", str(out))
            self.assertEqual(r.returncode, 0, f"--output-dir 模式应成功: {r.stdout}\n{r.stderr}")
            self.assertEqual(md5(img), before_md5, "原图 md5 必须零改动")
            dest = out / "sub dir" / "我的 图片 .png"
            self.assertTrue(dest.exists(), f"副本应写到 {dest}")
            self.assertNotEqual(md5(dest), before_md5, "副本应是压缩后的产物")


class ExitCodeAndCacheTests(unittest.TestCase):
    """P1-2/P1-3/P2-1: 坏缓存不崩; 有图失败 exit 2; 坏图 hash 持久化二次跳过。"""

    def test_empty_dir_exit0(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d) / "empty"
            root.mkdir()
            r = run_main(root, "--allow-non-git")
            self.assertEqual(r.returncode, 0, f"空目录应正常退出: {r.stdout}\n{r.stderr}")

    def test_missing_dir_exit1(self):
        r = run_main("/nonexistent/path/xyz")
        self.assertEqual(r.returncode, 1)
        self.assertIn("目录不存在", r.stdout + r.stderr)

    def test_bad_cache_no_traceback_and_bak(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d) / "proj"
            make_png(root / "normal.png")
            cache = root / MODULE.CACHE_NAME
            cache.write_text("not-json{{{")  # 损坏缓存
            r = run_main(root, "--allow-non-git")
            combined = r.stdout + r.stderr
            self.assertNotIn("JSONDecodeError", combined, "坏缓存不得抛 traceback")
            self.assertIn("缓存文件", combined)
            self.assertTrue(cache.with_name(MODULE.CACHE_NAME + ".bak").exists(),
                            "坏缓存应改名为 .bak 保留证据")
            self.assertEqual(r.returncode, 0, f"坏缓存兜底后应正常跑完: {combined}")

    def test_broken_image_exit2_then_persisted_skip(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d) / "proj"
            make_png(root / "normal.png")
            broken = root / "broken.png"
            broken.write_bytes(b"\x89PNG\r\n\x1a\n" + b"garbage garbage garbage")
            r1 = run_main(root, "--allow-non-git")
            self.assertEqual(r1.returncode, 2,
                             f"有图解码失败必须 exit 2: rc={r1.returncode}\n{r1.stdout}\n{r1.stderr}")
            self.assertIn("[ERR]", r1.stdout)

            r2 = run_main(root, "--allow-non-git")
            self.assertEqual(r2.returncode, 0,
                             f"坏图已持久化, 第二次应 exit 0: rc={r2.returncode}\n{r2.stdout}\n{r2.stderr}")
            self.assertNotIn("[ERR]", r2.stdout, "第二次不得再刷坏图 stderr")
            self.assertIn("已知坏图", r2.stdout)

            r3 = run_main(root, "--allow-non-git", "--retry-errors")
            self.assertEqual(r3.returncode, 2, "--retry-errors 应重新检测坏图")


if __name__ == "__main__":
    unittest.main(verbosity=2)
