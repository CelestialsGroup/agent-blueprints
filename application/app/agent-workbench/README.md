# Agent Workbench

Phase: **0E, not implemented**.

This Next.js application will provide Chat, Plan, Timeline, Terminal, Files,
Artifact, and read-only replay views. Its BFF may handle same-origin cookies,
CSRF, and one-time token exchange, but must not own WorkOrder, RuntimeSession,
Event, Artifact, or authorization truth.

All server state comes from Agent Access REST/SSE and Runtime Gateway. Browser
state is disposable, and Provider-private events must be projected by the
platform before the UI consumes them.
