import json
import tempfile
import unittest
from pathlib import Path

from starsavior_trainer.event_profiles import (
    EventProfile,
    choose_event_by_profile,
    event_profile_name_for_build,
    load_event_profile,
)
from starsavior_trainer.models import EventOption, Rect


class EventProfileTests(unittest.TestCase):
    def test_maps_existing_build_profiles_to_master_event_profiles(self) -> None:
        self.assertEqual("attack", event_profile_name_for_build("power_focus"))
        self.assertEqual("speed", event_profile_name_for_build("focus_focus"))
        self.assertEqual("survival", event_profile_name_for_build("stamina_tank"))
        self.assertEqual("survival", event_profile_name_for_build("durability_focus"))
        self.assertEqual("survival", event_profile_name_for_build("protection_focus"))
        self.assertEqual("default", event_profile_name_for_build("balanced"))

    def test_loads_event_profile_entries(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            profile_dir = root / "events"
            profile_dir.mkdir()
            (profile_dir / "attack.json").write_text(
                json.dumps(
                    {
                        "events": [
                            {
                                "id": "free_time",
                                "event_name": "闲暇时间",
                                "status": "confirmed",
                                "recommended_option": 4,
                                "options": [
                                    {"index": 4, "keyword": "今天就这样好好休息吧", "alias": ["休息吧"]}
                                ],
                            }
                        ]
                    }
                ),
                encoding="utf-8",
            )

            profile = load_event_profile(root, "attack")

            self.assertEqual("attack", profile.name)
            self.assertEqual(1, len(profile.events))
            self.assertEqual("free_time", profile.events[0].id)
            self.assertEqual(4, profile.events[0].recommended_option)

    def test_chooses_recommended_option_by_event_title(self) -> None:
        profile = EventProfile.from_dict(
            "attack",
            {
                "events": [
                    {
                        "id": "free_time",
                        "event_name": "闲暇时间",
                        "status": "confirmed",
                        "recommended_option": 4,
                        "options": [],
                    }
                ]
            },
        )
        options = [
            EventOption("一起去吃限定甜点吧", Rect(10, 10, 20, 20), event_title="旅程事件 闲暇时间"),
            EventOption("一起去看新上映的电影吧", Rect(40, 40, 20, 20), event_title="旅程事件 闲暇时间"),
            EventOption("我们去露营吧", Rect(70, 70, 20, 20), event_title="旅程事件 闲暇时间"),
            EventOption("今天就这样好好休息吧", Rect(100, 100, 20, 20), event_title="旅程事件 闲暇时间"),
        ]

        chosen = choose_event_by_profile(options, profile)

        self.assertIsNotNone(chosen)
        self.assertEqual(options[3], chosen.option)
        self.assertEqual("free_time", chosen.event_id)

    def test_chooses_event_by_option_aliases_when_title_is_missing(self) -> None:
        profile = EventProfile.from_dict(
            "attack",
            {
                "events": [
                    {
                        "id": "rescue_supply",
                        "event_name": "拯救集团供应",
                        "status": "confirmed",
                        "recommended_option": 1,
                        "options": [
                            {"index": 1, "keyword": "让我们选择食物", "alias": ["营养剂", "选择食物"]},
                            {"index": 2, "keyword": "让我们选择一个蓬松的枕头", "alias": ["枕头"]},
                        ],
                    }
                ]
            },
        )
        options = [
            EventOption("选营养剂吧", Rect(10, 10, 20, 20)),
            EventOption("选蓬松的枕头吧", Rect(40, 40, 20, 20)),
        ]

        chosen = choose_event_by_profile(options, profile)

        self.assertIsNotNone(chosen)
        self.assertEqual(options[0], chosen.option)
        self.assertEqual("营养剂", chosen.keyword)

    def test_project_profile_matches_real_master_event_data(self) -> None:
        root = Path(__file__).resolve().parents[1] / "config" / "profiles"
        profile = load_event_profile(root, "attack")
        options = [
            EventOption("一起去吃限定甜点吧", Rect(10, 10, 20, 20), event_title="旅程事件 闲暇时间"),
            EventOption("一起去看新上映的电影吧", Rect(40, 40, 20, 20), event_title="旅程事件 闲暇时间"),
            EventOption("我们去露营吧", Rect(70, 70, 20, 20), event_title="旅程事件 闲暇时间"),
            EventOption("今天就这样好好休息吧", Rect(100, 100, 20, 20), event_title="旅程事件 闲暇时间"),
        ]

        chosen = choose_event_by_profile(options, profile)

        self.assertIsNotNone(chosen)
        self.assertEqual(options[3], chosen.option)


if __name__ == "__main__":
    unittest.main()
