# Master Migration Live Test Checklist

Date: 2026-06-08
Branch: `codex/master-capability-migration`

## Purpose

This checklist verifies the migrated `Starsavior-master` capabilities that cannot be fully proven offline:

- training profile rules
- event profile database fallback
- shop profile effect matching
- final skill learning
- PrintWindow capture timeout fallback

Do not enable new SendInput or HybridOCR work until this checklist is reasonably clean.

## Before Running

1. Restart the trainer process after pulling these changes. Python will not hot reload.
2. Use the normal GUI or live-loop command you already use.
3. Keep `execute` off for one dry-run pass if you want to inspect decisions first.
4. During real execution, keep the F9 pause hotkey and mouse-corner emergency stop in mind.

## Must-Watch Log Reasons

These messages prove the migrated pieces are active:

```text
training profile attack:adventure_any_gain
training profile ... return to hub to rest
event profile attack: ...
event profile speed: ...
event profile survival: ...
learn skill ... profile=attack
learn skill ... profile=speed
learn skill ... profile=survival
```

Shop profile matching may still show the existing buy reason, but it should buy effects like:

```text
效果 潜质10增加
潜质点数10增加
潜质点数 8 退还
```

It should not buy pure attribute-only effects just because they exist in the master shop database:

```text
效果 韧性5增加
效果 专注20增加
攻击力增加5%
```

## Training Checks

Pass conditions:

- If a visible inspected training has gain `>= 100`, the bot prefers the highest gain option.
- If the configured profile fail threshold is reached, the bot returns to hub and rests instead of looping training.
- If no training profile rule applies, the old `score=... ring=... fail=...` reason still appears.

Report back if:

- It rests too early while stamina is still healthy.
- It ignores an obviously high-gain training.
- It loops between hub and training select.

## Event Checks

Pass conditions:

- Known events can show `event db: ...` or `event profile ...`.
- Events with title OCR missing still use old safe keyword logic for fatigue-cost options.
- Fatigue-cost choices such as `用力量拔出来 疲劳值 70` are still avoided when a safer option exists.

Report back with screenshot/log if:

- It chooses a fatigue-cost option unexpectedly.
- It chooses the wrong option on a known master event.
- It pauses on an event whose options are clearly visible.

## Shop Checks

Pass conditions:

- The bot still inspects each shop row before buying.
- It buys stamina recovery or potential-point effects.
- It buys short OCR variants like `效果 潜质10增加`.
- It exits after one purchase, preserving the current safe one-buy-per-visit behavior.

Report back if:

- It buys attribute food/training books that you did not want.
- It misses a potential-point item.
- It gets stuck after buying.

## Final Skill Checks

Pass conditions:

- Mid-run skill pages still close immediately.
- After D-DAY trading is done and the final skill page appears, it learns by the skill profile priority.
- Attack build prefers `星光轨迹` when visible.

Report back if:

- It learns skills mid-run before the end.
- It exits the final skill page without learning.
- It repeatedly clicks the same already-learned skill.

## Capture Timeout Check

Pass conditions:

- The live loop should not hang forever on capture.
- If PrintWindow stalls, it should fall back instead of freezing the process.

Report back if:

- The console stops printing for more than 10 seconds while the game is responsive.
- Screenshots become black or stale repeatedly.

## Stop Point For Next Work

After this live checklist is clean, the next migration candidates are:

1. `SendInputExecutor`: better real click/keyboard delivery.
2. `HybridOCR/WinOCR`: faster OCR path.

Both directly affect live behavior and should be implemented only with real-game validation available.
