from __future__ import annotations

from dataclasses import dataclass, field

from starsavior_trainer.models import Action, BlessingChoice, BlessingOption, GameState


@dataclass
class BlessingChoiceInspector:
    """Inspect close blessing candidates through the right-side detail panel."""

    blessing_attribute_by_profile: dict[str, str]
    key: tuple[str, tuple[str, ...]] | None = None
    records: dict[str, int] = field(default_factory=dict)
    pending_name: str | None = None

    def decide(self, choice: BlessingChoice, state: GameState) -> Action | None:
        attribute = state.desired_blessing_attribute or self.blessing_attribute_by_profile.get(state.build_profile, "power")
        matching = [option for option in choice.options if option.attribute == attribute and option.value is not None]
        if len(matching) < 2:
            self.reset()
            return None

        # Attribute value is the primary criterion; sub-blessings only break a tie
        # between cards of the SAME top value. Lower-value cards never compete, so
        # a single clear top card needs no inspection — defer to the policy.
        best_value = max(option.value for option in matching if option.value is not None)
        candidates = sorted(
            [option for option in matching if option.value == best_value],
            key=lambda option: (option.target.y, option.target.x),
        )
        if len(candidates) < 2:
            self.reset()
            return None

        key = (attribute, tuple(option.name for option in candidates))
        if key != self.key:
            self.key = key
            self.records = {}
            self.pending_name = None

        if self.pending_name is not None and self.pending_name in {option.name for option in candidates}:
            self.records[self.pending_name] = choice.detail_sub_blessing_count
            self.pending_name = None

        unseen = [option for option in candidates if option.name not in self.records]
        if unseen:
            target = unseen[0]
            self.pending_name = target.name
            return Action("move", target.target, f"inspect {attribute} blessing {target.name}={target.value}")

        best = max(candidates, key=lambda option: (self.records.get(option.name, 0), -option.target.y, -option.target.x))
        if choice.selected_name == best.name and choice.confirm_button is not None:
            self.reset()
            return Action(
                "click",
                choice.confirm_button,
                f"confirm inspected {attribute} blessing: {best.name}={best.value}, sub_blessings={self.records.get(best.name, 0)}",
            )
        return Action(
            "click",
            best.target,
            f"choose inspected {attribute} blessing: {best.name}={best.value}, sub_blessings={self.records.get(best.name, 0)}",
        )

    def reset(self) -> None:
        self.key = None
        self.records = {}
        self.pending_name = None
