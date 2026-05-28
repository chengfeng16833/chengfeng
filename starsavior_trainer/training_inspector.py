from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable

from starsavior_trainer.models import Action, GameState, TrainingChoice


@dataclass
class TrainingInspector:
    """Pick the best of the priority trainings by inspecting each one's preview gain.

    Support-card "heads" are randomised every turn, so a fixed bias can't tell
    which training is best *this* turn. The game only shows a training's stat
    gain (the +N bubbles on the left panel) once that training is SELECTED — so,
    like the blessing inspector, we CLICK each candidate (力量/体力/韧性), read its
    main gain, then confirm whichever gives the most (the player's "看那个加成最多").

    Internal stat keys map to the game's trainings as:
        power=力量  stamina=体力  guts=韧性  wisdom=专注  speed=保护
    """

    # The trainings worth comparing on a power run, top-to-bottom. 专注/保护
    # (命中/命抗) are skipped here — they're only worth it on high affinity, a
    # separate rule.
    inspect_attrs: tuple[str, ...] = ("power", "stamina", "guts")
    max_fail_rate: int = 30
    records: dict[str, int] = field(default_factory=dict)
    fails: dict[str, int] = field(default_factory=dict)
    pending: str | None = None
    last_clicked: str | None = None

    def decide(self, choices: Iterable[TrainingChoice], state: GameState | None = None) -> Action | None:
        choices = list(choices)
        candidates = [c for c in choices if c.name in self.inspect_attrs]
        if len(candidates) < 2:
            self.reset()
            return None

        # Record the gain/fail for the card we clicked last turn: clicking it
        # selected it, so its +N preview is now on the panel (and its 失败率 shows).
        selected = next((c for c in choices if c.selected), None)
        if self.pending is not None and selected is not None and selected.name == self.pending:
            self.records[self.pending] = selected.stat_gain
            self.fails[self.pending] = selected.fail_rate
            self.pending = None

        # Inspect each not-yet-seen candidate by clicking it (selects -> panel
        # shows its gain next turn).
        unseen = [c for c in candidates if c.name not in self.records]
        if unseen:
            target = unseen[0]
            self.pending = target.name
            self.last_clicked = target.name
            return Action("click", target.target, f"inspect training {target.name}")

        # All inspected. Among those with an acceptable fail rate, take the most
        # gain (ties -> the inspect_attrs order, i.e. 力量 > 体力 > 韧性).
        affordable = [c for c in candidates if self.fails.get(c.name, 0) <= self.max_fail_rate]
        if not affordable:
            # Every priority training is too risky (low stamina) — defer to the
            # policy, which routes back to the hub to rest.
            self.reset()
            return None
        order = {name: i for i, name in enumerate(self.inspect_attrs)}
        best = max(affordable, key=lambda c: (self.records.get(c.name, 0), -order.get(c.name, 99)))
        gain = self.records.get(best.name, 0)

        # Two-step confirm that does NOT depend on a parsed selected_name: if best
        # is already selected (we clicked it last), confirm; else select it first.
        if self.last_clicked == best.name and best.confirm_button is not None:
            self.reset()
            return Action("click", best.confirm_button, f"confirm training {best.name}: gain={gain}")
        self.last_clicked = best.name
        return Action("click", best.target, f"choose training {best.name}: gain={gain}")

    def reset(self) -> None:
        self.records = {}
        self.fails = {}
        self.pending = None
        self.last_clicked = None
