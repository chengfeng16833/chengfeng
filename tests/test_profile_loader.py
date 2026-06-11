import json
import tempfile
import unittest
from pathlib import Path

from starsavior_trainer.profile_loader import (
    ProfileLoadError,
    ProfileRecord,
    load_profile,
    load_profiles,
)


class ProfileLoaderTests(unittest.TestCase):
    def test_loads_single_profile_with_kind_and_name(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            path = root / "training" / "attack.json"
            path.parent.mkdir()
            path.write_text(json.dumps({"rules": [{"name": "power"}]}), encoding="utf-8")

            record = load_profile(root, "training", "attack")

            self.assertEqual(
                ProfileRecord(kind="training", name="attack", path=path, data={"rules": [{"name": "power"}]}),
                record,
            )

    def test_loads_all_profiles_for_kind_sorted_by_name(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            profile_dir = root / "shop"
            profile_dir.mkdir()
            (profile_dir / "zeta.json").write_text(json.dumps({"items": []}), encoding="utf-8")
            (profile_dir / "alpha.json").write_text(json.dumps({"items": []}), encoding="utf-8")

            records = load_profiles(root, "shop")

            self.assertEqual(["alpha", "zeta"], [record.name for record in records])
            self.assertTrue(all(record.kind == "shop" for record in records))

    def test_rejects_unknown_profile_kind(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaisesRegex(ProfileLoadError, "Unsupported profile kind"):
                load_profiles(Path(tmp), "unknown")

    def test_rejects_missing_profile_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaisesRegex(ProfileLoadError, "Profile file not found"):
                load_profile(Path(tmp), "events", "missing")

    def test_rejects_malformed_json(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            path = root / "skills" / "broken.json"
            path.parent.mkdir()
            path.write_text("{broken", encoding="utf-8")

            with self.assertRaisesRegex(ProfileLoadError, "Invalid JSON"):
                load_profile(root, "skills", "broken")

    def test_rejects_non_object_profile(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            path = root / "training" / "list.json"
            path.parent.mkdir()
            path.write_text(json.dumps([]), encoding="utf-8")

            with self.assertRaisesRegex(ProfileLoadError, "must contain a JSON object"):
                load_profile(root, "training", "list")

    def test_project_contains_migrated_master_profile_sets(self) -> None:
        root = Path(__file__).resolve().parents[1] / "config" / "profiles"

        expected = {
            "training": {"attack", "default", "speed", "survival"},
            "events": {"attack", "default", "speed", "survival"},
            "shop": {"default", "speed"},
            "skills": {"attack", "default", "speed", "survival"},
        }
        for kind, names in expected.items():
            with self.subTest(kind=kind):
                records = load_profiles(root, kind)
                self.assertEqual(names, {record.name for record in records})


if __name__ == "__main__":
    unittest.main()
