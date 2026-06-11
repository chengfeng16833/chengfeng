"""Tests for HybridOcrEngine routing/fallback and the availability factory.

All OCR engines here are fakes — no winsdk/winrt or paddle is touched, so the
suite runs identically with or without the optional dependencies installed.
"""
import importlib.util
import unittest

from PIL import Image

from starsavior_trainer.ocr import (
    DEFAULT_FAST_MAX_AREA,
    HybridOcrEngine,
    NoopOcrEngine,
    OcrLine,
    OcrResult,
    WinRtOcrEngine,
    create_hybrid_ocr_engine,
)


class FakeOcrEngine:
    """Recording fake with configurable results/exceptions per method."""

    def __init__(
        self,
        text: str = "",
        confidence: float = 1.0,
        lines: list[OcrLine] | None = None,
        text_error: Exception | None = None,
        lines_error: Exception | None = None,
    ):
        self.text = text
        self.confidence = confidence
        self.lines = lines if lines is not None else []
        self.text_error = text_error
        self.lines_error = lines_error
        self.read_text_images: list[Image.Image] = []
        self.read_lines_images: list[Image.Image] = []

    def read_text(self, image: Image.Image) -> OcrResult:
        self.read_text_images.append(image)
        if self.text_error is not None:
            raise self.text_error
        return OcrResult(text=self.text, confidence=self.confidence)

    def read_lines(self, image: Image.Image) -> list[OcrLine]:
        self.read_lines_images.append(image)
        if self.lines_error is not None:
            raise self.lines_error
        return list(self.lines)


def _img(width: int = 100, height: int = 40) -> Image.Image:
    return Image.new("RGB", (width, height), color=(30, 30, 30))


LINE = OcrLine(text="力量训练", confidence=0.9, box=(1, 2, 30, 12))


class HybridRoutingTest(unittest.TestCase):
    """该走 fast 的输入走 fast、该走 detailed 的走 detailed。"""

    def test_read_text_routes_to_fast_only(self) -> None:
        fast = FakeOcrEngine(text="训练", confidence=0.9)
        detailed = FakeOcrEngine(text="detailed")
        hybrid = HybridOcrEngine(fast, detailed)
        image = _img()

        result = hybrid.read_text(image)

        self.assertEqual(result.text, "训练")
        self.assertEqual(len(fast.read_text_images), 1)
        self.assertIs(fast.read_text_images[0], image)
        self.assertEqual(detailed.read_text_images, [])

    def test_read_lines_routes_to_detailed_only(self) -> None:
        fast = FakeOcrEngine(lines=[OcrLine(text="fast", confidence=1.0, box=(0, 0, 1, 1))])
        detailed = FakeOcrEngine(lines=[LINE])
        hybrid = HybridOcrEngine(fast, detailed)
        image = _img()

        lines = hybrid.read_lines(image)

        self.assertEqual(lines, [LINE])
        self.assertEqual(len(detailed.read_lines_images), 1)
        self.assertIs(detailed.read_lines_images[0], image)
        self.assertEqual(fast.read_lines_images, [])

    def test_read_text_large_image_routes_to_detailed(self) -> None:
        # 源项目: 全屏/校准读取直接走 detailed, fast 只服务小区域热路径。
        fast = FakeOcrEngine(text="fast")
        detailed = FakeOcrEngine(text="detailed")
        hybrid = HybridOcrEngine(fast, detailed, fast_max_area=10_000)

        result = hybrid.read_text(_img(200, 100))  # 20k px^2 > 10k

        self.assertEqual(result.text, "detailed")
        self.assertEqual(fast.read_text_images, [])
        self.assertEqual(len(detailed.read_text_images), 1)

    def test_read_text_full_frame_routes_to_detailed_with_defaults(self) -> None:
        fast = FakeOcrEngine(text="fast")
        detailed = FakeOcrEngine(text="detailed")
        hybrid = HybridOcrEngine(fast, detailed)

        result = hybrid.read_text(_img(2560, 1440))

        self.assertEqual(result.text, "detailed")
        self.assertEqual(fast.read_text_images, [])
        self.assertGreater(2560 * 1440, DEFAULT_FAST_MAX_AREA)

    def test_fast_max_area_none_disables_size_routing(self) -> None:
        fast = FakeOcrEngine(text="fast", confidence=0.9)
        detailed = FakeOcrEngine(text="detailed")
        hybrid = HybridOcrEngine(fast, detailed, fast_max_area=None)

        result = hybrid.read_text(_img(2560, 1440))

        self.assertEqual(result.text, "fast")
        self.assertEqual(detailed.read_text_images, [])


