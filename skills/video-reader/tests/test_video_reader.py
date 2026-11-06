# -*- coding: utf-8 -*-
"""
video_frames.py 回归测试。
真视频用 ffmpeg testsrc 生成, 假视频用 PNG 改后缀; 子进程跑全链路验证退出码语义,
单元级 mock 验证装包确认闸门。素材全在 /tmp 临时目录, 不碰用户目录。

跑法:
    python3 -m unittest discover -s tests -v
"""
import importlib.util
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from PIL import Image

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "video_frames.py"
SPEC = importlib.util.spec_from_file_location("video_frames", SCRIPT)
VR = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(VR)

FFMPEG = shutil.which("ffmpeg")


def make_real_video(path: Path, duration=5, rate=10):
    subprocess.run(
        ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
         "-f", "lavfi", "-i", f"testsrc=duration={duration}:size=320x240:rate={rate}",
         "-pix_fmt", "yuv420p", str(path)],
        check=True)


def make_fake_video(path: Path):
    """PNG 改名 mp4: 能被 cv2.VideoCapture 打开, 但不是视频流。"""
    Image.new("RGB", (800, 600), "red").save(path.with_suffix(".png"))
    shutil.copyfile(path.with_suffix(".png"), path)


def run_script(*args):
    return subprocess.run([sys.executable, str(SCRIPT), *args],
                           capture_output=True, text=True, timeout=180)


class FakeVideoTests(unittest.TestCase):
    """P1-2: PNG 改名 mp4 不得再被当成'全静止视频' exit 0。"""

    def test_fake_video_exit2(self):
        if not FFMPEG:
            self.skipTest("ffmpeg 不可用")
        with tempfile.TemporaryDirectory() as d:
            fake = Path(d) / "fake.mp4"
            make_fake_video(fake)
            r = run_script("scan", str(fake))
            self.assertEqual(r.returncode, 2,
                             f"假视频必须 exit 2: rc={r.returncode}\n{r.stdout}\n{r.stderr}")
            self.assertIn("视频流", r.stderr)

    def test_real_video_exit0_and_json(self):
        if not FFMPEG:
            self.skipTest("ffmpeg 不可用")
        with tempfile.TemporaryDirectory() as d:
            v = Path(d) / "motion.mp4"
            make_real_video(v, duration=3)
            r = run_script("scan", str(v))
            self.assertEqual(r.returncode, 0, f"真视频应 exit 0: {r.stdout}\n{r.stderr}")
            data = json.loads(r.stdout)
            self.assertGreaterEqual(data["duration"], 2.0)
            self.assertEqual(data["resolution"], [320, 240])
            self.assertTrue(data["frames"], "真视频应至少抽出帧")


class FrameDirGovernanceTests(unittest.TestCase):
    """P1-1: --max-frames 截断; 默认保留+提示; --cleanup 成功退出才删。"""

    def setUp(self):
        if not FFMPEG:
            self.skipTest("ffmpeg 不可用")
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.video = self.root / "motion.mp4"
        make_real_video(self.video, duration=5)

    def tearDown(self):
        self._tmp.cleanup()

    def test_max_frames_truncates(self):
        # 5s × density 10 = 51 帧, 上限 10 → 截断为 10
        r = run_script("zoom", str(self.video), "--start", "0", "--end", "5",
                       "--density", "10", "--max-frames", "10")
        self.assertEqual(r.returncode, 0, r.stderr)
        data = json.loads(r.stdout)
        self.assertEqual(len(data["frames"]), 10,
                         f"应截断为 10 帧, 实际 {len(data['frames'])}")
        self.assertIn("截断", r.stderr)

    def test_default_keeps_dir_and_prints_hint(self):
        r = run_script("scan", str(self.video))
        self.assertEqual(r.returncode, 0, r.stderr)
        outdir = json.loads(r.stdout)["outdir"]
        self.assertTrue(os.path.isdir(outdir), "默认不自动删, 帧目录应保留")
        self.assertIn("可删除", r.stderr, "退出时应打印删除提示")

    def test_cleanup_deletes_only_temp_dir(self):
        r = run_script("scan", str(self.video), "--cleanup")
        self.assertEqual(r.returncode, 0, r.stderr)
        outdir = json.loads(r.stdout)["outdir"]
        self.assertFalse(os.path.exists(outdir), "--cleanup 成功退出后应删除自动临时目录")

    def test_explicit_outdir_never_cleaned(self):
        custom = self.root / "myframes"
        r = run_script("scan", str(self.video), "--outdir", str(custom), "--cleanup")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertTrue(custom.exists(), "--cleanup 绝不能删用户显式指定的 --outdir")


class PipGateTests(unittest.TestCase):
    """P1-3: 未设 VIDEO_READER_YES_PIP=1 不静默装包。"""

    def test_no_env_exits3_and_never_installs(self):
        with mock.patch.object(VR.importlib.util, "find_spec") as fs, \
             mock.patch.object(VR.subprocess, "run") as pr, \
             mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop("VIDEO_READER_YES_PIP", None)
            fs.return_value = None  # cv2/numpy 都"缺失"
            with self.assertRaises(SystemExit) as cm:
                VR._ensure_deps()
            self.assertEqual(cm.exception.code, 3)
            pr.assert_not_called(), "未设放行变量时绝不能触发 pip install"

    def test_env_set_allows_install_attempt(self):
        with mock.patch.object(VR.importlib.util, "find_spec") as fs, \
             mock.patch.object(VR.subprocess, "run") as pr, \
             mock.patch.dict(os.environ, {"VIDEO_READER_YES_PIP": "1"}):
            fs.return_value = None
            pr.return_value = mock.Mock(returncode=0)
            try:
                VR._ensure_deps()
            except SystemExit:
                pass  # mock 环境里装完仍 import 不到属预期, 关键是 install 被放行
            self.assertTrue(pr.called, "已设 VIDEO_READER_YES_PIP=1 应允许 pip install")
            self.assertIn("pip", " ".join(pr.call_args[0][0]))

    def test_transcribe_gate_exits4(self):
        from types import SimpleNamespace
        args = SimpleNamespace(video=str(SCRIPT), model="tiny", language=None)
        with mock.patch.object(VR.importlib.util, "find_spec") as fs, \
             mock.patch.object(VR.subprocess, "run") as pr, \
             mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop("VIDEO_READER_YES_PIP", None)
            fs.return_value = None  # whisper "缺失"
            with self.assertRaises(SystemExit) as cm:
                VR.cmd_transcribe(args)
            self.assertEqual(cm.exception.code, 4)
            pr.assert_not_called(), "transcribe 在未放行时也不能静默装 torch"


if __name__ == "__main__":
    unittest.main(verbosity=2)
