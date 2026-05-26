from __future__ import annotations

import argparse
import json
from pathlib import Path

from starsavior_trainer.classifier import classify_by_filename
from starsavior_trainer.fixtures import demo_observations, demo_state
from starsavior_trainer.manifest import load_manifest
from starsavior_trainer.models import Action, GameState, Observation
from starsavior_trainer.policy import TrainerPolicy
from starsavior_trainer.regions import load_region_profile


def main() -> None:
    parser = argparse.ArgumentParser(description="Run Starsavior decisions against offline observations.")
    parser.add_argument("--manifest", help="JSON file containing labeled observations.")
    parser.add_argument("--screenshots", help="Directory of screenshots to classify by filename for now.")
    parser.add_argument("--profile", help="Region profile JSON to validate and report.")
    parser.add_argument("--demo", action="store_true", help="Run built-in demo observations.")
    parser.add_argument("--jsonl", action="store_true", help="Print decisions as JSON lines.")
    args = parser.parse_args()

    if args.profile:
        profile = load_region_profile(args.profile)
        print(f"profile={profile.name} resolution={profile.resolution[0]}x{profile.resolution[1]} regions={len(profile.regions)}")

    state, observations = _load_inputs(args)
    policy = TrainerPolicy()
    for index, observation in enumerate(observations, start=1):
        action = policy.decide(state, observation)
        if args.jsonl:
            print(json.dumps(_record(index, observation, action), ensure_ascii=False))
        else:
            _print_human(index, observation, action)


def _load_inputs(args: argparse.Namespace) -> tuple[GameState, list[Observation]]:
    if args.manifest:
        return load_manifest(args.manifest)
    if args.screenshots:
        paths = sorted(
            path
            for path in Path(args.screenshots).iterdir()
            if path.suffix.lower() in {".png", ".jpg", ".jpeg", ".bmp", ".webp"}
        )
        return GameState(), [classify_by_filename(path) for path in paths]
    return demo_state(), demo_observations()


def _record(index: int, observation: Observation, action: Action) -> dict[str, object]:
    return {
        "index": index,
        "source": observation.source,
        "screen": observation.screen.value,
        "screen_confidence": observation.confidence,
        "action": action.kind,
        "target": _target(action),
        "action_confidence": action.confidence,
        "reason": action.reason,
    }


def _target(action: Action) -> dict[str, int] | None:
    if action.target is None:
        return None
    return {
        "x": action.target.x,
        "y": action.target.y,
        "width": action.target.width,
        "height": action.target.height,
        "center_x": action.target.center[0],
        "center_y": action.target.center[1],
    }


def _print_human(index: int, observation: Observation, action: Action) -> None:
    print(f"{index:02d}. source={observation.source or '-'} screen={observation.screen.value} confidence={observation.confidence:.2f}")
    print(f"    action={action.kind} target={action.target} confidence={action.confidence:.2f}")
    print(f"    reason={action.reason}")


if __name__ == "__main__":
    main()
