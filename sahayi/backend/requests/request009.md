# Request 009 — Frontend refactor: professional clinical console

## Goal
Replace the dark, unprofessional dashboard with a clean, light, clinically-focused doctor
console. The previous UI was described by the team as looking like "AI vomited" — too dark,
random graphs, no clear hierarchy. This refactor delivers a calm, professional monitoring
console for time-poor clinicians.

## Design decisions (research-driven)
- **Palette**: light clinical `canvas #F7F9FB` + white surfaces, teal brand `#0D9488`
  (distinct from generic medical blue), semantic green/amber/red risk colours.
- **Type**: Sora (display) + Inter (body) + JetBrains Mono (data/labels). Dropped the serif.
- **Layout**: persistent dark left rail (anchor/contrast) + light content. Critical-first:
  an **Attention Queue** pulls red/amber patients to the top automatically, then a full
  patient-risk grid, then a right rail of live alerts + research.
- **Signature element**: the "Vitals Pulse" `RiskMeter` — a segmented bar that fills to the
  risk score and shifts colour by status, with a trend readout. No random charts.

## Privacy (hard rule)
Doctor dashboard shows ONLY clinical signals: risk, status, symptoms, trends, calls.
Patient personal messages / conversation transcripts are NEVER rendered. The old
`PatientCard` (live signal dump) and `KnowledgeGraph` were removed; `PatientProfile`
shows clinical signals, conditions, meds, contacts, risk, calls — no transcripts.

## Files
- `tailwind.config.js`, `src/styles/index.css`, `index.html`: new tokens, fonts, light theme.
- `src/lib/format.js` (new): shared phone/status/time helpers.
- `src/components/ui/{Panel,RiskBadge,RiskMeter,StatusDot}.jsx` (new): primitives.
- `src/pages/Dashboard.jsx`: attention queue + risk grid + alerts rail.
- `src/pages/Patients.jsx`, `src/pages/PatientProfile.jsx`: clean clinical views.
- `src/components/Layout/{Sidebar,Navbar,MobileNav}.jsx`, `src/pages/Login.jsx`,
  `Setup.jsx`, `Settings.jsx`, `Debug.jsx`, `AgentDebugPanel.jsx`: new theme.
- Deleted dead components: `RiskFeed.jsx`, `PatientCard.jsx`, `KnowledgeGraph.jsx`.
- `hooks/useWebSocket.js`: derives live state (attention, summary, hypothesis, emergencies).

## Verification
- `npm run build` passes (2343 modules).
- No Firebase, no `127.0.0.1`, no `dark:bg-black`/`medical-card` references remain.
- Theme defaults to light; rail stays dark for contrast.

## Status
Done.
