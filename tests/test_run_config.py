import unittest

from starsavior_trainer.run_config import PreJourneyConfig


class PreJourneyConfigTests(unittest.TestCase):
    def test_defaults_are_stable(self) -> None:
        config = PreJourneyConfig()

        self.assertEqual("default", config.difficulty)
        self.assertEqual("", config.character_name)
        self.assertEqual("", config.profession)
        self.assertEqual(1, config.imprint_slot_1_index)
        self.assertEqual(1, config.imprint_slot_2_index)
        self.assertEqual(1, config.support_deck)
        self.assertEqual("", config.friend_support_name)
        self.assertEqual("力量", config.imprint_attribute())

    def test_support_and_tank_professions_use_stamina_attribute(self) -> None:
        for profession in ("辅助", "坦克"):
            with self.subTest(profession=profession):
                self.assertEqual("体力", PreJourneyConfig(profession=profession).imprint_attribute())

    def test_aidai_character_uses_guts_attribute_even_as_tank(self) -> None:
        self.assertEqual("韧性", PreJourneyConfig(character_name="艾黛", profession="坦克").imprint_attribute())

    def test_attack_professions_use_power_attribute(self) -> None:
        for profession in ("术师", "刺客", "战士", "游侠"):
            with self.subTest(profession=profession):
                self.assertEqual("力量", PreJourneyConfig(profession=profession).imprint_attribute())

    def test_explicit_values_are_preserved(self) -> None:
        config = PreJourneyConfig(
            difficulty="困难",
            character_name="艾黛",
            profession="游侠",
            imprint_slot_1_index=4,
            imprint_slot_2_index=12,
            support_deck=5,
            friend_support_name="好友A",
        )

        self.assertEqual("困难", config.difficulty)
        self.assertEqual("艾黛", config.character_name)
        self.assertEqual("游侠", config.profession)
        self.assertEqual(4, config.imprint_slot_1_index)
        self.assertEqual(12, config.imprint_slot_2_index)
        self.assertEqual(5, config.support_deck)
        self.assertEqual("好友A", config.friend_support_name)


if __name__ == "__main__":
    unittest.main()
