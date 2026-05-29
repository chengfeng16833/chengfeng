"""Tests for the F9 pause hotkey and the mouse-corner emergency stop."""
import sys
import types
import unittest
from unittest import mock

from starsavior_trainer.cli.live_loop import (
    PauseController,
    _is_corner_point,
    install_pause_hotkey,
)


class CornerStopTest(unittest.TestCase):
    """Robust emergency stop: cursor inside ANY corner region aborts the run.

    Unlike pyautogui's single-pixel FAILSAFE points (which need an exact landing
    pixel at the precise moment pyautogui is called), this checks a whole corner
    region at the top of every loop iteration — a quick mouse-slam to a corner
    reliably stops the bot regardless of DPI / exact pixel / OCR timing.
    """

    W, H, M = 2560, 1440, 120

    def test_all_four_corner_regions_trigger(self) -> None:
        for x, y in [
            (0, 0), (5, 5), (self.M, self.M),           # top-left region
            (self.W - 1, 0), (self.W - 5, 5),           # top-right
            (0, self.H - 1), (5, self.H - 5),           # bottom-left
            (self.W - 1, self.H - 1),                   # bottom-right
        ]:
            self.assertTrue(_is_corner_point(x, y, self.W, self.H, self.M), (x, y))

    def test_centre_and_edge_midpoints_do_not_trigger(self) -> None:
        # Centre and edge-midpoints (near only one axis) must NOT trigger, so the
        # bot's own clicks on UI elements never false-stop it.
        for x, y in [
            (self.W // 2, self.H // 2),                 # centre
            (self.W // 2, 5),                           # top edge midpoint
            (5, self.H // 2),                           # left edge midpoint
            (self.M + 1, self.M + 1),                   # just outside top-left region
            (self.W - self.M - 1, self.H - self.M - 1), # just outside bottom-right
        ]:
            self.assertFalse(_is_corner_point(x, y, self.W, self.H, self.M), (x, y))


class PauseControllerTest(unittest.TestCase):
    def test_initial_state_not_paused(self) -> None:
        self.assertFalse(PauseController().paused)

    def test_toggle_flips_state_and_returns_new_value(self) -> None:
        controller = PauseController()

        self.assertTrue(controller.toggle())   # not paused -> paused
        self.assertTrue(controller.paused)
        self.assertFalse(controller.toggle())  # paused -> resumed
        self.assertFalse(controller.paused)
        self.assertTrue(controller.toggle())    # resumed -> paused again

    def test_pause_and_resume_are_idempotent(self) -> None:
        controller = PauseController()

        controller.pause()
        controller.pause()
        self.assertTrue(controller.paused)

        controller.resume()
        controller.resume()
        self.assertFalse(controller.paused)


class InstallPauseHotkeyTest(unittest.TestCase):
    def test_success_binds_toggle_callback(self) -> None:
        recorded: dict[str, object] = {}

        def fake_add_hotkey(key, callback, trigger_on_release=False):
            recorded["key"] = key
            recorded["callback"] = callback
            recorded["trigger_on_release"] = trigger_on_release

        fake_keyboard = types.SimpleNamespace(add_hotkey=fake_add_hotkey)
        with mock.patch.dict(sys.modules, {"keyboard": fake_keyboard}):
            controller = PauseController()
            ok = install_pause_hotkey(controller, key="f12")

        self.assertTrue(ok)
        self.assertEqual(recorded["key"], "f12")
        # Must fire on key RELEASE, so a slightly-held press (OS key-repeat) can't
        # toggle the flag several times and land back where it started ("no effect").
        self.assertIs(recorded["trigger_on_release"], True)
        # the hotkey must be wired to the controller's toggle
        self.assertFalse(controller.paused)
        recorded["callback"]()  # type: ignore[operator]
        self.assertTrue(controller.paused)
        recorded["callback"]()  # type: ignore[operator]
        self.assertFalse(controller.paused)

    def test_default_key_is_f9_not_f12(self) -> None:
        # F12 is Steam's default screenshot key and gets swallowed before our global
        # hook sees it, so the pause hotkey defaults to F9 instead.
        recorded: dict[str, object] = {}

        def fake_add_hotkey(key, callback, trigger_on_release=False):
            recorded["key"] = key

        fake_keyboard = types.SimpleNamespace(add_hotkey=fake_add_hotkey)
        with mock.patch.dict(sys.modules, {"keyboard": fake_keyboard}):
            ok = install_pause_hotkey(PauseController())

        self.assertTrue(ok)
        self.assertEqual(recorded["key"], "f9")

    def test_missing_library_returns_false_without_raising(self) -> None:
        # A None entry in sys.modules makes ``import keyboard`` raise ImportError.
        with mock.patch.dict(sys.modules, {"keyboard": None}):
            controller = PauseController()
            ok = install_pause_hotkey(controller)

        self.assertFalse(ok)
        self.assertFalse(controller.paused)

    def test_registration_failure_returns_false_without_raising(self) -> None:
        def boom(key, callback):
            raise RuntimeError("need admin privileges to hook keyboard")

        fake_keyboard = types.SimpleNamespace(add_hotkey=boom)
        with mock.patch.dict(sys.modules, {"keyboard": fake_keyboard}):
            controller = PauseController()
            ok = install_pause_hotkey(controller)

        self.assertFalse(ok)
        self.assertFalse(controller.paused)


if __name__ == "__main__":
    unittest.main()
