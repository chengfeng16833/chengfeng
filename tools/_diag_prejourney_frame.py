# -*- coding: utf-8 -*-
"""诊断: 对一张实机帧跑 分类→解析→决策 全管线(真实 PaddleOCR, 不点击)。

用法: python -B tools/_diag_prejourney_frame.py [图片路径]
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from PIL import Image  # noqa: E402

from starsavior_trainer.classifier import classify_hybrid  # noqa: E402
from starsavior_trainer.models import GameState, Observation  # noqa: E402
from starsavior_trainer.ocr import PaddleOcrEngine  # noqa: E402
from starsavior_trainer.policy import TrainerPolicy  # noqa: E402
from starsavior_trainer.regions import load_region_profile  # noqa: E402
from starsavior_trainer.run_config import PreJourneyConfig  # noqa: E402
from starsavior_trainer.screens import HANDLERS  # noqa: E402
from starsavior_trainer.screen_reader import RegionOcrReader  # noqa: E402

image_path = sys.argv[1] if len(sys.argv) > 1 else "screenshots/prejourney_live_001.png"
image = Image.open(image_path)
profile = load_region_profile("config/regions/2560x1440.json")
ocr = PaddleOcrEngine()
reader = RegionOcrReader(profile, ocr)

obs = classify_hybrid(image, profile, ocr)
print(f"[1] 分类: screen={obs.screen.value} confidence={obs.confidence:.2f}")

handler = HANDLERS.get(obs.screen)
payload = None
if handler is not None and handler.ocr_prefixes:
    region_texts = reader.read_prefixes(image, handler.ocr_prefixes, max_area=160000)
    for item in region_texts:
        if item.text.strip():
            print(f"    OCR {item.name} = {item.text.strip()[:60]}")
    payload = handler.parse(region_texts, profile, image)
print(f"[2] 解析: payload={payload}")

if handler is not None:
    obs2 = Observation(screen=obs.screen, confidence=obs.confidence, payload=payload)
    state = GameState(prejourney=PreJourneyConfig(difficulty="困难"))
    action = TrainerPolicy().decide(state, obs2)
    print(f"[3] 决策: kind={action.kind} target={action.target} reason={action.reason}")
