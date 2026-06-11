import unittest

from starsavior_trainer.cli.gui import append_prejourney_args


class GuiCommandArgsTests(unittest.TestCase):
    def test_appends_prejourney_args_to_live_loop_command(self) -> None:
        cmd = ["python", "-m", "starsavior_trainer.cli.live_loop"]

        append_prejourney_args(
            cmd,
            difficulty="困难",
            profession="游侠",
            imprint_slot_1_index="4",
            imprint_slot_2_index="12",
            support_deck="5",
            friend_support_name="好友A",
        )

        self.assertEqual(
            [
                "python",
                "-m",
                "starsavior_trainer.cli.live_loop",
                "--difficulty",
                "困难",
                "--profession",
                "游侠",
                "--imprint-slot-1-index",
                "4",
                "--imprint-slot-2-index",
                "12",
                "--support-deck",
                "5",
                "--friend-support-name",
                "好友A",
            ],
            cmd,
        )


if __name__ == "__main__":
    unittest.main()
