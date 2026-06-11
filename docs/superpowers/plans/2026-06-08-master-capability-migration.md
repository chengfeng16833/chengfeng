# Starsavior Master Capability Migration Plan

Date: 2026-06-08
Main project: `C:\Users\ChengFeng\Desktop\starsavior-trainer`
Source project: `C:\Users\ChengFeng\Desktop\Starsavior-master`

## Goal

Use `starsavior-trainer` as the only product line, and migrate the useful capabilities from `Starsavior-master` without copying its monolithic runtime shape. The target state keeps the typed model/screen/policy/test structure of `starsavior-trainer`, while adding the mature behaviors from `Starsavior-master` in small, testable slices.

## Baseline

- `starsavior-trainer` is a git repo on `master`, tracking `origin/master`.
- Baseline verification command:
  - `& 'C:\Users\ChengFeng\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' -B -m unittest discover -s tests`
- Current baseline result before this plan: 259 tests pass.
- `pytest` is not available in the bundled Python runtime, so new tests should use `unittest` unless dependencies are intentionally changed.
- The user runs the real bot; Codex changes code, tests locally, and gives a real-game validation checklist.

## Migration Principles

- Keep `starsavior-trainer` as the architecture owner.
- Port behavior, config data, and proven algorithms from `Starsavior-master`; do not wholesale-copy `src/handlers.py`.
- Every production behavior slice starts with a failing or characterization test.
- Optional Windows-only capabilities must degrade cleanly in tests and non-Windows contexts.
- Keep current policy behavior as default until the replacement is verified.
- Prefer structured JSON loaders and typed adapters over ad hoc string logic.

## Source Advantages To Port

1. Rule-driven training profiles from `src/rule_engine.py` and `profiles/training/*.json`.
2. Rich event/shop/skill profile databases from `profiles/events`, `profiles/shop`, and `profiles/skills`.
3. Safer Windows execution from `src/controller.py` using `SendInput`, cursor restore, and keyboard hotkeys.
4. PrintWindow capture timeout protection from `src/capture.py`.
5. Hybrid OCR strategy from `src/recognition.py`: fast OCR for hot paths, detailed OCR for complex reads.
6. Support card/arcanum visual detection from `src/arcanum.py`.
7. Flash training detection, scan modes, camp/rest strategy, and target-stat downweighting from the v5.1 changelog.
8. Journey-end skill learning from `JourneyEndHandler` plus skill priority JSON.
9. Timing logger and analysis tooling.
10. Pre-journey main-menu-to-journey flow from the DOCX: difficulty, profession, imprint slots, support deck, friend support card, and journey start.

## Target Module Map

- `starsavior_trainer/profile_loader.py`: JSON profile discovery, schema checks, and normalized profile objects.
- `starsavior_trainer/rule_engine.py`: typed training rule engine adapted to `TrainingChoice` and existing policy inputs.
- `starsavior_trainer/run_config.py`: user-facing run configuration shared by CLI and GUI.
- `starsavior_trainer/capture.py`: add timeout-protected PrintWindow path or wrapper around existing capture entry points.
- `starsavior_trainer/executor.py`: add optional `SendInputExecutor`; keep `DryRunExecutor` and current pyautogui path.
- `starsavior_trainer/ocr.py`: add optional hybrid OCR wrapper with graceful fallback.
- `starsavior_trainer/support_cards.py`: support-card deck/friend/card visual decisions and arcanum-style bond/icon scoring.
- `starsavior_trainer/prejourney.py`: policy helpers for main menu, difficulty, character/profession, imprint slots, support deck, friend card, and start button.
- `starsavior_trainer/timing.py`: lightweight timing logger for classifiers, OCR, inspectors, policy, and executor calls.
- `config/profiles/...`: normalized data copied from `Starsavior-master/profiles/...`.
- `tests/...`: one test file per slice.

## Execution Phases

### Phase 0: Safety Setup

