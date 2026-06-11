import unittest

from starsavior_trainer.cli.live_loop import build_arg_parser, prejourney_config_from_args


class LiveLoopArgsTests(unittest.TestCase):
    def test_prejourney_args_default_to_safe_values(self) -> None:
        args = build_arg_parser().parse_args([])

        config = prejourney_config_from_args(args)

        self.assertEqual("default", config.difficulty)
        self.assertEqual("", config.character_name)
        self.assertEqual("", config.profession)
        self.assertEqual(1, config.imprint_slot_1_index)
        self.assertEqual(1, config.imprint_slot_2_index)
        self.assertEqual(1, config.support_deck)
        self.assertEqual("", config.friend_support_name)

    def test_prejourney_args_accept_explicit_values(self) -> None:
        args = build_arg_parser().parse_args(
            [
                "--difficulty",
                "困难",
                "--profession",
                "游侠",
                "--character",
                "艾黛",
                "--imprint-slot-1-index",
                "4",
                "--imprint-slot-2-index",
                "12",
                "--support-deck",
                "5",
                "--friend-support-name",
                "好友A",
            ]
        )

        config = prejourney_config_from_args(args)

        self.assertEqual("困难", config.difficulty)
        self.assertEqual("艾黛", config.character_name)
        self.assertEqual("游侠", config.profession)
        self.assertEqual(4, config.imprint_slot_1_index)
        self.assertEqual(12, config.imprint_slot_2_index)
        self.assertEqual(5, config.support_deck)
        self.assertEqual("好友A", config.friend_support_name)


if __name__ == "__main__":
    unittest.main()
