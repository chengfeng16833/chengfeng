from __future__ import annotations

import argparse
import json

from starsavior_trainer.executor import DryRunExecutor, PyAutoGuiExecutor
from starsavior_trainer.manifest import load_manifest
from starsavior_trainer.policy import TrainerPolicy


def main() -> None:
    parser = argparse.ArgumentParser(description="Run decisions from a manifest and optionally execute clicks.")
    parser.add_argument("--manifest", required=True, help="JSON file containing labeled observations.")
    parser.add_argument("--execute-clicks", action="store_true", help="Actually click with pyautogui. Default is dry-run.")
    args = parser.parse_args()

    state, observations = load_manifest(args.manifest)
    policy = TrainerPolicy()
    executor = PyAutoGuiExecutor() if args.execute_clicks else DryRunExecutor()

    for index, observation in enumerate(observations, start=1):
        action = policy.decide(state, observation)
        result = executor.execute(action)
        print(
            json.dumps(
                {
                    "index": index,
                    "source": observation.source,
                    "screen": observation.screen.value,
                    "action": action.kind,
                    "point": result.point,
                    "executed": result.executed,
                    "reason": result.reason,
                },
                ensure_ascii=False,
            )
        )


if __name__ == "__main__":
    main()