1. Create an isolated implementation branch or worktree for the migration.
2. Run baseline `unittest` and offline harness.
3. Do not touch untracked user files: `_capture_screens.py`, `_classify_caps.py`, `协作守则.md`, and `游戏主界面进入旅途的流程.docx` unless the user asks.

Verification:

```powershell
& 'C:\Users\ChengFeng\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' -B -m unittest discover -s tests
& 'C:\Users\ChengFeng\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' -B -m starsavior_trainer.cli.offline_harness --demo --profile .\config\regions\2560x1440.json
```

### Phase 1: Shared Run Configuration And Profile Loader

Purpose: add the configuration spine needed by both the DOCX flow and the master profile migration, with no runtime behavior change by default.

Tests first:

- `tests/test_run_config.py`
  - default difficulty/profession/imprint/support settings are stable.
  - character class maps to a default imprint attribute.
  - explicit GUI/CLI values override inferred values.
- `tests/test_profile_loader.py`
  - loads normalized JSON profiles from `config/profiles`.
  - rejects malformed profile files with a clear error.
  - keeps source profile type names: `training`, `events`, `shop`, `skills`.

Implementation:

- Add `starsavior_trainer/run_config.py`:

```python
from dataclasses import dataclass

@dataclass(frozen=True)
class PreJourneyConfig:
    difficulty: str = "default"
    profession: str = ""
    imprint_slot_1_index: int = 1
    imprint_slot_2_index: int = 1
    support_deck: int = 1
    friend_support_name: str = ""

    def imprint_attribute(self) -> str:
        if self.profession in {"辅助", "坦克"}:
            return "体力"
        if self.profession == "艾黛":
            return "韧性"
        return "力量"
```

- Add CLI args in `starsavior_trainer/cli/live_loop.py` and GUI fields in `starsavior_trainer/cli/gui.py` for:
  - difficulty
  - profession
  - imprint slot 1 index
  - imprint slot 2 index
  - support deck
  - friend support name
- Store config on the live-loop settings object without changing policy decisions yet.
- Add `config/profiles/README.md` documenting the imported source folders.

Verification:

```powershell
& 'C:\Users\ChengFeng\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' -B -m unittest tests.test_run_config tests.test_profile_loader
& 'C:\Users\ChengFeng\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' -B -m unittest discover -s tests
```

### Phase 2: DOCX Pre-Journey Flow

Purpose: implement the requested main-screen-to-journey flow using the new config.

Tests first:

- `tests/test_prejourney_policy.py`
  - main game screen opens the menu whether the red exclamation mark exists or not.
  - difficulty screen picks configured difficulty.
  - character screen applies profession filter and selects the configured target character.
  - imprint slot selection converts index to row/column correctly: 4 = row 1 column 4, 12 = row 3 column 2.
  - imprint attribute follows `PreJourneyConfig.imprint_attribute()`.
  - support deck navigation chooses configured deck number.
  - friend support search clicks the matching OCR name and then confirms card details.
  - final support-card screen clicks journey start.

Implementation:

- Add or extend screen models for missing pre-journey screens.
- Add region keys to `config/regions/2560x1440.json` only after each key is used by tests or a handler.
- Add handler functions in `starsavior_trainer/screens/__init__.py` that delegate to `starsavior_trainer/prejourney.py`.
- Prefer typed `Action` objects already used by the executor.
- Keep real-game validation manual: Codex should not start the live bot without the user.

Verification:

```powershell
& 'C:\Users\ChengFeng\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' -B -m unittest tests.test_prejourney_policy
& 'C:\Users\ChengFeng\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' -B -m unittest discover -s tests
```

### Phase 3: Training Rule Engine

Purpose: port master training profiles and scoring while keeping the current trainer policy as a fallback.

Tests first:

- loader tests for `config/profiles/training/*.json`.
- rule evaluation tests for stamina penalty, flash multiplier, icon multiplier, target-stat downweighting, and profile-specific priorities.
- policy integration tests proving current behavior is unchanged when no rule profile is enabled.

Implementation:

