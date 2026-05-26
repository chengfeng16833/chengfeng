# Starsavior Trainer Design

## Goal

Build a PC-side Starsavior training assistant that reads one game window, identifies the current screen, chooses the next action, and clicks it.

This is not an emulator script. The design assumes the real PC client is visible and stable enough for screenshot-based OCR and computer vision.

## Core Loop

```text
capture screenshot
  -> classify screen
  -> extract observations
  -> decide action
  -> execute click
  -> wait for transition
  -> repeat
```

Every loop should produce a structured trace:

```text
screen=training_select confidence=0.91 action=train_speed reason="highest score, acceptable fail rate"
```

This trace is important because the script will make many small decisions, and bad behavior must be debuggable from logs instead of guessed from memory.

## Modules

| Module | Responsibility | First implementation |
| --- | --- | --- |
| Window capture | Find and screenshot the Starsavior window | `mss` or `dxcam`, crop to client area |
| Screen classifier | Decide which screen is visible | OCR anchors + template/color checks |
| Region map | Named rectangles for buttons, OCR zones, and color zones | Per-resolution JSON profile |
| OCR adapter | Return text and confidence for a region | PaddleOCR or EasyOCR behind one interface |
| Vision adapter | Detect color rings, red text, buttons, and highlight states | OpenCV HSV thresholds + templates |
| Game state | Current rank, coins, stamina, mood, turn, last action | In-memory state, updated from observations |
| Policy engine | Convert observations into ranked actions | Rule scoring with explainable weights |
| Click executor | Move/click/wait with safety checks | `pyautogui` or Windows input API |
| Logger | Save decisions, screenshots, and OCR text | JSONL + optional cropped debug images |

## Screen States

The controller should treat the game as a state machine, not a list of unrelated image checks.

| Screen state | Recognition anchors | Decision |
| --- | --- | --- |
| `initial` | Start button, title/menu layout | Click start |
| `character_select` | Header `旅程起点`, right-side character list, `选择` button | Pick configured character/build and click select |
| `blessing_setup` | Blessing slots with plus icons, auto-equip/confirm buttons | Open empty slot, or confirm when filled |
| `blessing_choice` | Blessing options with attribute and numeric value | Pick target attribute with highest value |
| `journey_start` | Arcana cards, auto journey button, `旅程起点` button | Ignore fixed Arcana and click journey start |
| `confirm_dialog` | Modal title/message plus cancel/confirm buttons | Click confirm when dialog is expected |
| `event_fast_forward_setting` | Three fast-forward option cards and `决定` button | Select `快转所有事件`, then confirm |
| `dialogue` | Skip button or dialogue text box | Click the skip button for the detected dialogue variant |
| `training_select` | Five training regions, fail-rate text, colored rings | Score five trainings and click best |
| `rest_submenu` | OCR text `冥想室`, `露宿`, coin amount | Coins >= 60 click `冥想室`, else `露宿` |
| `event_choice` | Multiple option buttons with OCR text | Pick by guide rule: recover > mood > attributes |
| `relic_choice` | Relic names and score/grade text | Pick highest score |
| `commission_select` | Red text, rank text, commission buttons | Match current rank and pick suitable commission |
| `shop` | Item names, prices, buy buttons | Buy whitelist items only |
| `region_move` | OCR/button text `移动` | Click move |
| `unknown` | Low confidence or conflicting anchors | Pause or take diagnostic screenshot |

## Observation Contracts

The policy engine should never read raw pixels directly. Each screen has a typed observation.

```text
TrainingChoice:
  name: speed | stamina | power | guts | wisdom
  stat_gain: number
  colored_ring: none | blue | gold | rainbow
  fail_rate: percent
  stamina_after_estimate: number
  rect: click target

RestSubmenu:
  coins: number
  has_meditation_room: boolean
  meditation_rect: click target
  rough_sleep_rect: click target

EventChoice:
  text: OCR text
  parsed_effects: recover | mood | attribute | unknown
  rect: click target
```

This boundary keeps OCR bugs separate from decision bugs.

## Decision Rules

### Training Selection

Initial scoring:

```text
score =
  stat_gain * 1.0
  + colored_ring_bonus
  - fail_rate_penalty
  + strategic_bias
```

`strategic_bias` comes from the selected character/build profile. The character-selection screen determines which attribute plan the run should follow.

Initial build profiles:

| Profile | Training bias |
| --- | --- |
| `balanced` | no extra bias |
| `power_focus` | power first, speed second |
| `focus_focus` | wisdom/focus first, speed second |
| `durability_focus` | stamina first, guts second |
| `stamina_tank` | stamina/HP first, protection second |
| `protection_focus` | guts/protection first, stamina second |

