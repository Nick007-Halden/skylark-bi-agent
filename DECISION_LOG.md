# Decision Log

## Assumptions I made

I treated "pipeline" as deals with Deal Status marked Open. Deals marked Won or Dead get counted separately (I show a win rate and a dead count) but I didn't include them in pipeline value, since that's how a founder would actually expect the word "pipeline" to be used.

For vague time references like "this quarter," I let the agent use whatever date fields are already in the data (Tentative Close Date, Created Date) and just state its assumption in the answer rather than stopping to ask every time. If it genuinely can't figure out what's being asked, it asks.

The biggest assumption, and the one I want to be upfront about: Deal Name is the only field that connects the two boards. Deals has a Client Code like COMPANY089, Work Orders has a Customer Name Code like WOCOMPANY_002. These are two completely different ID systems, they don't match up. The masked Deal Name (things like "Sakura" or "Tanjiro") is the only shared field, but it repeats across a lot of unrelated records in both sheets. So any time the agent connects a deal to its execution status, it's really just guessing based on name and sector, and I made sure that shows up as a caveat in the output every time, not just buried in this doc.

I also assumed numeric fields with weird unit text attached ("5360 HA", "40MW", "2 location") should just have the number extracted and the unit dropped. That's fine for adding things up in most cases, but it does mean quantities in different units (hectares vs megawatts) get summed together if a question spans different types of work. I flag this in the data quality notes whenever it comes up.

## Trade-offs and why

I went with a simple keyword based router to figure out what kind of question someone's asking, instead of using another LLM call to do that classification. A second LLM call adds latency and another thing that can go wrong, and for a project on a 6 hour clock, I wanted something I could actually test and reason about quickly. The downside is it's less flexible for really unusual phrasing, so I built in a fallback: if nothing matches clearly, the agent just gets a broad set of metrics plus a list of known sectors, and either figures it out on its own or asks a clarifying question.

I built this as a Streamlit app instead of a separate frontend and backend. Given the time limit and the requirement for a hosted link that's testable without any local setup, Streamlit Community Cloud deploys straight from GitHub with basically no infrastructure work. The internal code is still split cleanly into the same layers (client, cleaner, analytics, agent) it would be either way, I just didn't build a separate API server on top of it. The trade-off is it looks less like a custom product UI, more like a working tool.

I added a short (60 second) cache on the monday.com reads instead of no caching at all or a proper database. This keeps things fast within one session without ever treating cached data as the permanent source of truth. Every fresh session, or hitting refresh, pulls live again.

Probably the decision I care most about explaining: the LLM never sees raw rows, ever. It only gets numbers that Python already computed and double checked. I did this because LLMs are genuinely unreliable at doing arithmetic across a lot of rows, and I didn't want the agent confidently stating a wrong revenue number. Python does the counting, Claude does the explaining. Keeping prompts small this way also just makes the whole thing faster and cheaper regardless of how big the boards get.

## How I interpreted "prepare data for leadership updates"

Since this was listed as optional, I built it as something you ask for in the chat itself (something like "prepare my weekly leadership update") rather than a scheduled export or an email. Behind the scenes it pulls all four metric groups (pipeline, operations, billing, risk) at once and I instructed the agent to lay it out in sections: Sales, Operations, Billing, Risks, and Recommendations, basically what a founder would actually forward to their team as-is. If I had more time I'd add a one click PDF export on top of the same data.

## What I'd change with more time

The sector matching right now is a small dictionary of known spelling variants. A better version would use something fuzzier so it doesn't need manual updates every time a new spelling shows up in the data.

The real fix for the join problem between the two boards isn't something code can solve, it's a data problem. I'd want a shared deal ID across both boards rather than relying on repeated masked names. That's the single most useful thing that could improve this.

I'd also want a small database sitting behind this instead of relying purely on live monday.com reads, mainly so questions about trends over time (like "how has pipeline grown over the last six months") don't depend entirely on what the API returns right now.

I didn't write automated tests for the cleaning functions given the time limit, though the way they're written (small, pure functions) makes that pretty straightforward to add later.

Lastly, I'd swap the keyword router for an actual small LLM based planner once I hit real cases where keyword matching falls short, right now I just haven't hit those limits yet in testing.
