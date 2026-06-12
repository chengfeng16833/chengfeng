from __future__ import annotations

import os
import re
import time
from collections.abc import Callable
from dataclasses import dataclass
from types import SimpleNamespace
from typing import Protocol

from PIL import Image

os.environ.setdefault("FLAGS_use_mkldnn", "0")
os.environ.setdefault("FLAGS_use_onednn", "0")
os.environ.setdefault("FLAGS_enable_pir_api", "0")
os.environ.setdefault("FLAGS_enable_pir_in_executor", "0")


@dataclass(frozen=True)
class OcrResult:
    text: str
    confidence: float


@dataclass(frozen=True)
class OcrLine:
    """A single detected text block with its bounding box (x1, y1, x2, y2),
    in the coordinate space of the image passed to read_lines()."""
    text: str
    confidence: float
    box: tuple[int, int, int, int]


class OcrEngine(Protocol):
    def read_text(self, image: Image.Image) -> OcrResult:
        raise NotImplementedError

    def read_lines(self, image: Image.Image) -> list[OcrLine]:
        raise NotImplementedError


class NoopOcrEngine:
    def read_text(self, image: Image.Image) -> OcrResult:
        return OcrResult(text="", confidence=0.0)

    def read_lines(self, image: Image.Image) -> list[OcrLine]:
        return []


class PaddleOcrEngine:
    def __init__(self, lang: str = "ch"):
        # Disable oneDNN/PIR paths that are fragile on some Windows CPU builds.
        os.environ.setdefault("FLAGS_use_mkldnn", "0")
        os.environ.setdefault("FLAGS_use_onednn", "0")
        os.environ.setdefault("FLAGS_enable_pir_api", "0")
        os.environ.setdefault("FLAGS_enable_pir_in_executor", "0")

        try:
            from paddleocr import PaddleOCR
        except ImportError as exc:
            raise RuntimeError("paddleocr is not installed") from exc

        self._engine = PaddleOCR(
            text_detection_model_name="PP-OCRv4_mobile_det",
            text_recognition_model_name="PP-OCRv4_mobile_rec",
            use_doc_orientation_classify=False,
            use_doc_unwarping=False,
            use_textline_orientation=False,
        )

    def read_text(self, image: Image.Image) -> OcrResult:
        import numpy as np

        result = self._engine.ocr(np.array(image))

        # PaddleOCR 3.5 returns OCRResult objects/dicts with rec_texts and rec_scores.
        if isinstance(result, list) and result and hasattr(result[0], "json"):
            data = result[0].json if isinstance(result[0].json, dict) else result[0].json()
            res = data.get("res", data)
            texts = [str(text) for text in res.get("rec_texts", []) if text]
            confidences = [float(score) for score in res.get("rec_scores", [])]
        elif isinstance(result, list) and result and isinstance(result[0], dict) and "rec_texts" in result[0]:
            texts = [str(text) for text in result[0].get("rec_texts", []) if text]
            confidences = [float(score) for score in result[0].get("rec_scores", [])]
        # PaddleOCR 3.x returns a list of dicts: [{"text": "...", "confidence": 0.99}, ...]
        elif isinstance(result, list) and result and isinstance(result[0], dict):
            texts = [item.get("text", "") for item in result if item.get("text")]
            confidences = [item.get("confidence", 0.0) for item in result if item.get("text")]
        # PaddleOCR 2.x returns nested lists: [[[bbox, (text, confidence)], ...]]
        elif isinstance(result, list) and result and isinstance(result[0], list):
            texts: list[str] = []
            confidences: list[float] = []
            for page in result or []:
                for line in page or []:
                    if len(line) < 2:
                        continue
                    text, confidence = line[1]
                    texts.append(str(text))
                    confidences.append(float(confidence))
        else:
            return OcrResult(text="", confidence=0.0)

        if not texts:
            return OcrResult(text="", confidence=0.0)
        return OcrResult(text=" ".join(texts), confidence=sum(confidences) / len(confidences))

    def read_lines(self, image: Image.Image) -> list[OcrLine]:
        """Return each detected text block with its bounding box.

        Lets callers locate text by position — needed for lists that scroll to
        arbitrary, non-row-aligned offsets, where fixed-region OCR reads only the
        sliced gaps between rows.
        """
        import numpy as np

        result = self._engine.ocr(np.array(image))
        res = None
        if isinstance(result, list) and result and hasattr(result[0], "json"):
            data = result[0].json if isinstance(result[0].json, dict) else result[0].json()
            res = data.get("res", data)
        elif isinstance(result, list) and result and isinstance(result[0], dict) and "rec_texts" in result[0]:
            res = result[0]
        if not isinstance(res, dict):
            return []

        texts = res.get("rec_texts") or []
        scores = res.get("rec_scores") or []
        boxes = res.get("rec_boxes")
        if boxes is None:
            boxes = res.get("rec_polys") or res.get("dt_polys")
        if boxes is None:
            return []

        lines: list[OcrLine] = []
        for i, text in enumerate(texts):
            if not text or i >= len(boxes):
                continue
            arr = np.array(boxes[i])
            if arr.ndim == 1 and arr.size >= 4:
                x1, y1, x2, y2 = int(arr[0]), int(arr[1]), int(arr[2]), int(arr[3])
            elif arr.ndim == 2 and arr.shape[0] >= 1:
                xs, ys = arr[:, 0], arr[:, 1]
                x1, y1, x2, y2 = int(xs.min()), int(ys.min()), int(xs.max()), int(ys.max())
            else:
                continue
            conf = float(scores[i]) if i < len(scores) else 0.0
            lines.append(OcrLine(text=str(text), confidence=conf, box=(x1, y1, x2, y2)))
        return lines


