import importlib.util
import tempfile
import unittest
from pathlib import Path

from PIL import Image


MODULE_PATH = Path(__file__).resolve().parents[1] / "compress_images.py"
SPEC = importlib.util.spec_from_file_location("compress_images", MODULE_PATH)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class CompressImagesTests(unittest.TestCase):
    def test_scans_generic_tree_and_excludes_generated_directories(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir) / "AnyApp"
            included = root / "App" / "Assets.xcassets" / "Hero.imageset" / "hero.png"
            excluded = root / "Pods" / "Vendor" / "vendor.png"
            included.parent.mkdir(parents=True)
            excluded.parent.mkdir(parents=True)
            Image.new("RGB", (8, 8), "red").save(included)
            Image.new("RGB", (8, 8), "blue").save(excluded)

            self.assertEqual(list(MODULE.find_pngs(root)), [included])

    def test_apng_is_kept_before_external_compression(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "spinner.png"
            first = Image.new("RGB", (16, 16), "red")
            second = Image.new("RGB", (16, 16), "blue")
            first.save(
                path,
                save_all=True,
                append_images=[second],
                duration=[100, 100],
                loop=0,
            )

            self.assertEqual(MODULE.apng_frame_count(path), 2)
            for hard_gate in (True, False):
                with self.subTest(hard_gate=hard_gate):
                    result = MODULE.compress_one(
                        path,
                        cache_hashes=set(),
                        dry_run=False,
                        gate_cfg={"hard_gate": hard_gate, "quality_gate": True},
                    )
                    self.assertEqual(result["status"], "kept_animated")
            with Image.open(path) as image:
                self.assertEqual(image.n_frames, 2)


if __name__ == "__main__":
    unittest.main()
