from __future__ import annotations

import os
from dataclasses import dataclass
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
