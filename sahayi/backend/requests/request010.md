# Request 010 — Scalability, alert center, scroll + dynamic sidebar fixes

## Context
After request009 the console looked good but had real usability gaps for doctors with large
patient panels:
- Hypothesis / research / population panels crowded the dashboard even with many patients.
- No first-class alert surface — emergencies, follow-ups, and critical patients had no
  unified entry point.
- Top of the page felt "stuck"/not scrollable (content sat under the fixed navbar).
- Sidebar was static; doctors wanted it out of the way until needed.

## Changes
1. **Scalability** — Right rail is now tabbed: "Live" (active call + latest summary) and
   "Insights" (hypothesis + population research). Insights no longer render by default, so a
   large roster stays focused on the Attention Queue + Patient Risk grid.
2. **Alert center** (`components/Alerts/AlertCenter.jsx`) — navbar bell with unread badge
   (red for critical, amber otherwise) and a dropdown list. `buildAlerts()` unifies:
   emergency cascades, critical-status patients, follow-up-due, and live calls; ranked
   critical-first. Fed from `App` via `live` + a lightweight patient roster snapshot.
3. **Scroll fix** — added `.content-area` with `pt-16` (clears the fixed navbar) and
   `pb-24 lg:pb-8` (clears the mobile bottom nav). Navbar is `fixed`; content now flows below it.
4. **Dynamic sidebar** — rail is `fixed` and collapsed to icons (`w-[4.5rem]`) by default;
   expands to `w-60` on hover. An invisible left-edge hover-zone (`w-3`) opens it as the
   cursor approaches. Content gets `lg:ml-[4.5rem]` so it's never hidden. Labels fade in/out.
5. **Socket ownership** — `App` owns the single dashboard WebSocket and passes `live` +
   `patients` + `connectionState` to `Dashboard` (Dashboard no longer opens its own socket).

## Verification
- `npm run build` passes (2344 modules, no warnings).
- Alert center, tabs, dynamic rail, and scroll offset all implemented against real WS events.

## Status
Done.
