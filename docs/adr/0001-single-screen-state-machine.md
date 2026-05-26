# ADR 0001: Single-Screen State Machine

## Status

Accepted

## Context

The Starsavior trainer must run against the PC client and make decisions from a single visible game interface. The user wants recognition and decision support for training selection, rest submenu, event choices, relic choices, commissions, shop purchases, region movement, initial start, and dialogue skipping.

The dangerous failure mode is clicking a valid-looking button on the wrong screen.

## Decision

Model the assistant as a state machine:

1. Classify the screen from anchors.
2. Extract a typed observation for that screen.
3. Run only the policy that matches the classified screen.
4. Emit an action with a click rectangle and reason.
5. Pause on low confidence or unknown screens.

OCR and computer vision are adapters. They produce observations, but they do not choose actions.

## Consequences

This design makes the first version slower to write than a direct chain of image checks, but it gives us safer automation and clearer logs.

It also means screenshot collection is a first-class workflow. Each screen state needs saved examples before autonomous clicking should be trusted.
