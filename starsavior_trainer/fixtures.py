from __future__ import annotations

from starsavior_trainer.models import (
    CommissionOption,
    BlessingChoice,
    BlessingOption,
    BlessingSetup,
    BlessingSlot,
    CharacterOption,
    CharacterSelect,
    EventOption,
    GameState,
    ConfirmDialog,
    DialogueScene,
    EventFastForwardSetting,
    Observation,
    Rect,
    JourneyStart,
    RelicChoice,
    RelicOption,
    RestSubmenu,
    Screen,
    ShopItem,
    TrainingChoice,
    TrainingHubStatus,
)


def demo_state() -> GameState:
    return GameState(current_rank="C", coins=80)


def demo_observations() -> list[Observation]:
    return [
        Observation(Screen.INITIAL, 0.95, source="demo:initial"),
        Observation(
            Screen.CHARACTER_SELECT,
            0.93,
            CharacterSelect(
                options=[
                    CharacterOption("beier_lisi", "A", 4, "focus", True, Rect(1620, 202, 366, 96)),
                    CharacterOption("xiaer", "B", 4, "power", False, Rect(1620, 318, 366, 96)),
                ],
                confirm_button=Rect(1629, 1046, 357, 58),
                selected_name="beier_lisi",
            ),
            source="demo:character_select",
        ),
        Observation(
            Screen.BLESSING_SETUP,
            0.93,
            BlessingSetup(
                slots=[
                    BlessingSlot(1, False, Rect(768, 584, 196, 196)),
                    BlessingSlot(2, False, Rect(1647, 337, 196, 196)),
                ],
                auto_equip_button=Rect(1688, 976, 210, 52),
                confirm_button=Rect(1684, 1044, 290, 60),
                can_confirm=False,
            ),
            source="demo:blessing_setup",
        ),
        Observation(
            Screen.BLESSING_CHOICE,
            0.91,
            BlessingChoice(
                options=[
                    BlessingOption("power_blessing_30", "power", 30, Rect(650, 420, 300, 100)),
                    BlessingOption("power_blessing_50", "power", 50, Rect(990, 420, 300, 100), 1, ("attack_sense",)),
                    BlessingOption("stamina_blessing_40", "stamina", 40, Rect(1330, 420, 300, 100)),
                ]
            ),
            source="demo:blessing_choice",
        ),
        Observation(
            Screen.JOURNEY_START,
            0.94,
            JourneyStart(
                start_button=Rect(1542, 1078, 430, 60),
                auto_journey_button=Rect(1300, 1078, 232, 60),
                arcana_slots=[
                    Rect(1124, 392, 130, 292),
                    Rect(1276, 430, 130, 292),
                    Rect(1426, 448, 130, 292),
                    Rect(1584, 402, 160, 292),
                    Rect(1778, 424, 160, 292),
                ],
            ),
            source="demo:journey_start",
        ),
        Observation(
            Screen.CONFIRM_DIALOG,
            0.96,
            ConfirmDialog(
                title="entry_confirm",
                message="start_journey",
                confirm_button=Rect(1033, 753, 286, 60),
                cancel_button=Rect(730, 753, 286, 60),
            ),
            source="demo:confirm_dialog",
        ),
        Observation(
            Screen.EVENT_FAST_FORWARD_SETTING,
            0.96,
            EventFastForwardSetting(
                no_fast_forward_option=Rect(433, 389, 394, 306),
                watched_only_option=Rect(835, 389, 380, 300),
                all_events_option=Rect(1228, 389, 380, 300),
                confirm_button=Rect(882, 805, 286, 60),
                selected_mode="no_fast_forward",
            ),
            source="demo:event_fast_forward_setting",
        ),
        Observation(
            Screen.DIALOGUE,
            0.91,
            DialogueScene(skip_button=Rect(1905, 40, 105, 55), variant="intro_story"),
            source="demo:dialogue_intro",
        ),
        Observation(
            Screen.DIALOGUE,
            0.91,
            DialogueScene(skip_button=Rect(1484, 43, 62, 52), variant="journey_hud"),
            source="demo:dialogue_journey_hud",
        ),
        Observation(
            Screen.TRAINING_HUB,
            0.92,
            TrainingHubStatus(
                turn_label="3\u4e0a\u65ec",
                coins=48,
                rank_label="RANK 13",
                potential_points=21,
                training_button=Rect(1750, 450, 650, 180),
                commission_button=Rect(1750, 665, 650, 180),
                rest_button=Rect(1750, 880, 650, 180),
            ),
            source="demo:training_hub",
        ),
        Observation(
            Screen.TRAINING_SELECT,
            0.92,
            [
                TrainingChoice("speed", 24, "blue", 3, Rect(200, 720, 220, 120)),
                TrainingChoice("stamina", 18, "rainbow", 12, Rect(480, 720, 220, 120)),
                TrainingChoice("power", 32, "none", 28, Rect(760, 720, 220, 120)),
                TrainingChoice("guts", 14, "gold", 0, Rect(1040, 720, 220, 120)),
                TrainingChoice("wisdom", 10, "none", 0, Rect(1320, 720, 220, 120)),
            ],
            source="demo:training",
        ),
        Observation(
            Screen.REST_SUBMENU,
            0.90,
            RestSubmenu(80, True, Rect(900, 520, 240, 90), Rect(900, 660, 240, 90)),
            source="demo:rest",
        ),
        Observation(
            Screen.EVENT_CHOICE,
            0.88,
            [
                EventOption("speed +12", Rect(900, 480, 420, 70)),
                EventOption("stamina recover 20", Rect(900, 570, 420, 70)),
                EventOption("mood up", Rect(900, 660, 420, 70)),
            ],
            source="demo:event",
        ),
        Observation(
            Screen.RELIC_CHOICE,
            0.93,
            RelicChoice(
                options=[
                    RelicOption("soft_toy_friend", 12, Rect(390, 263, 384, 604)),
                    RelicOption("annoying_cuckoo_clock", 12, Rect(832, 263, 384, 604)),
                    RelicOption("balanced_scale", 12, Rect(1275, 263, 384, 604)),
                ],
                confirm_button=Rect(863, 927, 322, 66),
                fixed_name="annoying_cuckoo_clock",
            ),
            source="demo:relic",
        ),
        Observation(
            Screen.COMMISSION_SELECT,
            0.86,
            [
                CommissionOption("short_patrol", "C", True, Rect(760, 640, 320, 90)),
                CommissionOption("highland_training", "B", True, Rect(1120, 640, 320, 90)),
            ],
            source="demo:commission",
        ),
        Observation(
            Screen.SHOP,
            0.89,
            [
                ShopItem("decoration", 40, Rect(1380, 420, 160, 60)),
                ShopItem("stamina_potion", 75, Rect(1380, 520, 160, 60)),
            ],
            source="demo:shop",
        ),
        Observation(Screen.REGION_MOVE, 0.90, source="demo:move"),
        Observation(Screen.UNKNOWN, 0.40, source="demo:unknown"),
    ]
