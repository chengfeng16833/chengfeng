"""层级3: 真实 PaddleOCR 测试 — 用截图逐张验证全链路"""
import sys, os
sys.path.insert(0, os.path.dirname(__file__))
os.environ.setdefault("FLAGS_use_mkldnn", "0")
import logging
logging.disable(logging.CRITICAL)

from PIL import Image
from starsavior_trainer.ocr import PaddleOcrEngine
from starsavior_trainer.regions import load_region_profile, scale_region_profile
from starsavior_trainer.screen_reader import parse_blessing_choice, RegionOcrReader
from starsavior_trainer.policy import TrainerPolicy
from starsavior_trainer.models import BlessingChoice, GameState

print("[1/3] Loading PaddleOCR...")
ocr = PaddleOcrEngine()
profile = load_region_profile("config/regions/2560x1440.json")
policy = TrainerPolicy()

for name in ("blessing_choice_001.png", "blessing_choice_002.png"):
    path = f"screenshots/{name}"
    print(f"\n[2/3] {name} ({Image.open(path).size})")

    img = Image.open(path)
    scaled = scale_region_profile(profile, img.size)
    reader = RegionOcrReader(scaled, ocr)
    region_texts = reader.read_prefixes(img, ["blessing_choice", "blessing_card"], max_area=160000)

    # detail panel OCR
    detail = {rt.name: rt.text for rt in region_texts if "detail" in rt.name and rt.text.strip()}
    print(f"  detail_panel: {detail}")

    # card OCR samples
    cards = {rt.name: rt.text for rt in region_texts if rt.name.startswith("blessing_card_") and "_attribute" in rt.name and rt.text.strip()}
    samples = ["blessing_card_01_attribute", "blessing_card_02_attribute", "blessing_card_03_attribute"]
    for s in samples:
        if s in cards:
            print(f"  {s}: '{cards[s]}'")

    payload = parse_blessing_choice(region_texts, scaled, img)
    if payload is None:
        print("  => parse_blessing_choice: None (FAIL)")
        continue

    print(f"  => parsed {len(payload.options)} options, selected={payload.selected_name}")
    power_opts = [o for o in payload.options if o.attribute == "power"]
    print(f"     power options: {[(o.value, o.sub_blessing_count) for o in sorted(power_opts, key=lambda x: -(x.value or 0))[:5]]}")

    action = policy.decide_blessing_choice(payload, GameState(build_profile="power_focus"))
    print(f"  => policy: {action.kind} — {action.reason}")

print("\n[3/3] done")
