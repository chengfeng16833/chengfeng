import json
import tempfile
import unittest
from pathlib import Path

from starsavior_trainer.models import Rect, TrainingChoice
from starsavior_trainer.training_profiles import (
    TrainingProfile,
    TrainingProfileDecision,
    evaluate_training_profile,
    load_training_profile,
    training_profile_name_for_build,
)


def _choice(
    name: str,
    gain: int,
    fail: int | None = 0,
    *,
    selected: bool = False,
    back_button: Rect | None = None,
) -> TrainingChoice:
    return TrainingChoice(
        name=name,
        stat_gain=gain,
        ring="none",
        fail_rate=fail,
        target=Rect(gain, gain, 20, 20),
        selected=selected,
        confirm_button=Rect(900, 900, 20, 20),
        back_button=back_button,
    )


class TrainingProfileTests(unittest.TestCase):
    def test_maps_existing_build_profiles_to_master_training_profiles(self) -> None:
        self.assertEqual("attack", training_profile_name_for_build("power_focus"))
        self.assertEqual("speed", training_profile_name_for_build("focus_focus"))
        self.assertEqual("survival", training_profile_name_for_build("stamina_tank"))
        self.assertEqual("survival", training_profile_name_for_build("durability_focus"))
        self.assertEqual("survival", training_profile_name_for_build("protection_focus"))
        self.assertEqual("default", training_profile_name_for_build("balanced"))

    def test_loads_training_profile_rules(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            profile_dir = root / "training"
            profile_dir.mkdir()
            (profile_dir / "attack.json").write_text(
                json.dumps(
                    {
                        "legacy_strategy": {"build_direction": "attack", "fail_rate_threshold": 25},
                        "rules": [
                            {
                                "id": "adventure_any_gain",
                                "field": "any_gain",
                                "operator": ">=",
                                "value": 100,
                                "action": "train_best_gain",
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )

            profile = load_training_profile(root, "attack")

            self.assertEqual("attack", profile.name)
            self.assertEqual("attack", profile.build_direction)
            self.assertEqual(25, profile.fail_rate_threshold)
            self.assertEqual(1, len(profile.rules))
            self.assertEqual("train_best_gain", profile.rules[0].action)

    def test_high_priority_fail_rate_rule_requests_rest(self) -> None:
        profile = TrainingProfile.from_dict(
            "attack",
            {
                "legacy_strategy": {"build_direction": "attack", "fail_rate_threshold": 25},
                "rules": [
                    {"id": "rest_normal_fail", "field": "any_fail_rate", "operator": ">=", "value": 25, "action": "rest"}
                ],
            },
        )
        back = Rect(1, 2, 3, 4)

        decision = evaluate_training_profile(
            [_choice("power", 30, 25, back_button=back), _choice("stamina", 80, 5, back_button=back)],
            profile,
        )

        self.assertEqual(TrainingProfileDecision("rest", None, "rest_normal_fail"), decision)

    def test_best_gain_rule_selects_highest_gain_option(self) -> None:
        profile = TrainingProfile.from_dict(
            "attack",
            {
                "rules": [
                    {"id": "adventure_any_gain", "field": "any_gain", "operator": ">=", "value": 100, "action": "train_best_gain"}
                ]
            },
        )
        low = _choice("power", 60, 0)
        high = _choice("stamina", 120, 0)

        decision = evaluate_training_profile([low, high], profile)

        self.assertEqual(TrainingProfileDecision("train", high, "adventure_any_gain"), decision)

    def test_fallback_strength_rule_selects_power(self) -> None:
        profile = TrainingProfile.from_dict(
            "attack",
            {"rules": [{"id": "fallback_attack_strength", "action": "train_strength"}]},
        )
        power = _choice("power", 10, 0)
        stamina = _choice("stamina", 100, 0)

        decision = evaluate_training_profile([stamina, power], profile)

        self.assertEqual(TrainingProfileDecision("train", power, "fallback_attack_strength"), decision)

    def test_project_attack_profile_requests_rest_at_real_threshold(self) -> None:
        root = Path(__file__).resolve().parents[1] / "config" / "profiles"
        profile = load_training_profile(root, "attack")

        decision = evaluate_training_profile([_choice("power", 80, 25)], profile)

        self.assertEqual("rest", decision.kind)
        self.assertEqual("rest_normal_fail", decision.rule_id)


if __name__ == "__main__":
    unittest.main()
