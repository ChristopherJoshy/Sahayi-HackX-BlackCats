# Request 034 - Fix "Okay brother" filler and context-fixation on wrong topic

## Goal

Two concrete defects from a live Malayalam call log:

1. The companion opened almost every turn with "ശരി, ചേട്ടാ" (Okay, brother)
   — robotic, and wrong-gendered for a female patient. It had become a fixed
   filler the model copied from prompt examples and fallback phrasing.
2. Context confusion: after the patient mentioned a neighbour's baby, the
   companion asked "how's the baby?" FOUR turns in a row, even after the patient
   said "അത്" (that one) and "ഇഷ്ട്ടെ ലാക്കാത്തി" (I don't care). It fixated on a
   stale topic instead of following the patient's current turn.

## Changes

- `agents/main_companion.py` system prompt:
  - Added a GOLDEN RULE making the CURRENT patient turn the absolute priority:
    follow the patient when they change subject; immediately DROP a topic once
    they move on or show disinterest (short "അത്"/"ഇല്ല"/"I don't care" etc).
    This overrides all other flow instructions.
  - Demoted "pivot to a new topic" to only trigger when the patient gives
    almost nothing to respond to (bare yes/okay), fixing the over-eager
    topic-switching that caused unrelated replies.
  - Added VOICE REPAIR rule banning the fixed "Okay brother"/"ശരി, ചേട്ടാ"
    opener; the model must use the patient's real name or fitting warmth.
- `tests/test_companion_humanlike.py`: added cases for the filler ban and the
  current-turn priority.

## Validation

- `python tests/test_companion_humanlike.py` — all 15 cases pass.
