from __future__ import annotations

import argparse
from datetime import datetime
from pathlib import Path

from starsavior_trainer.capture import capture_screen, capture_window, list_windows, save_image


def main() -> None:
    parser = argparse.ArgumentParser(description="Capture a Starsavior window or full screenshot.")
    parser.add_argument("--window-title", help="Capture the first visible window whose title contains this text.")
    parser.add_argument("--out", default="screenshots/capture.png", help="Output image path.")
    parser.add_argument("--list-windows", action="store_true", help="Print visible window titles and exit.")
    parser.add_argument("--timestamp", action="store_true", help="Append a timestamp before the file extension.")
    args = parser.parse_args()

    if args.list_windows:
        for window in list_windows():
            print(f"{window.hwnd} {window.rect.width}x{window.rect.height}+{window.rect.x}+{window.rect.y} {window.title}")
        return

    output = _timestamped(args.out) if args.timestamp else Path(args.out)
    if args.window_title:
        image, window = capture_window(args.window_title)
        save_image(image, output)
        print(f"captured window={window.title!r} rect={window.rect} out={output}")
    else:
        save_image(capture_screen(), output)
        print(f"captured screen out={output}")


def _timestamped(path: str) -> Path:
    output = Path(path)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    return output.with_name(f"{output.stem}-{stamp}{output.suffix}")


if __name__ == "__main__":
    main()