class HybridFallbackTest(unittest.TestCase):
    """fast 为空/低置信/抛错时自动回退 detailed。"""

    def test_empty_fast_falls_back_to_detailed(self) -> None:
        fast = FakeOcrEngine(text="", confidence=0.0)
        detailed = FakeOcrEngine(text="休息", confidence=0.8)
        hybrid = HybridOcrEngine(fast, detailed)

        result = hybrid.read_text(_img())

        self.assertEqual(result, OcrResult(text="休息", confidence=0.8))
        self.assertEqual(len(fast.read_text_images), 1)
        self.assertEqual(len(detailed.read_text_images), 1)

    def test_low_confidence_fast_falls_back_to_detailed(self) -> None:
        fast = FakeOcrEngine(text="训绁", confidence=0.2)  # 误识
        detailed = FakeOcrEngine(text="训练", confidence=0.95)
        hybrid = HybridOcrEngine(fast, detailed, fast_min_confidence=0.5)

        result = hybrid.read_text(_img())

        self.assertEqual(result.text, "训练")
        self.assertEqual(len(detailed.read_text_images), 1)

    def test_confidence_at_threshold_is_accepted_without_fallback(self) -> None:
        fast = FakeOcrEngine(text="ok", confidence=0.5)
        detailed = FakeOcrEngine(text="detailed")
        hybrid = HybridOcrEngine(fast, detailed, fast_min_confidence=0.5)

        result = hybrid.read_text(_img())

        self.assertEqual(result.text, "ok")
        self.assertEqual(detailed.read_text_images, [])

    def test_fast_exception_falls_back_to_detailed(self) -> None:
        fast = FakeOcrEngine(text_error=RuntimeError("winrt broke"))
        detailed = FakeOcrEngine(text="交易", confidence=0.7)
        hybrid = HybridOcrEngine(fast, detailed)

        result = hybrid.read_text(_img())

        self.assertEqual(result.text, "交易")

    def test_detailed_empty_keeps_low_confidence_fast_text(self) -> None:
        # detailed 没读到任何东西时, fast 的低置信文本好过空结果。
        fast = FakeOcrEngine(text="maybe", confidence=0.3)
        detailed = FakeOcrEngine(text="", confidence=0.0)
        hybrid = HybridOcrEngine(fast, detailed)

        result = hybrid.read_text(_img())

        self.assertEqual(result, OcrResult(text="maybe", confidence=0.3))

    def test_both_engines_fail_returns_empty_result_without_raising(self) -> None:
        fast = FakeOcrEngine(text_error=RuntimeError("fast down"))
        detailed = FakeOcrEngine(text_error=RuntimeError("detailed down"))
        hybrid = HybridOcrEngine(fast, detailed)

        result = hybrid.read_text(_img())

        self.assertEqual(result, OcrResult(text="", confidence=0.0))

    def test_large_image_detailed_failure_falls_back_to_fast(self) -> None:
        fast = FakeOcrEngine(text="rescued", confidence=0.9)
        detailed = FakeOcrEngine(text_error=RuntimeError("paddle down"))
        hybrid = HybridOcrEngine(fast, detailed, fast_max_area=10_000)

        result = hybrid.read_text(_img(200, 100))

        self.assertEqual(result.text, "rescued")

    def test_read_lines_detailed_exception_falls_back_to_fast(self) -> None:
        fast_lines = [OcrLine(text="fast", confidence=1.0, box=(0, 0, 5, 5))]
        fast = FakeOcrEngine(lines=fast_lines)
        detailed = FakeOcrEngine(lines_error=RuntimeError("paddle down"))
        hybrid = HybridOcrEngine(fast, detailed)

        lines = hybrid.read_lines(_img())

        self.assertEqual(lines, fast_lines)
        self.assertEqual(len(fast.read_lines_images), 1)

    def test_read_lines_detailed_empty_falls_back_to_fast(self) -> None:
        fast_lines = [OcrLine(text="fast", confidence=1.0, box=(0, 0, 5, 5))]
        fast = FakeOcrEngine(lines=fast_lines)
        detailed = FakeOcrEngine(lines=[])
        hybrid = HybridOcrEngine(fast, detailed)

        lines = hybrid.read_lines(_img())

        self.assertEqual(lines, fast_lines)

    def test_read_lines_both_fail_returns_empty_list(self) -> None:
        fast = FakeOcrEngine(lines_error=RuntimeError("fast down"))
        detailed = FakeOcrEngine(lines_error=RuntimeError("detailed down"))
        hybrid = HybridOcrEngine(fast, detailed)

        self.assertEqual(hybrid.read_lines(_img()), [])


