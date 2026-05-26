import os,logging,ctypes,time,sys,io
os.environ["FLAGS_use_mkldnn"]="0"
logging.disable(logging.CRITICAL)
sys.stdout=io.TextIOWrapper(sys.stdout.buffer,encoding="utf-8",errors="replace")
hwnd=ctypes.windll.kernel32.GetConsoleWindow()
ctypes.windll.user32.ShowWindow(hwnd,0)
time.sleep(0.5)
from starsavior_trainer.capture import capture_window
from starsavior_trainer.ocr import PaddleOcrEngine
from PIL import Image
import colorsys
from collections import defaultdict
img,win=capture_window("StarSavior")
ctypes.windll.user32.ShowWindow(hwnd,5)
W,H=img.size
print(f"Captured: {W}x{H}")

# OCR
engine=PaddleOcrEngine()
result=engine.read_text(img)
safe=result.text.encode("ascii","replace").decode("ascii")
print(f"\nOCR: {safe[:300]}")
for kw in ["旅程","起点","选择","力量","体力","开始","确认","训练","祝福","星辰","入场","SKIP","RANK"]:
    if kw in result.text: print(f"  FOUND: '{kw}'")

# Scan bottom half for ANY colored UI elements
print(f"\n=== Bottom-half color scan ===")
pixels=list(img.convert("RGB").getdata())
clusters=defaultdict(list)
step=6
for y in range(H//2,H,step):
    for x in range(0,W,step):
        idx=y*W+x
        if idx>=len(pixels):continue
        r,g,b=pixels[idx]
        h,s,v=colorsys.rgb_to_hsv(r/255,g/255,b/255)
        hue=h*360
        # Detect any saturated colored pixel (not gray/white/black)
        if s>0.3 and v>0.3:
            clusters[(x//100,y//100)].append((x,y,r,g,b,hue,s,v))

# Report top colored clusters in bottom half
for (cx,cy),pts in sorted(clusters.items(),key=lambda kv:-len(kv[1]))[:15]:
    ax=sum(p[0] for p in pts)/len(pts);ay=sum(p[1] for p in pts)/len(pts)
    # Most common hue
    hues=[p[4] for p in pts]
    avg_hue=sum(hues)/len(hues)
    sat=[p[5] for p in pts]
    avg_sat=sum(sat)/len(sat)
    val=[p[6] for p in pts]
    avg_val=sum(val)/len(val)
    color="red" if avg_hue<20 or avg_hue>340 else "gold" if 30<avg_hue<60 else "green" if 80<avg_hue<160 else "blue" if 180<avg_hue<260 else "purple" if 260<avg_hue<300 else "other"
    print(f"  ({ax:.0f},{ay:.0f}) {len(pts)}pts hue={avg_hue:.0f} sat={avg_sat:.2f} val={avg_val:.2f} [{color}]")

img.save("screenshots/_diag_current.png")
print("\nSaved")