# ---------------------------------------------------------------------------
# WinRT (Windows.Media.Ocr) fast engine — optional dependency
# ---------------------------------------------------------------------------

# Windows OCR splits CJK text into single space-separated glyphs ("训 练" instead
# of "训练"), which breaks keyword matching downstream. Collapse spaces between
# adjacent CJK characters; keep spaces between latin words/digits.
_CJK_GAP_RE = re.compile(
    r"(?<=[㐀-䶿一-鿿豈-﫿])\s+(?=[㐀-䶿一-鿿豈-﫿])"
)


def _collapse_cjk_spaces(text: str) -> str:
    return _CJK_GAP_RE.sub("", text)


def _load_winrt_api() -> SimpleNamespace:
    """Import the WinRT OCR projection from either ``winsdk`` or ``winrt-*``.

    Both packages are optional (NOT in requirements.txt); callers must treat
    any exception from here as "fast engine unavailable".
    """
    try:
        from winsdk.windows.foundation import AsyncStatus
        from winsdk.windows.globalization import Language
        from winsdk.windows.graphics.imaging import BitmapPixelFormat, SoftwareBitmap
        from winsdk.windows.media.ocr import OcrEngine as WinOcrEngine
        from winsdk.windows.storage.streams import DataWriter
    except ImportError:
        from winrt.windows.foundation import AsyncStatus
        from winrt.windows.globalization import Language
        from winrt.windows.graphics.imaging import BitmapPixelFormat, SoftwareBitmap
        from winrt.windows.media.ocr import OcrEngine as WinOcrEngine
        from winrt.windows.storage.streams import DataWriter
    return SimpleNamespace(
        AsyncStatus=AsyncStatus,
        Language=Language,
        BitmapPixelFormat=BitmapPixelFormat,
        SoftwareBitmap=SoftwareBitmap,
        WinOcrEngine=WinOcrEngine,
        DataWriter=DataWriter,
    )


