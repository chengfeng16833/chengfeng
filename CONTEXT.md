# Starsavior Trainer Context

## Domain

Starsavior Trainer is a PC-window automation assistant for training runs. It observes the visible game client, recognizes the current screen, chooses the next action, and executes clicks.

The script is screenshot-driven. It does not assume emulator APIs, memory reading, packet inspection, or game internals.

## Ubiquitous Language

| Term | Meaning |
| --- | --- |
| Screen state | The current game screen category, such as training selection, dialogue, shop, or region movement. |
| Observation | Structured data extracted from a screenshot, such as OCR text, fail rate, item price, rank, and clickable rectangles. |
| Policy | Rules that rank possible actions from an observation. |
| Action | The output of the policy: usually a click target, sometimes pause/skip/log. |
| Region map | Resolution-specific rectangles for OCR zones, buttons, and color-detection areas. |
| Anchor | Reliable text, button, template, or color signal used to classify a screen. |
| Training choice | One of the five available trainings, with OCR stat gain, colored ring, fail rate, and click target. |
| Colored ring | Visual training signal such as blue, gold, or rainbow. It increases training priority. |
| Safe mode | Conservative behavior where low-confidence or unknown decisions pause instead of clicking. |

## Current Product Shape

The first version should be an assisted automation pipeline:

1. Recognize live screen.
2. Produce a proposed action.
3. Log the reason.
4. Click only when confidence passes thresholds.

Autonomous clicking comes after the offline screenshot harness is reliable.

## Design Principles

1. Keep OCR/CV separate from policy logic.
2. Prefer typed observations over raw text passed around the system.
3. Every click must have a reason and a known rectangle.
4. Unknown states are data collection opportunities, not guessing moments.
5. Start with fixed regions for one resolution, then generalize after screenshots prove the layout.
