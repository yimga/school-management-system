"""Unit tests for ``generate_companion_extension_icons.py``.

Stdlib-only (``unittest`` + ``tempfile``); no Django, no pytest fixtures
— this is a pure script test that runs anywhere Python runs.
"""

from __future__ import annotations

import importlib
import pathlib
import sys
import tempfile
import unittest


HERE = pathlib.Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

# Imported by module name to keep this test runnable from any cwd.
gen = importlib.import_module("generate_companion_extension_icons")


PNG_MAGIC = b"\x89PNG\r\n\x1a\n"


class IconGeneratorTests(unittest.TestCase):
    def _generate_into(self, out_dir: pathlib.Path, monogram: str = "RMC") -> None:
        rc = gen.main(["--out", str(out_dir), "--monogram", monogram])
        self.assertEqual(rc, 0)

    def test_three_sizes_generated(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            out = pathlib.Path(tmp)
            self._generate_into(out)
            for size in (16, 48, 128):
                self.assertTrue(
                    (out / f"icon-{size}.png").is_file(),
                    f"icon-{size}.png not written",
                )

    def test_png_magic_header_present(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            out = pathlib.Path(tmp)
            self._generate_into(out)
            for size in (16, 48, 128):
                data = (out / f"icon-{size}.png").read_bytes()
                self.assertEqual(
                    data[: len(PNG_MAGIC)],
                    PNG_MAGIC,
                    f"PNG magic missing in icon-{size}.png",
                )

    def test_file_size_sane(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            out = pathlib.Path(tmp)
            self._generate_into(out)
            for size in (16, 48, 128):
                n = (out / f"icon-{size}.png").stat().st_size
                self.assertGreater(n, 50, f"icon-{size}.png too small: {n}")
                self.assertLess(n, 5000, f"icon-{size}.png too large: {n}")

    def test_idempotent_byte_identical(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            out = pathlib.Path(tmp)
            self._generate_into(out)
            first = {
                size: (out / f"icon-{size}.png").read_bytes()
                for size in (16, 48, 128)
            }
            # Run again into the same directory; bytes should match.
            self._generate_into(out)
            for size in (16, 48, 128):
                second = (out / f"icon-{size}.png").read_bytes()
                self.assertEqual(
                    first[size],
                    second,
                    f"icon-{size}.png not byte-identical across runs",
                )

    def test_different_monograms_produce_different_output(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_a, tempfile.TemporaryDirectory() as tmp_b:
            out_a = pathlib.Path(tmp_a)
            out_b = pathlib.Path(tmp_b)
            self._generate_into(out_a, monogram="FOO")
            self._generate_into(out_b, monogram="BAR")
            # At least one size must differ; PNG of FOO != PNG of BAR.
            any_diff = False
            for size in (16, 48, 128):
                a = (out_a / f"icon-{size}.png").read_bytes()
                b = (out_b / f"icon-{size}.png").read_bytes()
                if a != b:
                    any_diff = True
                    break
            self.assertTrue(
                any_diff,
                "FOO and BAR monograms produced byte-identical icons",
            )

    def test_render_monogram_png_returns_valid_png(self) -> None:
        data = gen.render_monogram_png(48, "RMC")
        self.assertTrue(data.startswith(PNG_MAGIC))
        # IEND chunk is the final 12 bytes: length(4)+type(4)+crc(4).
        self.assertEqual(data[-8:-4], b"IEND")

    def test_render_rejects_invalid_inputs(self) -> None:
        with self.assertRaises(ValueError):
            gen.render_monogram_png(0, "R")
        with self.assertRaises(ValueError):
            gen.render_monogram_png(16, "")


if __name__ == "__main__":
    unittest.main()
