# Skylark Drones BI Agent

This is my submission for the monday.com Business Intelligence Agent assignment.

The idea: a founder can ask plain English questions like "how's our pipeline for Mining this quarter" or "prepare my weekly leadership update," and the agent pulls live data from two monday.com boards (Deals and Work Orders), cleans it up, and answers with real numbers.

## How it's built

I split this into layers instead of just throwing everything at an LLM:

1. `monday_client.py` talks to monday.com's GraphQL API and pulls the raw rows from both boards. Nothing is hardcoded or cached permanently, every session pulls fresh data (with a short 60 second cache just so I'm not hammering the API on every keystroke).
2. `cleaner.py` takes that raw, messy data and cleans it up. The real spreadsheets have stuff like "5360 HA", "40MW", "#VALUE!" errors, missing dates, and inconsistent sector names, so this file handles all of that with plain Python, no LLM involved.
3. `analytics.py` computes the actual business numbers: pipeline value, sector breakdowns, delayed projects, billing status, and a rough join between the two boards to spot risk (deals that closed but execution is delayed).
4. `agent.py` is the only file that talks to Claude. It sends the already computed metrics (not raw rows) along with the founder's question, and Claude writes the answer, decides what's relevant, and calls out any data quality issues.
5. `streamlit_app.py` is the actual chat interface people use.

I did it this way on purpose. LLMs are bad at doing math over hundreds of rows and tend to hallucinate numbers if you dump raw data on them. So I let Python do all the counting and let Claude do the explaining. This is basically the standard pattern for reliable AI agents right now.

## Why the numbers can be a bit off between the two boards

Worth being upfront about this: Deals and Work Orders don't actually share a clean ID. Deals uses something like `COMPANY089` as the client code, Work Orders uses something like `WOCOMPANY_002`. Different systems entirely. The only thing they share is a masked deal name (like "Sakura" or "Tanjiro"), and those names repeat a lot across unrelated deals in both sheets.

So when the agent tries to connect a deal to its execution status, it's matching on deal name plus sector as a best guess, and it always says so in the answer. I didn't want to pretend this was a clean join when it isn't, more on this in the decision log.

## Setting up monday.com

1. Make a free monday.com account if you don't already have one.
2. Create two boards: one called Deals, one called Work Orders.
3. Import the given CSVs into each (File > Import in monday.com).
4. A few columns are worth setting up properly instead of leaving as plain text:

Deals board: Deal Status, Closure Probability, Deal Stage, and Sector/service work well as Status or Dropdown columns. Masked Deal value should be Numbers. The date columns (Close Date, Tentative Close Date, Created Date) should be Date columns.

Work Orders board: Execution Status, Sector, Invoice Status, Billing Status and WO Status work well as Status/Dropdown columns. Dates (PO/LOI, Probable Start/End) as Date columns. Leave the amount columns as they are, even the messy ones with unit text like "5360 HA" or "#VALUE!" errors, since `cleaner.py` is built to handle exactly that. Don't pre-clean these in monday.com, it'll mess with the parsing logic.

5. Grab your personal API token from monday.com: click your avatar top right, go to Developers, then My Access Tokens.
6. Get each board's ID from its URL, it's the number after `/boards/`.

## Running it locally

```
git clone <this repo>
cd skylark-bi-agent
pip install -r requirements.txt
cp .env.example .env
```
Fill in your MONDAY_API_TOKEN and ANTHROPIC_API_KEY in that .env file, then:
```
streamlit run app/streamlit_app.py
```
Type your two board IDs into the sidebar and start asking questions.

## Deploying it (this is the hosted link I'm submitting)

I used Streamlit Community Cloud since it's free and deploys straight from GitHub.

1. Go to share.streamlit.io, sign in with GitHub.
2. New app, point it at this repo, main file path `app/streamlit_app.py`.
3. In the app's settings, add these two secrets:
```
MONDAY_API_TOKEN = "your token"
ANTHROPIC_API_KEY = "your key"
```
4. Deploy and share the link it gives you.

## What I know isn't perfect

- The cross board join is approximate, explained above and in the decision log.
- I used simple keyword matching to figure out what kind of question is being asked instead of a second LLM call, mainly to keep things fast and easy to debug within the time I had. Details in the decision log.
