# Request 030 - Natural Malayalam voice-turn repair

## Goal

Make the Malayalam telephone companion respond naturally when speech is
ambiguous or the caller criticises the conversation, while avoiding long TTS
playback that delays the next caller turn.

## Changes

- Explicitly instruct the companion to repair a misunderstanding without
  claiming to be human or arguing with the caller.
- Keep ordinary-query answers direct and spoken replies short.
- Reduce the voice reply token ceiling and cap unusually long output at a
  word boundary before TTS.
- Use the known warm opener when the model returns an unusably short opening.

## Validation

- Run the focused companion and voice pipeline scripts from `backend/`.
- Make a Malayalam call and inspect the STT transcript, companion reply, and
  TTS timing logs for each turn.