class WinRtOcrEngine:
    """Windows built-in OCR (Windows.Media.Ocr) — the "fast" hybrid path.

    Port of the source project's LightOCR/WinOCR: instant startup (no model
    download/load), good enough for hot-path region text reads. Notes:

    - Requires the optional ``winsdk`` (or ``winrt-Windows.Media.Ocr``) package
      plus an installed Windows OCR language pack. When either is missing the
      constructor raises ``RuntimeError`` (mirrors ``PaddleOcrEngine``) so
      factories can degrade gracefully. Importing this module never fails.
    - Windows OCR reports no confidence scores; non-empty reads are returned
      with confidence 1.0 (empty with 0.0) — same convention as the source,
      where fallback triggered on empty/parse-failure rather than score.
    """

    _LANG_TAGS = {
        "ch": ("zh-Hans", "zh-CN", "zh-Hant"),
        "en": ("en-US", "en-GB", "en"),
    }

    # Windows OCR rejects tiny bitmaps; upscale crops below this side length.
    _MIN_SIDE = 50

    def __init__(self, lang: str = "ch", timeout_seconds: float = 5.0):
        self._timeout = timeout_seconds
        try:
            self._api = _load_winrt_api()
        except Exception as exc:  # ImportError, OSError from broken installs, ...
            raise RuntimeError(
                "WinRT OCR is not available (install 'winsdk' or 'winrt-Windows.Media.Ocr')"
            ) from exc

        engine = None
        for tag in self._LANG_TAGS.get(lang, (lang,)):
            try:
                language = self._api.Language(tag)
                if self._api.WinOcrEngine.is_language_supported(language):
                    engine = self._api.WinOcrEngine.try_create_from_language(language)
                if engine is not None:
                    break
            except Exception:
                continue
        if engine is None:
            try:
                engine = self._api.WinOcrEngine.try_create_from_user_profile_languages()
            except Exception as exc:
                raise RuntimeError("WinRT OCR engine creation failed") from exc
        if engine is None:
            raise RuntimeError("WinRT OCR has no usable language pack installed")
        self._engine = engine

    def _recognize(self, image: Image.Image):
        """Run Windows OCR; returns (winrt OcrResult, upscale factor)."""
        rgba = image.convert("RGBA")
        scale = 1
        min_side = min(rgba.width, rgba.height)
        if min_side < 1:
            raise RuntimeError("WinRT OCR got an empty image")
        if min_side < self._MIN_SIDE:
            scale = (self._MIN_SIDE + min_side - 1) // min_side
            rgba = rgba.resize((rgba.width * scale, rgba.height * scale), Image.LANCZOS)

        writer = self._api.DataWriter()
        writer.write_bytes(rgba.tobytes())
        buffer = writer.detach_buffer()
        bitmap = self._api.SoftwareBitmap.create_copy_from_buffer(
            buffer, self._api.BitmapPixelFormat.RGBA8, rgba.width, rgba.height
        )

        op = self._engine.recognize_async(bitmap)
        deadline = time.monotonic() + self._timeout
        while op.status == self._api.AsyncStatus.STARTED:
            if time.monotonic() > deadline:
                try:
                    op.cancel()
                except Exception:
                    pass
                raise RuntimeError("WinRT OCR timed out")
            time.sleep(0.002)
        if op.status != self._api.AsyncStatus.COMPLETED:
            raise RuntimeError("WinRT OCR recognize_async failed")
        return op.get_results(), scale

    def read_text(self, image: Image.Image) -> OcrResult:
        result, _scale = self._recognize(image)
        text = _collapse_cjk_spaces(" ".join(line.text for line in result.lines).strip())
        return OcrResult(text=text, confidence=1.0 if text else 0.0)

    def read_lines(self, image: Image.Image) -> list[OcrLine]:
        result, scale = self._recognize(image)
        lines: list[OcrLine] = []
        for line in result.lines:
            words = list(line.words)
            if not words:
                continue
            x1 = min(word.bounding_rect.x for word in words)
            y1 = min(word.bounding_rect.y for word in words)
            x2 = max(word.bounding_rect.x + word.bounding_rect.width for word in words)
            y2 = max(word.bounding_rect.y + word.bounding_rect.height for word in words)
            text = _collapse_cjk_spaces(line.text.strip())
            if not text:
                continue
            lines.append(
                OcrLine(
                    text=text,
                    confidence=1.0,
                    box=(int(x1 / scale), int(y1 / scale), int(x2 / scale), int(y2 / scale)),
                )
            )
        return lines


