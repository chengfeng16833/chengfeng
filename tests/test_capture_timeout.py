import threading
import unittest

from PIL import Image

from starsavior_trainer.capture import _run_capture_with_timeout


class CaptureTimeoutTests(unittest.TestCase):
    def test_run_capture_with_timeout_returns_capture_result(self) -> None:
        image = Image.new("RGB", (2, 2), "white")

        result = _run_capture_with_timeout(lambda: image, timeout_seconds=0.1)

        self.assertIs(result, image)

    def test_run_capture_with_timeout_returns_none_when_capture_blocks(self) -> None:
        started = threading.Event()
        release = threading.Event()

        def blocking_capture():
            started.set()
            release.wait(timeout=1.0)
            return Image.new("RGB", (2, 2), "black")

        result = _run_capture_with_timeout(blocking_capture, timeout_seconds=0.01)
        release.set()

        self.assertTrue(started.is_set())
        self.assertIsNone(result)

    def test_run_capture_with_timeout_returns_none_when_capture_raises(self) -> None:
        def broken_capture():
            raise RuntimeError("boom")

        self.assertIsNone(_run_capture_with_timeout(broken_capture, timeout_seconds=0.1))


if __name__ == "__main__":
    unittest.main()
