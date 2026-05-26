"""Tests for the F12 pause hotkey: state toggling and graceful registration."""
import sys
import types
import unittest
from unittest import mock

from starsavior_trainer.cli.live_loop import PauseController, install_pause_hotkey


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

        def fake_add_hotkey(key, callback):
            recorded["key"] = key
            recorded["callback"] = callback

        fake_keyboard = types.SimpleNamespace(add_hotkey=fake_add_hotkey)
        with mock.patch.dict(sys.modules, {"keyboard": fake_keyboard}):
            controller = PauseController()
            ok = install_pause_hotkey(controller, key="f12")

        self.assertTrue(ok)
        self.assertEqual(recorded["key"], "f12")
        # the hotkey must be wired to the controller's toggle
        self.assertFalse(controller.paused)
        recorded["callback"]()  # type: ignore[operator]
        self.assertTrue(controller.paused)
        recorded["callback"]()  # type: ignore[operator]
        self.assertFalse(controller.paused)

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
