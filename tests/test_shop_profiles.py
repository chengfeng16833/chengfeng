import json
import tempfile
import unittest
from pathlib import Path

from starsavior_trainer.shop_profiles import (
    ShopProfile,
    load_shop_profile,
    shop_effect_worth_buying,
)


class ShopProfileTests(unittest.TestCase):
    def test_loads_shop_profile_entries(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            profile_dir = root / "shop"
            profile_dir.mkdir()
            (profile_dir / "speed.json").write_text(
                json.dumps(
                    {
                        "items": [
                            {
                                "id": "shop_potential",
                                "name": "潜质",
                                "type": "potential_points",
                                "keywords": ["潜质点数10增加"],
                                "effect_keys": ["潜质"],
                            }
                        ]
                    }
                ),
                encoding="utf-8",
            )

            profile = load_shop_profile(root, "speed")

            self.assertEqual("speed", profile.name)
            self.assertEqual(1, len(profile.items))
            self.assertEqual("shop_potential", profile.items[0].id)
            self.assertEqual("potential_points", profile.items[0].kind)

    def test_potential_points_effect_is_worth_buying_even_with_short_ocr(self) -> None:
        profile = ShopProfile.from_dict(
            "speed",
            {
                "items": [
                    {
                        "id": "shop_potential",
                        "name": "潜质",
                        "type": "potential_points",
                        "keywords": ["潜质点数10增加"],
                        "effect_keys": ["潜质"],
                    }
                ]
            },
        )

        self.assertTrue(shop_effect_worth_buying("效果 潜质10增加", profile))

    def test_item_name_alone_is_not_worth_buying(self) -> None:
        profile = ShopProfile.from_dict(
            "speed",
            {
                "items": [
                    {
                        "id": "shop_potential",
                        "name": "潜质",
                        "type": "potential_points",
                        "keywords": ["潜质点数10增加"],
                        "effect_keys": ["潜质"],
                    }
                ]
            },
        )

        self.assertFalse(shop_effect_worth_buying("商品名 潜质", profile))

    def test_non_potential_profile_items_are_not_auto_buy_signals(self) -> None:
        profile = ShopProfile.from_dict(
            "speed",
            {
                "items": [
                    {
                        "id": "shop_attr",
                        "name": "鸡排",
                        "type": "attribute_boost",
                        "keywords": ["韧性5增加"],
                        "effect_keys": ["韧性"],
                    }
                ]
            },
        )

        self.assertFalse(shop_effect_worth_buying("效果 韧性5增加", profile))

    def test_project_speed_profile_matches_real_potential_item(self) -> None:
        root = Path(__file__).resolve().parents[1] / "config" / "profiles"
        profile = load_shop_profile(root, "speed")

        self.assertTrue(shop_effect_worth_buying("效果 潜质点数10增加", profile))


if __name__ == "__main__":
    unittest.main()
