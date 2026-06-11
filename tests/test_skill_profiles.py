import json
import tempfile
import unittest
from pathlib import Path

from starsavior_trainer.models import Rect, SkillOption
from starsavior_trainer.skill_profiles import (
    SkillProfile,
    choose_skill_by_profile,
    load_skill_profile,
    skill_profile_name_for_build,
)


class SkillProfileTests(unittest.TestCase):
    def test_maps_existing_build_profiles_to_master_skill_profiles(self) -> None:
        self.assertEqual("attack", skill_profile_name_for_build("power_focus"))
        self.assertEqual("speed", skill_profile_name_for_build("focus_focus"))
        self.assertEqual("survival", skill_profile_name_for_build("stamina_tank"))
        self.assertEqual("survival", skill_profile_name_for_build("durability_focus"))
        self.assertEqual("survival", skill_profile_name_for_build("protection_focus"))
        self.assertEqual("default", skill_profile_name_for_build("balanced"))

    def test_loads_master_skill_profile_entries(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            profile_dir = root / "skills"
            profile_dir.mkdir()
            (profile_dir / "attack.json").write_text(
                json.dumps(
                    {
                        "skills": [
                            {"name": "星光轨迹", "priority": 10, "keywords": ["星光轨迹", "星光"]},
                            {"name": "攻击技巧", "priority": 1, "keywords": ["攻击技巧"]},
                        ]
                    }
                ),
                encoding="utf-8",
            )

            profile = load_skill_profile(root, "attack")

            self.assertEqual("attack", profile.name)
            self.assertEqual(2, len(profile.entries))
            self.assertEqual("星光轨迹", profile.entries[0].name)
            self.assertEqual(10, profile.entries[0].priority)
            self.assertEqual(("星光轨迹", "星光"), profile.entries[0].keywords)

    def test_choose_skill_by_profile_uses_highest_priority_keyword_match(self) -> None:
        low = SkillOption("攻击技巧", cost=10, target=Rect(10, 10, 20, 20))
        high = SkillOption("星光轨迹-3号", cost=200, target=Rect(40, 40, 20, 20))
        profile = SkillProfile.from_dict(
            "attack",
            {
                "skills": [
                    {"name": "攻击技巧", "priority": 1, "keywords": ["攻击技巧"]},
                    {"name": "星光轨迹", "priority": 10, "keywords": ["星光轨迹", "星光"]},
                ]
            },
        )

        chosen = choose_skill_by_profile([low, high], profile)

        self.assertIsNotNone(chosen)
        self.assertEqual(high, chosen.option)
        self.assertEqual("星光轨迹", chosen.skill_name)
        self.assertEqual(10, chosen.priority)

    def test_choose_skill_by_profile_ignores_learned_and_missing_targets(self) -> None:
        learned = SkillOption("已习得 星光轨迹", cost=10, target=Rect(10, 10, 20, 20))
        missing = SkillOption("星光轨迹", cost=10, target=None)
        fallback = SkillOption("攻击技巧", cost=10, target=Rect(40, 40, 20, 20))
        profile = SkillProfile.from_dict(
            "attack",
            {
                "skills": [
                    {"name": "星光轨迹", "priority": 10, "keywords": ["星光轨迹"]},
                    {"name": "攻击技巧", "priority": 1, "keywords": ["攻击技巧"]},
                ]
            },
        )

        chosen = choose_skill_by_profile([learned, missing, fallback], profile)

        self.assertIsNotNone(chosen)
        self.assertEqual(fallback, chosen.option)

    def test_project_attack_profile_matches_real_master_skill_data(self) -> None:
        root = Path(__file__).resolve().parents[1] / "config" / "profiles"
        profile = load_skill_profile(root, "attack")
        options = [
            SkillOption("攻击技巧", cost=10, target=Rect(10, 10, 20, 20)),
            SkillOption("星光轨迹-9号", cost=200, target=Rect(40, 40, 20, 20)),
        ]

        chosen = choose_skill_by_profile(options, profile)

        self.assertIsNotNone(chosen)
        self.assertEqual(options[1], chosen.option)
        self.assertEqual("星光轨迹", chosen.skill_name)


if __name__ == "__main__":
    unittest.main()