# ---------------------------------------------------------------------------
# Hybrid engine — fast OCR on the hot path, detailed OCR for complex reads
# ---------------------------------------------------------------------------


_EMPTY_RESULT = OcrResult(text="", confidence=0.0)

# read_text() crops above this area skip the fast path and go straight to the
# detailed engine. The source project sent full-screen/calibration reads to the
# detailed engine and only hot-path *region* reads (live_loop caps those at
# 160k px^2) to the fast one; 640k px^2 keeps every region crop on the fast
# path while any full-frame read (2560x1440 = 3.7M px^2) routes detailed.
DEFAULT_FAST_MAX_AREA = 640_000


class HybridOcrEngine:
    """Fast OCR for the hot path + detailed OCR for complex reads.

    Port of ``HybridOCR`` from the source project (Starsavior-master
    ``src/recognition.py``), adapted to this project's ``OcrEngine`` protocol.
    Routing rules carried over from the source:

    - ``read_text()`` → **fast** engine (source: ``recognize()`` /
      ``recognize_region()`` → WinOCR). This is the per-frame hot path —
      screen detection and state reads on small region crops.
    - ``read_lines()`` → **detailed** engine (source: ``recognize_detailed()``
      → PP-OCRv4). The source's fast path returns no bounding boxes, so every
      bbox consumer used the detailed engine; same here, accuracy first.
    - ``read_text()`` on images larger than ``fast_max_area`` goes straight to
      the detailed engine (source routed full-screen/calibration reads to the
      detailed path). Pass ``fast_max_area=None`` to disable size routing.
    - Fallbacks (source trainer.py ran 方案1→方案3 cascades between engines):
      fast result empty / below ``fast_min_confidence`` / raised → retry with
      detailed; detailed ``read_lines`` failed or found nothing → retry with
      fast. When both paths fail, returns an empty result instead of raising,
      so one bad frame never kills the live loop.

    Both engines are injected (pass fakes in tests); use
    ``create_hybrid_ocr_engine()`` to assemble from whatever is installed.
    """

    def __init__(
        self,
        fast_engine: OcrEngine,
        detailed_engine: OcrEngine,
        *,
        fast_min_confidence: float = 0.5,
        fast_max_area: int | None = DEFAULT_FAST_MAX_AREA,
        fallback_on_empty: bool = True,
    ):
        self.fast_engine = fast_engine
        self.detailed_engine = detailed_engine
        self.fast_min_confidence = fast_min_confidence
        self.fast_max_area = fast_max_area
        # False = 「信空」: fast 正常执行但没读到字时直接返回空, 不回退 detailed。
        # 分类锚场景大多数区域本来就没字, 逐个回退 Paddle 确认空是纯浪费
        # (实测 timing: classify 占帧 68%/2.57s 的元凶)。精读 payload 用 True。
        self.fallback_on_empty = fallback_on_empty

    # -- internal: never let one engine's exception escape the hybrid --

    @staticmethod
    def _safe_read_text(engine: OcrEngine, image: Image.Image) -> OcrResult | None:
        try:
            return engine.read_text(image)
        except Exception:
            return None

    @staticmethod
    def _safe_read_lines(engine: OcrEngine, image: Image.Image) -> list[OcrLine] | None:
        try:
            return engine.read_lines(image)
        except Exception:
            return None

    def _is_large(self, image: Image.Image) -> bool:
        return self.fast_max_area is not None and image.width * image.height > self.fast_max_area

    # -- OcrEngine protocol --

    def read_text(self, image: Image.Image) -> OcrResult:
        if self._is_large(image):
            # Full-frame/oversized read: detailed first (source behavior),
            # fast only as a last resort if detailed is broken.
            detailed = self._safe_read_text(self.detailed_engine, image)
            if detailed is not None and detailed.text:
                return detailed
            fast = self._safe_read_text(self.fast_engine, image)
            if fast is not None and fast.text:
                return fast
            return detailed or fast or _EMPTY_RESULT

        fast = self._safe_read_text(self.fast_engine, image)
        if fast is not None and fast.text and fast.confidence >= self.fast_min_confidence:
            return fast
        if fast is not None and not fast.text and not self.fallback_on_empty:
            # 信空模式: fast 正常跑完且确实没字 → 这就是答案(空锚区域常态)。
            # 注意只信「空」; 低置信的非空文本仍走下面的精读回退(质量兜底)。
            return fast
        # Fast path empty, low-confidence, or errored → accuracy-first retry.
        detailed = self._safe_read_text(self.detailed_engine, image)
        if detailed is not None and detailed.text:
            return detailed
        if fast is not None and fast.text:
            # Detailed found nothing; low-confidence text beats no text.
            return fast
        return detailed or fast or _EMPTY_RESULT

    def read_lines(self, image: Image.Image) -> list[OcrLine]:
        detailed = self._safe_read_lines(self.detailed_engine, image)
        if detailed:
            return detailed
        # Source 方案3: detailed path failed → WinOCR fallback. Coarser boxes
        # (or none at all from a noop) still beat an empty answer.
        fast = self._safe_read_lines(self.fast_engine, image)
        if fast:
            return fast
        return detailed if detailed is not None else []


