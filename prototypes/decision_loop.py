"""PROTOTYPE: run the Starsavior decision loop without capture/clicking."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from starsavior_trainer.fixtures import demo_observations, demo_state
from starsavior_trainer.policy import TrainerPolicy


def main() -> None:
    state = demo_state()
    policy = TrainerPolicy()
    for index, observation in enumerate(demo_observations(), start=1):
        action = policy.decide(state, observation)
        print(f"{index:02d}. screen={observation.screen.value} confidence={observation.confidence:.2f}")
        print(f"    action={action.kind} target={action.target} confidence={action.confidence:.2f}")
        print(f"    reason={action.reason}")


if __name__ == "__main__":
    main()
