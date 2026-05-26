# Screenshot Collection Guide

Use this guide to collect the first real Starsavior PC screenshots for region calibration and OCR checks.

See `docs/game-screens.md` for the screenshots and rules already described in
chat during intake mode.

## Capture Rules

1. Use the PC client, not an emulator.
2. Keep one fixed resolution and window mode for the first batch.
3. Do not crop screenshots manually.
4. Do not resize screenshots.
5. Capture the whole Starsavior client window.
6. Give each file a screen-state prefix.

Example names:

```text
initial_001.png
dialogue_001.png
training_select_001.png
rest_submenu_001.png
event_choice_001.png
relic_choice_001.png
commission_select_001.png
shop_001.png
region_move_001.png
unknown_001.png
```

The first screenshot received in chat appears to be `2048x1190` including the Windows title bar. Keep the rest of the batch in this same window size if possible.

## Minimum First Batch

| Screen state | Minimum screenshots | What must be visible |
| --- | ---: | --- |
| `initial` | 1 | Start button |
| `character_select` | 2 | Right-side character list, selected character, `选择` button |
| `blessing_setup` | 2 | Blessing slots, auto-equip button, confirm button |
| `blessing_choice` | 3 | Blessing attribute names and numeric values |
| `journey_start` | 1 | Arcana cards and `旅程起点` button |
| `confirm_dialog` | 1 | Modal title, message, cancel and confirm buttons |
| `event_fast_forward_setting` | 1 | Three fast-forward options and decision button |
| `dialogue_intro` | 1 | Full-screen story and top-right `SKIP` |
| `dialogue_journey_hud` | 1 | Journey HUD and changed top-right skip controls |
| `relic_choice` | 2 | Three relic cards, score, names, confirm button |
| `training_select` | 5 | Five trainings, fail rates, colored rings |
| `rest_submenu` | 2 | Meditation room / rough sleep choices and coins |
| `event_choice` | 5 | Full option text |
| `relic_choice` | 3 | Relic names and scores/grades |
| `commission_select` | 3 | Red text, rank text, commission choices |
| `shop` | 3 | Item names, prices, buy buttons |
| `region_move` | 2 | Move button |
| `unknown` | optional | Any screen where the bot should pause |

The most valuable screenshots are messy ones: low stamina, high failure rate, unclear OCR, multiple colored rings, expensive shop items, or event options with similar wording.

## Capture Commands

List visible windows:

```powershell
python -m starsavior_trainer.cli.capture_once --list-windows
```

Capture a window by title:

```powershell
python -m starsavior_trainer.cli.capture_once --window-title Starsavior --out .\screenshots\training_select_001.png
```

If the title is localized or different, use a unique substring from the window list.

## Region Calibration

After a screenshot is captured, generate crops and an overlay:

```powershell
python -m starsavior_trainer.cli.crop_regions --image .\screenshots\training_select_001.png --profile .\config\regions\1920x1080.json
```

Check `debug/regions-overlay.png`. If boxes do not align with the UI, update `config/regions/1920x1080.json`.

## What To Send Back

Send either:

1. A zip/folder containing the screenshots, or
2. The path to your local screenshot folder, or
3. A few representative screenshots pasted into the chat.

Best first folder shape:

```text
screenshots/
  initial_001.png
  character_select_001.png
  blessing_setup_001.png
  blessing_choice_001.png
  journey_start_001.png
  entry_confirm_001.png
  event_fast_forward_setting_001.png
  dialogue_intro_001.png
  dialogue_journey_hud_001.png
  relic_choice_initial_001.png
  training_select_001.png
  training_select_002.png
  rest_submenu_001.png
  event_choice_001.png
  relic_choice_001.png
  commission_select_001.png
  shop_001.png
  region_move_001.png
```
