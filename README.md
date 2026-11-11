# CupSwap — an agent-to-agent marketplace for World Cup 2026

MIS 552 · AI for Digital Platforms · Homework 3. A fictional fan-to-fan ticket resale platform where a **buyer
agent**, a **seller agent** and a **platform agent** transact under marketplace rules, an **operations workflow**
handles a storm postponement, and the **Fair-Drop desk** (innovation feature) keeps organizer releases fair when
agents race humans. Everything runs on mock tools and synthetic data: no real money, tickets, emails or scraping.

## Run it (cached demo mode — no API key needed)

```bash
pip install -r requirements.txt
streamlit run app.py
```

Open http://localhost:8501. The app starts in **Cached demo** mode, which replays the recorded LLM responses for the
bundled scenarios. Tools, guards, rule engines, approvals and state changes all run for real against the local mock
data, so every feature works without a key.

## Live mode (optional)

```powershell
$env:OPENAI_API_KEY = "sk-..."     # PowerShell; on macOS/Linux: export OPENAI_API_KEY=sk-...
streamlit run app.py
```

Switch the sidebar to **Live**. The key is read only from the environment and is never written to disk. Live runs
are saved under `recordings/live/`. Optionally set `CUPSWAP_MODEL` (default `gpt-4o-mini`).

To re-record the canonical cached scenarios (about $0.02 in total):

```bash
python scripts/record_all.py              # or a subset: python scripts/record_all.py nego_success
```

## Project site

A static showcase of the project (screenshots, how each agent works and how to run it) is published at
**https://gitty-hash.github.io/CupSwap/**. GitHub Pages serves static files only, so the interactive app itself
runs locally with the commands above.

## How to operate each agent

Use the top navigation to open a page. The sidebar is shared by all pages: **Run mode** (Cached demo or Live API),
**Replay speed** (cached mode only), the session token and cost meter, the safety rails, and **Reset demo data**.
Press **Reset demo data** between runs to start from a clean state. Cached mode needs no API key; every approval
button below is a real gate, and nothing irreversible happens until you click it.

### 1. Buyer Agent (Part B, single agent with plan mode and memory)

1. Open **Buyer Agent**. Under *The request*, choose a fan profile: **Sofía** (Mexico supporter, Dallas) or
   **Julien** (France supporter, New York). Both get the same request: two tickets together for a Round-of-16 match
   under $400 total.
2. Leave **Call check_match_status via the MCP server** on to use the bonus MCP server, or turn it off to call the
   same tool as plain Python.
3. Click **Draft a plan**. The agent proposes numbered steps and the memory it applied, but takes no action yet.
4. Click **Approve plan & run agent**. (In Live mode you can instead type feedback and click **Revise plan**.)
   Watch the think → act → observe loop fill the **Agent trace** at the bottom.
5. Review the recommendation (listing, total, why, rejected alternatives). Click **Approve purchase** to record a
   mock order, or **Decline & release hold**.
6. Compare the **Long-term memory** cards, *before* and *after*, and the diff. Run the other fan with the same
   request to see how memory changes the search and the final choice.

Limits: 10 steps, 14 tool calls. A purchase and the memory update only happen after your click.

### 2. Negotiation Arena (Part C, buyer, seller and platform agents)