- Add `starsavior_trainer/rule_engine.py`.
- Normalize master profile names into `config/profiles/training`.
- Add a `--training-profile` CLI/GUI setting.
- Make `TrainerPolicy` call the rule engine only when a valid profile is selected.

Verification:

```powershell
& 'C:\Users\ChengFeng\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' -B -m unittest tests.test_rule_engine tests.test_policy
& 'C:\Users\ChengFeng\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' -B -m unittest discover -s tests
```

### Phase 4: Safe Windows Runtime Layer

Purpose: port lower-risk runtime improvements independently from game strategy.

Tests first:

- fake `user32` tests for cursor restore, click coordinate conversion, multi-click, escape/space/number keys.
- capture timeout tests using a blocking fake capture function.

Implementation:

- Add `SendInputExecutor` to `starsavior_trainer/executor.py` behind `--executor sendinput`.
- Add timeout wrapper to capture code.
- Keep pyautogui executor available.

Verification:

```powershell
& 'C:\Users\ChengFeng\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' -B -m unittest tests.test_executor tests.test_capture
& 'C:\Users\ChengFeng\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' -B -m unittest discover -s tests
```

### Phase 5: OCR And Vision Improvements

Purpose: port hybrid OCR and arcanum/support-card detection without adding mandatory heavy dependencies.

Tests first:

- fake fast/detailed OCR tests for routing and fallback.
- synthetic image tests for yellow bond bars, icon priority, and flash training detection.

Implementation:

- Add optional `HybridOcrEngine` in `ocr.py`.
- Add `support_cards.py` for arcanum-inspired detection.
- Reuse existing PIL/NumPy vision helpers where possible.
- Avoid making `opencv-python` mandatory unless a measured accuracy gain requires it.

Verification:

```powershell
& 'C:\Users\ChengFeng\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' -B -m unittest tests.test_ocr tests.test_support_cards
& 'C:\Users\ChengFeng\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' -B -m unittest discover -s tests
```

### Phase 6: Events, Shop, Skills, And Endgame

Purpose: port master data-driven event/shop/skill behavior after the runtime spine is stable.

Tests first:

- event profile matching, hotkey action generation, and unknown-event fallback.
- shop item priority and skip/fallback behavior.
- journey-end skill priority selection.

Implementation:

- Normalize source JSON into `config/profiles/events`, `config/profiles/shop`, and `config/profiles/skills`.
- Replace hard-coded choices only where tests prove behavior.
- Keep self-learning writes disabled by default until file ownership is clear.

Verification:

```powershell
& 'C:\Users\ChengFeng\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' -B -m unittest tests.test_events tests.test_shop tests.test_skills
& 'C:\Users\ChengFeng\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' -B -m unittest discover -s tests
```

### Phase 7: Timing, Scan Modes, And Safety Policies

Purpose: port operational safety and performance controls after behavior is measurable.

Tests first:

- timing logger records classifier/OCR/handler/policy/executor durations.
- max runtime, consecutive unknown, and per-round timeout produce safe actions.
- scan mode changes do not bypass emergency stop behavior.

Implementation:

- Add `timing.py` and optional CSV/JSONL logging.
- Add scan mode setting: fast, normal, focus.
- Add safety counters to the live loop using existing pause/emergency-stop conventions.

Verification:

```powershell
& 'C:\Users\ChengFeng\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' -B -m unittest tests.test_timing tests.test_live_loop_safety
& 'C:\Users\ChengFeng\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' -B -m unittest discover -s tests
```

## First Implementation Slice

Start with Phase 1, because it creates the shared config surface needed by the DOCX flow and every later migrated feature. It is low-risk: it should not change any live policy decisions until explicit integration phases.

## Done Criteria For Each Phase

- New tests fail before implementation or characterize existing behavior before refactor.
- Phase-specific tests pass.
- Full `unittest discover` passes.
- Offline harness still runs.
- Any Windows-only feature has a fallback or a clear unavailable message.
- Final note includes exact files changed and what remains for real-game validation.
