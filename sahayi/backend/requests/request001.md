# Request 001 — Repository docs

## Change
- Created root `README.md` with project overview, layout, setup, and contributor rules.
- Improved `AGENTS.md` with verified backend/frontend commands, `rules.md` hard rules, and the `requests/request{id}.md` backend-edit workflow.

## Rationale
Future contributors and OpenCode sessions needed a single entry point and
repo-specific gotchas (orchestrator-only agent calls, Safety Agent first, no
audio stored, how to run `test_*.py`).

## Affected areas
- `README.md` (new)
- `AGENTS.md` (updated in place)

## Verification
- `npm run build` from `sahayi/frontend/` (frontend sanity check).
- Backend `python test_api.py` once `.env` + `python seed.py` are in place.