def create_hybrid_ocr_engine(
    *,
    lang: str = "ch",
    fast_min_confidence: float = 0.5,
    fast_max_area: int | None = DEFAULT_FAST_MAX_AREA,
    fast_factory: Callable[[], OcrEngine] | None = None,
    detailed_factory: Callable[[], OcrEngine] | None = None,
    verbose: bool = True,
) -> OcrEngine:
    """Assemble the best available OCR engine; never raises.

    Tries WinRT OCR as the fast engine and PaddleOCR as the detailed engine
    (both optional). Degrades gracefully:

    - both available  → ``HybridOcrEngine(fast, detailed)``
    - one available   → that single engine, unwrapped
    - none available  → ``NoopOcrEngine()``

    ``fast_factory`` / ``detailed_factory`` exist for dependency injection in
    tests and for callers that want different engines per path.

    Deviation from the source: the source lazy-loaded its detailed engine on
    first use; here both engines are built eagerly because availability must
    be known to assemble (and live_loop already builds PaddleOCR eagerly).
    """
    if fast_factory is None:
        fast_factory = lambda: WinRtOcrEngine(lang=lang)  # noqa: E731
    if detailed_factory is None:
        detailed_factory = lambda: PaddleOcrEngine(lang=lang)  # noqa: E731

    fast = _try_build_engine("fast (WinRT)", fast_factory, verbose)
    detailed = _try_build_engine("detailed (PaddleOCR)", detailed_factory, verbose)

    if fast is not None and detailed is not None:
        if verbose:
            print(
                f"hybrid OCR: fast={type(fast).__name__} detailed={type(detailed).__name__}"
            )
        return HybridOcrEngine(
            fast,
            detailed,
            fast_min_confidence=fast_min_confidence,
            fast_max_area=fast_max_area,
        )
    if detailed is not None:
        if verbose:
            print(f"hybrid OCR: fast path unavailable, using {type(detailed).__name__} only")
        return detailed
    if fast is not None:
        if verbose:
            print(f"hybrid OCR: detailed path unavailable, using {type(fast).__name__} only")
        return fast
    if verbose:
        print("warning: no OCR engine available, falling back to noop")
    return NoopOcrEngine()


def _try_build_engine(
    label: str, factory: Callable[[], OcrEngine], verbose: bool
) -> OcrEngine | None:
    try:
        return factory()
    except Exception as exc:
        if verbose:
            print(f"warning: {label} OCR engine unavailable ({exc})")
        return None
