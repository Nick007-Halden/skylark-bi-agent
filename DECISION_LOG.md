# Decision Log

## Key assumptions

- **Board IDs, not names, identify the boards.** The app takes monday.com board IDs as
  config rather than searching by board name, to avoid ambiguity if boards get renamed
  or duplicated during evaluation.
- **"Quarter" and other vague time references** are resolved by the LLM using the
  Tentative Close Date / Created Date fields already in the metrics payload; if a
  question has no resolvable time anchor, the agent states its assumption inline rather
  than blocking on a clarifying question.
- **Pipeline = deals with Deal Status = "Open".** Deals marked "Dead" or "Won" are
  reported separately (win rate, dead count) but excluded from "pipeline value" figures,
  matching how a founder would expect "pipeline" to be scoped.
- **Deal Name is the only usable cross-board key.** Deals uses `Client Code`
  (e.g. `COMPANY089`); Work Orders uses `Customer Name Code` (e.g. `WOCOMPANY_002`) —
  different masking namespaces with no overlap. The masked `Deal Name` (e.g. "Sakura")
  is shared but repeats across many unrelated records in both sheets. I treat any join
  on it as **approximate** and hard-code that caveat into every cross-board analytics
  function's output, so the agent cannot present it as exact.
- **Numeric fields with unit suffixes** ("5360 HA", "40MW", "2 location") are parsed by
  extracting the leading numeric value and discarding the unit. This is a defensible
  default for aggregate sums but means "HA" and "MW" quantities get summed together if a
  query spans work types — flagged as a data-quality note whenever it affects an answer.

## Trade-offs chosen and why

- **Keyword-based intent routing instead of an LLM planner call.** A second LLM call to
  classify intent adds latency and a second point of failure for a 6-hour build. A small,
  transparent keyword router is easy to audit, fast, and covers the founder-question
  patterns in the brief. Trade-off: less flexible than an LLM planner for very novel
  phrasings — the "general" fallback path mitigates this by handing the LLM a broad
  metrics bundle plus the list of available sectors, so it can still self-route within
  its own answer or ask a clarifying question.
- **Streamlit over a separate React/FastAPI stack.** Skylark's evaluators need a hosted,
  testable link inside a 6-hour window. Streamlit Community Cloud deploys directly from
  a GitHub repo with zero infra work, and keeps the architecture (client → cleaner →
  analytics → LLM) just as clean internally as a split frontend/backend would, without
  the deployment overhead. Trade-off: less UI polish than a custom frontend.
- **Short-TTL in-memory cache (60s) instead of no cache or a persistent DB.** Satisfies
  "query monday.com dynamically" (never a static hardcoded source) while avoiding
  redundant API calls within one user session. A persistent cache/warehouse would be the
  right call at production scale — noted below.
- **The LLM only ever receives computed metrics, never raw rows.** This is the single
  biggest reliability decision in the project. LLMs are unreliable at arithmetic over
  many rows and at parsing inconsistent formats; pandas is not. This also keeps prompts
  small and cheap regardless of board size.

## How I interpreted "prepare data for leadership updates"

I implemented it as an on-demand conversational command ("prepare my weekly leadership
update" / similar phrasing) rather than a scheduled email/export, since the brief scopes
this as optional and the core deliverable is the conversational agent itself. Triggering
it calls `analytics.leadership_update()`, which bundles pipeline, operations, billing,
and cross-board risk metrics, and the system prompt instructs the LLM to structure the
answer as: Sales / Operations / Billing / Risks / Recommendations — mirroring what a
founder would actually forward to their team. Given more time, I'd add a one-click
"export as PDF/Slack message" action on top of this same data bundle.

## What I'd do differently with more time

- **Semantic/fuzzy sector matching** (embeddings or a maintained synonym table) instead
  of the current exact-match-plus-canonical-dict approach in `cleaner.py`, so an
  unrecognized sector variant doesn't need a manual code addition.
- **A real join key.** I'd push back to the business to get a shared deal ID across both
  boards (or ingest a mapping table) rather than relying on repeated masked names —
  this is the single highest-value data-quality fix available.
- **Persistent metrics warehouse** (e.g. nightly ETL into a small Postgres/DuckDB store)
  so historical trend questions ("how has pipeline grown over the last 6 months") don't
  depend on monday.com's current-state API responses alone.
- **Automated tests** for `cleaner.py`'s parsers against the actual messy value patterns
  seen in the sheets (unit suffixes, `#VALUE!`, blank cells) — skipped due to the time-box
  but straightforward to add given the pure-function design.
- **Streaming responses** in the chat UI for perceived latency, and a proper LLM-based
  planner (with tool-calling) once keyword routing's limits are actually hit in practice.
