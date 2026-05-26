import os, logging, sys, io
os.environ["FLAGS_use_mkldnn"] = "0"
logging.disable(logging.CRITICAL)
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

from PIL import Image
from starsavior_trainer.regions import load_region_profile, scale_region_profile
from starsavior_trainer.ocr import PaddleOcrEngine
from starsavior_trainer.classifier import classify_hybrid
from starsavior_trainer.screen_reader import RegionOcrReader, parse_training_hub, parse_training_select, parse_rest_submenu
from starsavior_trainer.models import GameState, Observation
from starsavior_trainer.policy import TrainerPolicy

profile_base = load_region_profile("config/regions/2560x1440.json")
ocr = PaddleOcrEngine()
policy = TrainerPolicy()
state = GameState()

test_files = [
    ("training_hub_001.png", "training_hub"),
    ("training_select_001.png", "training_select"),
    ("rest_submenu_001.png", "rest_submenu"),
    ("event_choice_001.png", "event_choice"),
    ("commission_select_001.png", "commission_select"),
    ("shop_001.png", "shop_item"),
]

for fname, prefix in test_files:
    try:
        img = Image.open(f"screenshots/{fname}")
        profile = scale_region_profile(profile_base, img.size)
        obs = classify_hybrid(img, profile, ocr)
        reader = RegionOcrReader(profile, ocr)
        rts = reader.read_prefixes(img, [prefix], max_area=160000)

        payload = None
        sv = obs.screen.value
        if sv == "training_hub":
            payload = parse_training_hub(rts, profile, img)
        elif sv == "training_select":
            from starsavior_trainer.screen_reader import parse_training_select
            payload = parse_training_select(rts, profile, img)
        elif sv == "rest_submenu":
            payload = parse_rest_submenu(rts, profile)
        elif sv == "event_choice":
            from starsavior_trainer.screen_reader import parse_event_choice
            payload = parse_event_choice(rts, profile)
        elif sv == "commission_select":
            from starsavior_trainer.screen_reader import parse_commission_select
            payload = parse_commission_select(rts, profile, img)
        elif sv == "shop":
            from starsavior_trainer.screen_reader import parse_shop
            payload = parse_shop(rts, profile, img)

        full_obs = Observation(screen=obs.screen, confidence=obs.confidence, payload=payload)
        action = policy.decide(state, full_obs)
        print(f"\n=== {fname} ===")
        print(f"  screen={obs.screen.value} conf={obs.confidence:.2f}")
        print(f"  payload={payload}")
        print(f"  action={action.kind} target={action.target}")
        print(f"  reason={action.reason}")
    except Exception as e:
        print(f"\n=== {fname} === ERROR: {e}")
