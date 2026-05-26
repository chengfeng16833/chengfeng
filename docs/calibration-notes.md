# Calibration Notes

## initial_001

Received from chat as the first initial screen example.

Observed screen:

- Window title: `StarSavior`
- Screenshot shape: approximately `2048x1190`
- Capture includes the Windows title bar.
- Client area begins around `y=36`.
- This is the route-selection start screen, with the route `001` and title text `星光引导者`.
- Primary action: click the blue `开始` button in the bottom-right.
- File naming: use either `initial_001.png` or `route_select_001.png`; both map to the `initial` screen state.

Draft regions:

| Region | Rect |
| --- | --- |
| `start_button` | `[1631, 1088, 374, 60]` |
| `initial_difficulty_hard` | `[1882, 1016, 124, 52]` |
| `initial_route_card` | `[65, 1026, 353, 122]` |
| `journey_record_area` | `[1631, 192, 375, 38]` |

The coordinates are approximate because the image was provided through chat rather than as a local file. Once the raw file exists under `screenshots/initial_001.png`, run:

```powershell
python -m starsavior_trainer.cli.crop_regions --image .\screenshots\initial_001.png --profile .\config\regions\2048x1190.json
```

Then inspect `debug/regions-overlay.png` and tighten the rectangles.

## character_select_001

Received from chat as the first post-start character selection example.

Observed screen:

- Screenshot shape appears to match the first `2048x1190` windowed capture.
- Header text: `旅程起点`.
- Right side contains the selectable character list.
- Bottom-right blue button: `选择`.
- Left side shows selected character and five starting attributes.
- The selected character determines the build profile and therefore later training weights.

Draft regions:

| Region | Rect |
| --- | --- |
| `character_option_1` | `[1624, 202, 363, 96]` |
| `character_option_2` | `[1624, 316, 363, 96]` |
| `character_option_3` | `[1624, 432, 363, 96]` |
| `character_option_4` | `[1624, 548, 363, 96]` |
| `character_option_5` | `[1624, 664, 363, 96]` |
| `character_select_button` | `[1629, 1046, 357, 58]` |
| `character_stat_power` | `[78, 505, 322, 48]` |
| `character_stat_focus` | `[78, 668, 322, 48]` |

New state:

```text
initial -> character_select -> dialogue/training flow
```

The current selected example has high `专注` and `力量`, so a likely profile is `focus_focus` or `power_focus`. The script will eventually map selected character names to a build profile.

## blessing_setup_001

Received from chat as the first post-character blessing setup screen.

Observed screen:

- Header text: `旅程起点`.
- Left side still shows selected character and base attributes.
- Two visible blessing slots with plus icons.
- Bottom-right buttons: `自动装备`, search/icon button, disabled `确认`.
- Blessing selection should happen before entering the run.

Draft regions:

| Region | Rect |
| --- | --- |
| `blessing_slot_1` | `[768, 584, 196, 196]` |
| `blessing_slot_2` | `[1646, 337, 196, 196]` |
| `blessing_auto_equip_button` | `[1688, 976, 210, 52]` |
| `blessing_confirm_button` | `[1684, 1044, 290, 60]` |

Logic:

```text
character_select -> blessing_setup -> blessing_choice -> blessing_setup -> confirm
```

For a power-focused character, choose the highest value power blessing. Blessing values appear to cap at 50.

## blessing_choice_001

Received from chat as the first blessing choice grid.

Observed screen:

- Sort dropdown text: `能力值祝福`.
- Grid shows 5 columns of blessing cards.
- Each card has an attribute/value label such as `力量:45`, `力量:35`, `体力:35`.
- Right side detail panel shows selected blessing details and a blue `确认` button.
- A selected blessing can include smaller sub-blessings. Example: a `力量:35` blessing also shows an attack-sense sub-blessing icon.
- Up to 2 blessings can be equipped. Single blessing max value is 50, so target total is 100.

Draft regions:

| Region | Rect |
| --- | --- |
| `blessing_card_01` | `[438, 250, 170, 196]` |
| `blessing_card_02` | `[638, 250, 170, 196]` |
| `blessing_card_03` | `[838, 250, 170, 196]` |
| `blessing_choice_detail_panel` | `[1446, 174, 472, 970]` |
| `blessing_choice_detail_sub_1` | `[1485, 517, 92, 92]` |
| `blessing_choice_confirm_button` | `[1472, 1068, 420, 58]` |

Selection priority:

```text
target attribute match
  -> higher value
  -> more sub-blessings
  -> deterministic name tie-break
```

For a power-focused run, two selected blessings should aim for `力量:50 + 力量:50 = 100`. If only lower values are visible, choose the highest visible value and prefer options with sub-blessings when values tie.

## journey_start_001

Received from chat as the post-blessing journey start screen.

Observed screen:

