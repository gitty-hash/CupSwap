# CupSwap — Design Report (template)

Target 1,500–2,200 words (appendix excluded). Follow the HW3 template order. Facts, quotes and numbers for every
section are in `REPORT_EVIDENCE.md`; **the reasoning must be yours** (HW3 §9.3: autonomy decisions, trace and
negotiation analyses, failure diagnoses and ethics reflect your own judgment). The bullets below are questions to
answer, not text to paste.

## 1. Scenario and agentic design brief (~1 page, ~550 words)
- Scenario in your own words (one short paragraph).
- **Stakeholder map** (at least 3): fans buying, ticket holders reselling, platform trust & ops team, tournament
  organizers. For each, give their goal on the platform and the pain point *your* agents address.
- **Autonomy decisions:** for each agent (buyer, seller, platform, ops workflow, Fair-Drop), say who writes the plan:
  a hard-coded workflow, an LLM-generated plan, or a human-imposed objective. Say why.
- **Every state-changing action, marked gated or monitored.** The Overview page lists what is implemented: hold,
  purchase, memory update, settlement, refund ≤/> threshold, reissue, freeze, dispute queue, account flag, Fair-Drop
  allocation, trust-review hold. Defend *where you drew the line*. Why is a 15-minute hold only monitored while the
  purchase is gated?
- **Framework choice: custom loop on the OpenAI Chat Completions API.** Give at least two trade-offs from your own
  experience: transparency (you can see every message), traceability (the trace logs each think/act/observe), setup
  burden (no framework, but you wrote the loop), control (code guards enforce constraints). What would LangGraph or
  the Agents SDK have given you instead?

## 2. Trace walkthrough (~½ page)
- Quote at least 3 think → act → observe steps from one buyer run (the Julien run has a guard refusal followed by a
  recovery, which makes a good story).
- Interpret, don't narrate: why L18 over L17 and over L14? Check each stated rejection reason against what the
  agent actually observed in its trace. Are they all true? Find one moment where **memory or a constraint changed
  behavior**. Compare Sofía's run on the same request.

## 3. Negotiation analysis (~½ page)
- **Who captured the surplus, and why?** Use the numbers: ZOPA, buyer surplus, seller surplus after the 8% fee, and
  the platform fee. Is the seller's floor set before or after the fee? What does that mean for a platform owner?
- **Leakage test:** did any agent reveal its floor or ceiling? Compare v1 (the "my ceiling is $300" evidence in
  prompts.md) with the current version. What would leakage mean in a real agent-to-agent market where the
  counterparty logs everything? Is "behavioral" leakage avoidable?
- **What the failed negotiation shows** (no ZOPA; it ended gracefully at the round cap).

## 4. Workflow analysis (~½ page)
- How the 14 cases routed (refund / keep / disputed / fraud / escalated).
- **Approval threshold: state it and defend it in one sentence**, connecting it to Chapter 6's rule that high-stakes,
  irreversible actions keep a human in the loop. (Default $500; change `REFUND_APPROVAL_THRESHOLD` in
  `cupswap/config.py` if you choose differently, then re-run.)
- **Failure case + recovery rule:** O-1014 (classifier mis-route caught by R5) and/or O-1010 (retrieval miss caught
  by R4 → re-query + escalate). Diagnose why each failed. Also mention the v1 sarcasm failure (O-1009) that *no rule*
  could catch: what does that say about guards versus prompt quality?

## 5. Innovation feature rationale (~½ page) — Fair-Drop desk
- Target stakeholder: tournament organizers (plus fans without agents).
- Decision improved: allocating scarce face-value releases when agents race humans.
- One thing that could go wrong, and your mitigation. Candidates you observed: eloquent unverifiable stories (R08),
  prompt injection (R10), an assessor under-ranking verified fans (guard corrections), and the judge's concern.

## 6. Ethics note (2–3 sentences)
- Pick one: fairness for fans without agents, manipulation between agents, accountability for a wrong purchase, or
  foreign-language fans (the classifier handled French, Portuguese and Arabic).

## 7. AI-use disclosure
- Which tools you used (e.g. Claude Code for building the app and the data script; gpt-4o-mini as the agents' model),
  what tasks they did, and how you verified their output (the AppTest suite in `tests/`, reading traces, checking
  recordings).

## 8. Appendix (not counted)
- 2–3 **live-mode** screenshots: run the app with your key, switch the sidebar to *Live*, run e.g. the buyer agent
  and a negotiation, then screenshot the trace / transcript.