Default bonuses:

| Signal | Bonus |
| --- | ---: |
| rainbow ring | +40 |
| gold ring | +25 |
| blue ring | +10 |
| no ring | +0 |

Default failure penalty:

```text
if fail_rate <= 5:   penalty = 0
if fail_rate <= 15:  penalty = fail_rate * 1.5
if fail_rate <= 30:  penalty = fail_rate * 3
else:                disallow unless no safe action exists
```

Strategic bias should be configurable per character/build. Start with a neutral policy, then add build profiles later.

### Rest Submenu

```text
if coins >= 60 and "冥想室" is visible:
  click 冥想室
else:
  click 露宿
```

### Event Choices

Parse option text against a guide table. If no exact guide match exists:

```text
recover stamina > mood up > useful attribute gain > unknown
```

Unknown options should be logged with screenshot crops so the guide table can grow over time.

### Blessings

Blessing selection follows the selected character/build profile.

```text
target_attribute =
  desired_blessing_attribute
  or attribute mapped from build_profile
```

Rules:

1. For `power_focus`, choose power blessings.
2. For `focus_focus`, choose focus/wisdom blessings.
3. For `durability_focus`, choose stamina blessings.
4. For `protection_focus`, choose protection/guts blessings.
5. For `stamina_tank`, choose stamina/HP blessings.
6. Among matching blessings, choose the highest numeric value.
7. Each blessing can be up to 50.
8. Two blessing slots can total up to 100.
9. If two matching blessings have the same value, prefer the one with more sub-blessings.
10. If no matching blessing value is recognized, pause instead of guessing.

### Journey Start

Arcana cards on the journey-start screen are treated as fixed route setup for now.

```text
click 旅程起点
```

Do not edit Arcana automatically in the first implementation.

### Confirm Dialog

When a confirmation modal appears after a known action, click the blue confirm button.

Known example:

```text
title=入场确认
message=是否要进行旅程?
action=click 确认
```

### Event Fast-Forward Setting

Always choose `快转所有事件`.

```text
if selected_mode != all_events:
  click 快转所有事件
else:
  click 决定
```

### Dialogue Skipping

There are at least two dialogue layouts:

| Variant | Recognition | Action |
| --- | --- | --- |
| `intro_story` | Full-screen story background, top-right `SKIP` text | Click `dialogue_intro_skip_button` |
| `journey_hud` | Journey HUD visible, changed top-right control row | Click `dialogue_journey_skip_button` |

The policy should prefer the skip button from the observation payload. If no payload is available, it falls back to the default skip rectangle.

### Relics

The first relic reward is fixed:

```text
choose 烦人的布谷鸟时钟
```

After the first relic, pick the highest recognized score. If score is missing, use a relic-name tier list. If both are missing, pause or choose the visually highlighted/default option depending on safe mode.

### Commissions

Match current rank first, then prefer commission text with red highlighted suitability. If rank OCR is uncertain, choose the lowest-risk commission and log uncertainty.

### Shop

Only buy whitelist items. Each whitelist entry should include max price and optional phase/rank conditions.

```text
buy if item_name in whitelist and price <= max_price and conditions match
skip otherwise
```

### Region Movement

When `移动` is visible and the policy says movement is needed, click it. Movement should not happen just because the button exists; the state machine must know the current task is finished.

## Safety Model

1. Never click when screen confidence is below threshold.
2. Never click outside known button rectangles.
3. Before high-impact choices, require both screen classification and anchor OCR to agree.
4. Save screenshot and OCR trace for every unknown state.
5. Add a global hotkey to pause/stop.

## Implementation Phases

### Phase 1: Logic Prototype

Simulate observations and verify the state machine and policy outputs.

### Phase 2: Offline Vision Harness

Feed saved screenshots into OCR/CV extractors. No clicking.

### Phase 3: Assisted Clicker

Read live screen, propose action, require manual confirmation.

### Phase 4: Autonomous Loop

Enable automatic clicking with logs, pause hotkey, and conservative confidence thresholds.

## Open Questions

1. Target resolution and window mode.
2. OCR engine preference: PaddleOCR, EasyOCR, or another local OCR.
3. Training stat names and exact five labels in the PC client.
4. Color ring meanings and whether multiple rings can appear on one training.
5. Event guide source and format.
6. Whitelist shop items and max prices.
7. Current rank scale and commission eligibility rules.
