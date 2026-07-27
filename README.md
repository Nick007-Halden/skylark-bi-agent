# Skylark Drones — monday.com Business Intelligence Agent

A conversational BI agent that answers founder-level questions ("How's our pipeline for
Mining this quarter?", "Prepare my weekly leadership update") by pulling **live** data
from two monday.com boards (Deals, Work Orders), cleaning it, computing real metrics,
and having an LLM explain the results — never do the arithmetic.

## Architecture

```
Founder question
      │
      ▼
Intent router (keyword-based, app/agent.py:route_intent)
      │
      ▼
monday.com GraphQL API  ──►  app/monday_client.py   (live fetch, short TTL cache, no hardcoded CSVs)
      │
      ▼
app/cleaner.py   — parses messy numbers/dates/text, normalizes sector names,
                    tracks every ambiguity as a "data quality note"
      │
      ▼
app/analytics.py — pandas aggregations: pipeline value, sector breakdowns,
                    execution status, billing/collections, cross-board risk join
      │
      ▼
app/agent.py     — sends ONLY the computed metrics (JSON) + data quality notes
                    to Claude, which writes the analyst-style answer,
                    asks clarifying questions, and surfaces caveats
      │
      ▼
app/streamlit_app.py — chat UI, the deployable entrypoint
```

**Core design decision:** the LLM never sees raw or bulk row-level data. It only ever
sees pre-computed, already-correct aggregate numbers. This avoids LLM arithmetic errors
and hallucinated figures — a known failure mode when you dump hundreds of spreadsheet
rows into a prompt and ask for a sum. See `DECISION_LOG.md` for the full reasoning.

## Repo structure

```
app/
  monday_client.py   # GraphQL client — auth, pagination, board reads
  cleaner.py         # deterministic cleaning/normalization (pandas)
  analytics.py        # business metrics + cross-board join
  agent.py            # LLM layer: intent routing + answer generation
  streamlit_app.py    # chat UI / entrypoint
requirements.txt
.env.example
DECISION_LOG.md
README.md   (this file)
```

## Setting up monday.com

1. Create a free monday.com account / workspace if you don't have one.
2. Create **two boards**: `Deals` and `Work Orders`.
3. Import the provided CSVs into each board (File → Import, or paste as a new board from
   spreadsheet). Set these column types (monday.com will guess most of them — the ones
   below need attention because the raw data is messy free text):

   **Deals board**
   | Column | Type |
   |---|---|
   | Deal Name | Text (this is the item's Name column) |
   | Owner code | Text |
   | Client Code | Text |
   | Deal Status | Status/Dropdown |
   | Close Date (A) | Date |
   | Closure Probability | Status/Dropdown |
   | Masked Deal value | Numbers |
   | Tentative Close Date | Date |
   | Deal Stage | Status/Dropdown |
   | Product deal | Text |
   | Sector/service | Status/Dropdown |
   | Created Date | Date |

   **Work Orders board**
   | Column | Type |
   |---|---|
   | Deal name masked | Text (item Name column) |
   | Customer Name Code | Text |
   | Execution Status | Status/Dropdown |
   | Date of PO/LOI, Probable Start Date, Probable End Date | Date |
   | BD/KAM Personnel code | Text |
   | Sector | Status/Dropdown |
   | Type of Work | Text |
   | Amount / Billed / Collected / Receivable columns | Numbers (several source cells contain
     unit suffixes like "5360 HA" or errors like "#VALUE!" — leave these as Text/Numbers in
     monday.com as-is; `app/cleaner.py` handles the extraction, don't pre-clean in monday.com) |
   | Invoice Status, Billing Status, WO Status (billed) | Status/Dropdown |

4. Generate a **Personal API Token**: monday.com → your avatar (top-right) → Developers →
   My Access Tokens → copy the token.
5. Get each board's **ID** from its URL: `monday.com/boards/1234567890` → `1234567890`.

## Running locally

```bash
git clone <your-repo-url>
cd skylark-bi-agent
pip install -r requirements.txt
cp .env.example .env   # fill in MONDAY_API_TOKEN and ANTHROPIC_API_KEY
export $(cat .env | xargs)   # or use python-dotenv / your shell's env loading
streamlit run app/streamlit_app.py
```

Enter the two board IDs in the sidebar and start asking questions.

## Deploying (free, hosted, no local setup needed to test)

1. Push this repo to GitHub.
2. Go to [share.streamlit.io](https://share.streamlit.io) (Streamlit Community Cloud),
   sign in with GitHub, "New app", point it at this repo and `app/streamlit_app.py`.
3. In the app's **Settings → Secrets**, add:
   ```toml
   MONDAY_API_TOKEN = "your_token"
   ANTHROPIC_API_KEY = "your_key"
   ```
4. Deploy. Share the generated `*.streamlit.app` link.

## Known limitations (see DECISION_LOG.md for full reasoning)

- Cross-board joins (Deals ↔ Work Orders) are approximate — the two boards don't share a
  reliable ID; the agent always labels these results as approximate.
- Intent routing is keyword-based rather than LLM-based, by design, for transparency and
  speed within the project's time-box — see Decision Log.
