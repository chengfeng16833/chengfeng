import unittest

from starsavior_trainer.round_tracker import RoundTracker


class RoundTrackerTest(unittest.TestCase):
    """Counts journey rounds from the hub date ('N月X旬'); each change = +1 round."""

    def test_fresh_tracker_has_no_round(self) -> None:
        self.assertIsNone(RoundTracker().current_round)

    def test_first_date_seen_is_round_one(self) -> None:
        t = RoundTracker()
        self.assertEqual(t.observe_date("3月上旬"), 1)
        self.assertEqual(t.current_round, 1)

    def test_same_date_does_not_advance(self) -> None:
        t = RoundTracker()
        t.observe_date("3月上旬")
        self.assertEqual(t.observe_date("3月上旬"), 1)

    def test_each_date_change_advances_one(self) -> None:
        t = RoundTracker()
        rounds = [t.observe_date(d) for d in ("3月上旬", "3月中旬", "3月下旬", "4月上旬")]
        self.assertEqual(rounds, [1, 2, 3, 4])

    def test_month_digit_distinguishes_same_period(self) -> None:
        # 3月上旬 -> 4月上旬 is a real change even though both end in 上旬.
        t = RoundTracker()
        t.observe_date("3月上旬")
        self.assertEqual(t.observe_date("4月上旬"), 2)

    def test_unparseable_date_is_ignored(self) -> None:
        t = RoundTracker()
        self.assertIsNone(t.observe_date(None))
        self.assertIsNone(t.observe_date(""))
        self.assertIsNone(t.observe_date("月下旬"))  # missing the month digit
        self.assertEqual(t.observe_date("3月上旬"), 1)  # a good read still starts at 1

    def test_ocr_icon_noise_does_not_spuriously_advance(self) -> None:
        t = RoundTracker()
        self.assertEqual(t.observe_date("Q 3月上旬"), 1)  # search-icon OCR noise
        self.assertEqual(t.observe_date("3月上旬"), 1)  # same canonical date

    def test_reset_starts_a_new_journey(self) -> None:
        t = RoundTracker()
        t.observe_date("3月上旬")
        t.observe_date("3月中旬")
        self.assertEqual(t.current_round, 2)
        t.reset()
        self.assertIsNone(t.current_round)
        self.assertEqual(t.observe_date("3月上旬"), 1)


if __name__ == "__main__":
    unittest.main()
