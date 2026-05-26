import unittest

from PIL import Image

from starsavior_trainer.models import Rect
from starsavior_trainer.regions import RegionProfile, scale_region_profile
from starsavior_trainer.vision import BlueButtonDetector, RingColorDetector


class RegionsAndVisionTest(unittest.TestCase):
    def test_rect_center(self) -> None:
        self.assertEqual(Rect(10, 20, 30, 40).center, (25, 40))

    def test_scale_region_profile_scales_rectangles_to_image_size(self) -> None:
        profile = RegionProfile("base", (2560, 1440), {"button": Rect(1280, 720, 256, 144)})

        scaled = scale_region_profile(profile, (1280, 720))

        self.assertEqual(scaled.resolution, (1280, 720))
        self.assertEqual(scaled.regions["button"], Rect(640, 360, 128, 72))

    def test_scale_region_profile_returns_original_for_same_size(self) -> None:
        profile = RegionProfile("base", (2560, 1440), {"button": Rect(1280, 720, 256, 144)})

        self.assertIs(scale_region_profile(profile, (2560, 1440)), profile)

    def test_ring_color_detector_finds_blue_region(self) -> None:
        image = Image.new("RGB", (50, 50), (20, 110, 240))

        signal = RingColorDetector().detect(image)

        self.assertEqual(signal.name, "blue")
        self.assertGreater(signal.confidence, 0.5)

    def test_blue_button_detector_finds_enabled_button(self) -> None:
        image = Image.new("RGB", (100, 40), (45, 140, 225))

        signal = BlueButtonDetector().detect(image)

        self.assertEqual(signal.name, "active_blue")
        self.assertGreater(signal.confidence, 0.5)

    def test_blue_button_detector_ignores_grey_button(self) -> None:
        image = Image.new("RGB", (100, 40), (70, 70, 70))

        signal = BlueButtonDetector().detect(image)

        self.assertEqual(signal.name, "inactive")


if __name__ == "__main__":
    unittest.main()
