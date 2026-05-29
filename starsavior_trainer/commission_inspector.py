from __future__ import annotations

from dataclasses import dataclass, field

from starsavior_trainer.models import Action, CommissionChoice, GameState


@dataclass
class CommissionInspector:
    """Pick the highest-tier commission the character can still complete.

    The commission list shows only the tier name (低阶/中阶/高阶委托) per row; the
    numeric 建议综合等级 (suggested rank, e.g. RANK 17) shows only in the centre
    detail panel once a commission is SELECTED. So — like the training inspector —
    we CLICK each commission in turn to read its suggested rank, then accept the
    highest tier whose suggested rank is still ≤ our character rank.

    Fixes the old behaviour where every tier read as un-ranked (the list shows tier
    text, not a number) so the policy always fell back to the lowest tier.
    """

    records: dict[int, int] = field(default_factory=dict)  # option index -> suggested rank
    pending: int | None = None
    last_clicked: int | None = None
    # A commission whose 建议综合等级 is at most this many levels ABOVE our character
    # rank is still acceptable (doable for a slightly better reward); more than this
    # above is "too hard → pick another". (User: 大于当前等级3级就选其他委托.)
    rank_tolerance: int = 3

    def decide(self, choice: CommissionChoice, state: GameState | None = None) -> Action | None:
        options = choice.options
        # 0/1 commissions: nothing to compare — let the policy handle it (exit/accept).
        if len(options) < 2:
            self.reset()
            return None

        char_rank = choice.character_rank
        if char_rank is None and state is not None:
            char_rank = state.character_rank

        # Record the suggested rank of the commission we clicked last turn: clicking
        # it selected it, so the centre detail now shows its 建议综合等级.
        if self.pending is not None and choice.selected_suggested_rank is not None:
            self.records[self.pending] = choice.selected_suggested_rank
            self.pending = None

        # Without a character rank we can't judge doability — defer to the policy's
        # conservative fallback rather than guess.
        if char_rank is None:
            self.reset()
            return None

        # Inspect each not-yet-read commission by clicking it (reveals its rank).
        unseen = [i for i in range(len(options)) if i not in self.records]
        if unseen:
            idx = unseen[0]
            self.pending = idx
            self.last_clicked = idx
            return Action("click", options[idx].target, f"inspect commission: {options[idx].rank}")

        # All read. Take the highest-tier commission whose suggested rank is within
        # tolerance (≤ our rank + rank_tolerance); commissions more than tolerance
        # levels above us are too hard and skipped. If every one is too hard (rare),
        # take the easiest (lowest) so we still accept something completable.
        limit = char_rank + self.rank_tolerance
        doable = [(i, r) for i, r in self.records.items() if r <= limit]
        if doable:
            best_idx = max(doable, key=lambda item: item[1])[0]
        else:
            best_idx = min(self.records.items(), key=lambda item: item[1])[0]
        best = options[best_idx]

        # Two-step confirm (no reliance on a parsed selected name): if best is the
        # one we clicked last, accept it; otherwise select it first.
        if self.last_clicked == best_idx and choice.accept_button is not None:
            self.reset()
            return Action(
                "click",
                choice.accept_button,
                f"accept commission: {best.name} ({best.rank}, 建议≤角色RANK{char_rank})",
            )
        self.last_clicked = best_idx
        return Action("click", best.target, f"select commission: {best.name} ({best.rank})")

    def reset(self) -> None:
        self.records = {}
        self.pending = None
        self.last_clicked = None