1. Open **Negotiation Arena** and pick a scenario: **Deal** (Sofía's agent and listing L10, where the ask exceeds
   the price cap) or **No deal** (Julien's agent and listing L19, where the seller floor is above the buyer ceiling).
2. Click **Run negotiation**. The platform agent verifies the ticket and applies the price cap, then the buyer and
   seller agents trade offers for at most 5 rounds. Each message shows rule-check badges.
3. If an agreement is reached, click **Approve purchase** (the platform then records the settlement and its 8%
   fee) or **Decline**. A no-deal run ends gracefully at the round cap.
4. Switch on **Analyst view** to reveal each side's hidden floor and ceiling, then read **Who captured the surplus**
   and the **Leakage test**.

### 3. Operations Desk (Part D, fixed workflow for a storm postponement)

1. Open **Operations Desk**. The event card shows the postponed match.
2. Click **Ingest weather feed & run the refund-or-keep workflow**. All 14 orders are classified, matched to a cited
   policy, checked by the recovery rules and routed.
3. Work the **Approval queue**: **Approve** or **Reject** refunds above $500, **Approve account flag** or
   **Dismiss flag** for suspected fraud, and **Resolve** the escalated case (O-1010).
4. In the **Human-on-the-loop monitor**, tick **Escalate** on any case and click **Escalate selected** to pull it to
   a human.
5. Pick a case in the **Case inspector** (try O-1009, O-1010 and O-1014) to see its path, the classifier's reasoning
   and the cited policy text.

### 4. Fair-Drop Desk (Part E, innovation feature for organizers)

1. Open **Fair-Drop Desk** and expand **All incoming requests** to see the 20 requests (10 from an agent API and
   10 from a web form).
2. Click **Close the window & run Fair-Drop**. The integrity filter, need assessment, seeded lottery and fairness
   judge run in order.
3. Read the headline numbers (first-come-first-served versus Fair-Drop), the **Who gets the tickets** chart, the
   integrity table, the judge's verdict and the need assessment with its guard corrections.
4. As the organizer, click **Approve allocation** or **Send back for revision**. Nothing is allocated until you approve.

### 5. Audit Log

Open **Audit Log** after any run to see every state change, who made it (agent, workflow or human) and whether a
human approved it, plus the mock ledgers.

### Running the agents live

Set `OPENAI_API_KEY` (see *Live mode* above), switch the sidebar to **Live API**, and repeat any flow. In Live mode
you can edit the buyer's goal, revise a plan with feedback and run any scenario against the model. Live runs are
saved under `recordings/live/`.

## Requirements coverage

| HW3 requirement | Where |
|---|---|
| Plan mode with approval before any action | `cupswap/buyer_agent.py` `draft_plan` + Buyer page gate |
| ReAct with ≥4 tools via strict function calling | `cupswap/buyer_tools.py` (6 tools, strict JSON schemas, `thought` field on every call) |
| Long-term memory loaded at start, updated at end; two profiles | `cupswap/memory.py`, `data/profiles/`, memory panel before/after |
| Trace timeline (tool, args, result summary) | `cupswap/trace.py`, `ui/common.py::render_trace` |
| 3 roles with own prompts; hidden floor + kickoff-proximity concession; verify_ticket; price cap + fee; settlement | `cupswap/negotiation.py`, `cupswap/prompts.py` |
| Bounded alternating offers (5 rounds) + shared state | `negotiation.run` / `public_view` |
| Success with human approval, failure at round cap, leakage test | Negotiation page; `negotiation.leakage_report` |
| Trigger → LLM classification (4 routes) → policy retrieval + citation → conditional branch | `cupswap/operations.py` |
| Approval gate above threshold ($500), monitor table with escalate control | Operations page |
| Failure + recovery rule | R5 (O-1014 mis-route), R4 (O-1010 retrieval miss → re-query + escalate), R1–R3 |
| Innovation feature | `cupswap/fairdrop.py` + Fair-Drop page |
| ≥4 tabs/pages, no raw JSON walls, explicit approval clicks | `app.py` (6 pages) |
| Hard caps on every loop | `cupswap/config.py` (buyer 10 steps / 14 tool calls, 5 rounds, platform 4 steps) |
| Mock data minimums | `scripts/build_data.py` → `data/` (23 listings, 6 upcoming matches, 6 host cities, 14 orders straddling $500, 3 policies, 2 profiles) |
| Cached demo mode, key from env | `cupswap/llm.py`, `recordings/` |
| Bonus: MCP server | `cupswap/mcp_server.py` (MCPServer, stdio) + `cupswap/mcp_client.py` (list_tools → schema, call_tool); toggle on the Buyer page |
| prompts.md with iterations | `prompts.md` (generated by `scripts/export_prompts.py`), evidence in `recordings/iteration_evidence/` |

## Project layout

```
app.py                      Streamlit entry (st.navigation, 6 pages)
cupswap/                    agents, tools, workflow, LLM client (live/record/cached), trace, store, MCP
ui/                         one module per page + shared trace renderer
data/                       bundled synthetic seed data (listings, matches, events, orders, policies, profiles, Fair-Drop)
state/                      mutable mock "databases" (created from data/ on first launch; Reset restores it)
recordings/                 canonical recorded runs (+ .result.json evidence), live/ runs, iteration_evidence/
scripts/                    build_data.py, record_all.py, export_prompts.py, build_report_evidence.py
tests/                      headless AppTest suite (cached mode, no key): python -m pytest tests -q
report/                     REPORT_TEMPLATE.md + REPORT_EVIDENCE.md (facts extracted from recordings)
```

## Testing

```bash
python -m pytest tests -q     # drives every page through Streamlit AppTest in cached mode
```