- Header text: `旅程起点`.
- Arcana cards appear on the right side and are mostly fixed for the route.
- Bottom-right blue button: `旅程起点`.
- Bottom-center white button: `自动旅程`.
- Left stat panel shows blessing bonuses, for example `力量 +45 +35`.
- User rule: Arcana can be ignored for now; click journey start directly.

Draft regions:

| Region | Rect |
| --- | --- |
| `journey_start_button` | `[1542, 1078, 430, 60]` |
| `journey_start_auto_journey_button` | `[1300, 1078, 232, 60]` |
| `journey_start_arcana_slot_1` | `[1124, 392, 130, 292]` |
| `journey_start_arcana_slot_5` | `[1778, 424, 160, 292]` |
| `journey_start_power_bonus` | `[416, 540, 136, 38]` |

Logic:

```text
blessing_setup confirmed -> journey_start -> click journey_start_button
```

Arcana scoring is intentionally skipped until there is evidence it varies enough to matter.

## entry_confirm_001

Received from chat as the confirmation dialog after clicking `旅程起点`.

Observed screen:

- Modal title: `入场确认`.
- Message: `是否要进行旅程?`
- Left button: `取消`.
- Right blue button: `确认`.

Draft regions:

| Region | Rect |
| --- | --- |
| `confirm_dialog_panel` | `[508, 318, 1033, 516]` |
| `confirm_dialog_title` | `[541, 338, 220, 54]` |
| `confirm_dialog_message` | `[850, 620, 350, 50]` |
| `confirm_dialog_cancel_button` | `[730, 753, 286, 60]` |
| `confirm_dialog_confirm_button` | `[1033, 753, 286, 60]` |

Logic:

```text
journey_start -> confirm_dialog -> click confirm
```

## event_fast_forward_setting_001

Received from chat as the event fast-forward setting dialog.

Observed screen:

- Modal title: `事件快转设定`.
- Options:
  - `不快转`
  - `仅快转已观赏的事件`
  - `快转所有事件`
- User rule: always choose `快转所有事件`.
- Bottom blue button: `决定`.

Draft regions:

| Region | Rect |
| --- | --- |
| `event_fast_forward_no_option` | `[433, 389, 394, 306]` |
| `event_fast_forward_watched_option` | `[835, 389, 380, 300]` |
| `event_fast_forward_all_option` | `[1228, 389, 380, 300]` |
| `event_fast_forward_confirm_button` | `[882, 805, 286, 60]` |

Logic:

```text
if all-events option is not selected:
  click 快转所有事件
else:
  click 决定
```

## dialogue_intro_001

Received from chat as the first full-screen intro dialogue after the run begins.

Observed screen:

- Full-screen background with no main HUD.
- Top-right text button: `SKIP`.
- Dialogue text appears near the bottom center.

Draft regions:

| Region | Rect |
| --- | --- |
| `dialogue_intro_skip_button` | `[1905, 40, 105, 55]` |
| `dialogue_intro_text_area` | `[710, 940, 620, 92]` |

Logic:

```text
dialogue variant=intro_story -> click dialogue_intro_skip_button
```

## dialogue_journey_hud_001

Received from chat as the first in-journey dialogue screen.

Observed screen:

- Full journey HUD is visible.
- Left top shows distance goal and task.
- Top-right controls include a changed skip/fast-forward layout.
- Dialogue text remains at the bottom.

Draft regions:

| Region | Rect |
| --- | --- |
| `dialogue_journey_skip_button` | `[1484, 43, 62, 52]` |
| `dialogue_journey_fast_forward_button` | `[1570, 43, 62, 52]` |
| `dialogue_journey_text_area` | `[820, 940, 520, 92]` |
| `journey_hud_goal_area` | `[70, 44, 176, 104]` |
| `journey_hud_task_area` | `[70, 194, 280, 94]` |

Logic:

```text
dialogue variant=journey_hud -> click dialogue_journey_skip_button
```

## relic_choice_initial_001

Received from chat as the first relic reward choice.

Observed screen:

- Header text: `选择奖励`.
- Three relic cards are visible.
- Each card has a score in the upper-right area.
- Bottom button: `选择完成`, disabled until a relic is selected.
- User rule: the first relic choice is fixed. Choose `烦人的布谷鸟时钟`.
- Later relic choices should choose the highest score.

Draft regions:

| Region | Rect |
| --- | --- |
| `relic_card_1` | `[390, 263, 384, 604]` |
| `relic_card_2` | `[832, 263, 384, 604]` |
| `relic_card_3` | `[1275, 263, 384, 604]` |
| `relic_card_1_score` | `[665, 286, 84, 40]` |
| `relic_card_2_score` | `[1108, 286, 84, 40]` |
| `relic_card_3_score` | `[1550, 286, 84, 40]` |
| `relic_choice_confirm_button` | `[863, 927, 322, 66]` |

Logic:

```text
if first relic choice:
  click 烦人的布谷鸟时钟
elif relic already selected:
  click 选择完成
else:
  click highest score relic
```
