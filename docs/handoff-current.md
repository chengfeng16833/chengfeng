# Starsavior Trainer Handoff

## Purpose

Continue developing the current Starsavior PC training assistant from the
current project structure only. Do not resurrect the old `screen/` directory
design. Keep the existing package layout under `starsavior_trainer/`.

## Current Workspace

Primary project:

```text
C:\Users\ChengFeng\Documents\New project
```

Desktop synced copy:

```text
C:\Users\ChengFeng\Desktop\starsavior-trainer
```

The user is providing 2560x1440 game-client screenshots. The current primary
region profile is:

```text
config/regions/2560x1440.json
```

## Skills To Use

- Use `diagnose` if a bug or failing test appears.
- Use `tdd` when implementing readers or new decision behavior test-first.
- Use `handoff` again before any risky context transition or long pause.

## Important Instructions

- Do not reference old conversations.
- Only use current workspace files and the screenshots/user rules from this
  handoff.
- Do not do a large rewrite.
- Keep OCR/CV extraction separate from `TrainerPolicy`.
- Prefer small steps: update region profile, add parser/reader test, implement
  the smallest reader behavior, run tests, sync desktop copy.

## Current Architecture

- `starsavior_trainer/models.py`: typed observations and actions.
- `starsavior_trainer/policy.py`: decision logic from typed payloads.
- `starsavior_trainer/screen_reader.py`: OCR text reading and parser helpers.
- `starsavior_trainer/vision.py`: color detection. It now has a PIL fallback
  when OpenCV is not installed.
- `starsavior_trainer/classifier.py`: temporary filename classifier.
- `config/regions/2560x1440.json`: draft regions for the current real client
  resolution.
- `TODO.md`: current plan and known screen flow.

## Work Completed In This Session

Created `TODO.md` with development plan.

Added parser helpers in `screen_reader.py`:

- `normalize_ocr_text`
- `contains_any_text`
- `parse_first_int`
- `parse_percent`
- `parse_attribute_value`

Added/expanded tests in:

```text
tests/test_screen_reader.py
```

Added 2560x1440 region profile:

```text
config/regions/2560x1440.json
```

The profile currently contains draft regions for:

- route select / initial screen
- character select screen
- blessing setup screen
- blessing choice screen
- journey start / Arcana preset screen
- entry confirm dialog
- event fast-forward setting dialog

Updated `TODO.md` with sections for:

- pre-training entry flow
- blessing setup and blessing choice
- journey start and entry confirm
- event fast-forward setting

## Confirmed Screen Flow

The current known pre-training flow is:

```text
route_select / initial
  -> click start
  -> character_select
  -> click selected/desired character confirm
  -> blessing_setup
  -> blessing_choice
  -> blessing_setup confirm
  -> journey_start / Arcana preset screen
  -> click journey_start_button
  -> confirm_dialog
  -> click confirm
  -> event_fast_forward_setting
  -> choose all-events fast-forward
  -> later in-run screens
```

## Confirmed Rules

Route select:

- Start from `选择旅程`.
- Click the blue `开始` button.
- Current route is `星光引导者`.

Character select:

- Click `选择` for the chosen/selected character.
- Character/build should eventually determine desired blessing attribute.

Blessing setup:

- There are two blessing slots.
- Empty slots show plus icons.
- Do not trust `自动装备` until user says otherwise.

Blessing choice:

- Two blessings total.
- One blessing can provide up to 50 points.
- Ideal total is 100 points.
- Power characters prefer power blessings.
- Stamina characters prefer stamina blessings.
- Same logic applies via build profile mapping.
- Among matching blessings, choose highest numeric value.
- If same value, prefer the one with more sub-blessings.
- If no matching recognized value exists, pause instead of guessing.

Journey start / Arcana:

- Arcana cards are treated as fixed for now.
- Do not edit cards.
- Click `旅程起点`.

Entry confirm:

- When `入场确认` appears, click blue `确认`.

Event fast-forward setting:

- Always choose `快转所有事件`.
- If already selected, click `决定`.

## Verification

Use bundled Python because `python` may not be on PATH:

```powershell
& 'C:\Users\ChengFeng\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' -B -m unittest discover -s tests
```

Latest verification result:

```text
Ran 27 tests
OK
```

Region profile validation command:

```powershell
& 'C:\Users\ChengFeng\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' -B -m starsavior_trainer.cli.offline_harness --demo --profile .\config\regions\2560x1440.json
```

Latest region profile count:

```text
profile=pc-2560x1440-client-draft resolution=2560x1440 regions=142
```

## Important Caveat

The current `TrainerPolicy` demo still emits older hard-coded rectangles for
some screens because policy has not yet been connected to the region profile.
This is expected. Do not rewrite policy yet. The next good step is to add
screen readers and eventually pass profile rectangles into typed payloads.

## Suggested Next Step

Continue from the next screenshot after event fast-forward setting. Likely next
screens are dialogue/story, journey HUD, or the first in-run choice screen.

If implementing code next, a good small TDD step is:

1. Add a fake region-text based reader test for `EventFastForwardSetting` or
   `JourneyStart`.
2. Implement only that reader.
3. Keep policy unchanged.
4. Run all tests.
5. Sync changed files to `C:\Users\ChengFeng\Desktop\starsavior-trainer`.