class HybridFactoryTest(unittest.TestCase):
    """降级: 引擎构造失败/不可用时整体仍可用, 导入永不崩。"""

    def test_both_available_assembles_hybrid(self) -> None:
        fast = FakeOcrEngine(text="f")
        detailed = FakeOcrEngine(text="d")
        engine = create_hybrid_ocr_engine(
            fast_factory=lambda: fast,
            detailed_factory=lambda: detailed,
            fast_min_confidence=0.7,
            fast_max_area=123,
            verbose=False,
        )

        self.assertIsInstance(engine, HybridOcrEngine)
        self.assertIs(engine.fast_engine, fast)
        self.assertIs(engine.detailed_engine, detailed)
        self.assertEqual(engine.fast_min_confidence, 0.7)
        self.assertEqual(engine.fast_max_area, 123)

    def test_fast_unavailable_returns_detailed_unwrapped(self) -> None:
        detailed = FakeOcrEngine(text="d")

        def broken_fast():
            raise RuntimeError("winrt is not installed")

        engine = create_hybrid_ocr_engine(
            fast_factory=broken_fast, detailed_factory=lambda: detailed, verbose=False
        )

        self.assertIs(engine, detailed)

    def test_detailed_unavailable_returns_fast_unwrapped(self) -> None:
        fast = FakeOcrEngine(text="f")

        def broken_detailed():
            raise RuntimeError("paddleocr is not installed")

        engine = create_hybrid_ocr_engine(
            fast_factory=lambda: fast, detailed_factory=broken_detailed, verbose=False
        )

        self.assertIs(engine, fast)

    def test_none_available_returns_noop(self) -> None:
        def broken():
            raise RuntimeError("nothing installed")

        engine = create_hybrid_ocr_engine(
            fast_factory=broken, detailed_factory=broken, verbose=False
        )

        self.assertIsInstance(engine, NoopOcrEngine)
        # And the noop still satisfies the engine interface.
        self.assertEqual(engine.read_text(_img()), OcrResult(text="", confidence=0.0))
        self.assertEqual(engine.read_lines(_img()), [])

    def test_default_fast_factory_never_raises(self) -> None:
        # Exercises the real WinRtOcrEngine default path: with winsdk/winrt
        # missing it must degrade, never crash the caller.
        def broken_detailed():
            raise RuntimeError("skip heavy paddle init in tests")

        engine = create_hybrid_ocr_engine(detailed_factory=broken_detailed, verbose=False)

        self.assertTrue(callable(engine.read_text))
        self.assertTrue(callable(engine.read_lines))


_WINRT_INSTALLED = any(
    importlib.util.find_spec(name) is not None for name in ("winsdk", "winrt")
)


class WinRtEngineDegradationTest(unittest.TestCase):
    @unittest.skipIf(_WINRT_INSTALLED, "winsdk/winrt installed; constructor may succeed")
    def test_constructor_raises_runtime_error_when_unavailable(self) -> None:
        # Mirrors PaddleOcrEngine's contract: missing optional dependency is a
        # clean RuntimeError (caught by the factory), not an ImportError crash.
        with self.assertRaises(RuntimeError):
            WinRtOcrEngine()


class HybridInterfaceCompatibilityTest(unittest.TestCase):
    """返回结构与现有引擎一致 (OcrResult / list[OcrLine])。"""

    def test_read_text_returns_ocr_result_instance(self) -> None:
        hybrid = HybridOcrEngine(
            FakeOcrEngine(text="a", confidence=0.9), FakeOcrEngine(text="b")
        )
        result = hybrid.read_text(_img())

        self.assertIsInstance(result, OcrResult)
        self.assertIsInstance(result.text, str)
        self.assertIsInstance(result.confidence, float)

    def test_read_lines_returns_ocr_line_list(self) -> None:
        hybrid = HybridOcrEngine(FakeOcrEngine(), FakeOcrEngine(lines=[LINE]))
        lines = hybrid.read_lines(_img())

        self.assertIsInstance(lines, list)
        self.assertTrue(all(isinstance(line, OcrLine) for line in lines))
        self.assertEqual(lines[0].box, (1, 2, 30, 12))

    def test_hybrid_satisfies_engine_protocol_shape(self) -> None:
        hybrid = HybridOcrEngine(FakeOcrEngine(), FakeOcrEngine())
        for method in ("read_text", "read_lines"):
            self.assertTrue(callable(getattr(hybrid, method)))


if __name__ == "__main__":
    unittest.main()
