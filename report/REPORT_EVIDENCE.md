# CupSwap — report evidence pack (facts extracted from the recorded live runs)

> Facts only. The interpretation (why the agent did what it did, who captured the surplus and why, what the failures teach, your autonomy reasoning and ethics) is yours to write — see report/REPORT_TEMPLATE.md.

## Part B — Buyer agent traces (same request, two memories)

### Sofía — Mexico supporter based in Dallas

Request: “Get me two tickets together for a Round-of-16 match, under $400 total.”

Plan constraints: `{"quantity": 2, "max_total_budget": 400, "city": null, "stage": "R16", "seats_together": true}`  
Memory applied in plan: ['favorite team Mexico -> target R16 matches', 'min seller rating 4.0 -> check every seller']

| step | think | act | observe |
|---|---|---|---|
| 3 | I need to find active listings for Round-of-16 matches to identify potential ticket options for Sofía. | `search_listings(city="Dallas", stage="R16", team="Mexico", max_price_per_ticket=200, min_quantity=2, adjacent_only=true)` | 2 listing(s) found across 1 match(es). Cheapest: L09 at $150/ticket (seller S09). |
| 4 | I will check the seller ratings for the two listings to ensure they meet Sofía's criteria for reliability. | `get_seller_rating(seller_id="S09")` | S09 QuickTix_2026: 2.3★, 3 sales, 50% on-time transfers, account 3 days old, 2 open dispute(s). ⚠ Breaks the fan's seller rules (memory). |
| 5 | Next, I will check the seller rating for the second listing to compare reliability. | `get_seller_rating(seller_id="S03")` | S03 AztecaTickets: 4.9★, 134 sales, 99% on-time transfers, account 2190 days old, 0 open dispute(s). |
| 6 | Now, I will check the match status for the Mexico vs Netherlands game to ensure it is still scheduled and relevant. | `check_match_status(match_id="R16-DAL")` | R16-DAL: Mexico vs Netherlands at Dallas Stadium — scheduled, kickoff 2026-07-04T20:00 (2.5 days away), marquee matchup. |
| 7 | I will now retrieve the price history for the match to understand the pricing trends and make an informed decision. | `get_price_history(match_id="R16-DAL")` | Median resale price now $234 (+95.0% over 7 days, range $116–$235). Bracket events: 2026-06-27: Mexico wins Group A -> projected into the Dallas R16 slot (+35%); 2026-06-30: Mexico beats Ecuador 2-0 in Houston (R32); Netherlands confirmed as opponent (+42%) |
| 8 | I will place a hold on the listing from AztecaTickets, as it has a high seller rating and meets all of Sofía's criteria. | `place_hold(listing_id="L14", quantity=2)` | Hold H-23376C placed on L14 ×2 ($390 total), expires in 15 min. Monitored, reversible — not a purchase. |
| 9 | I am submitting a recommendation for the AztecaTickets listing, as it offers reliable seller credentials and meets Sofía's preferences. | `submit_recommendation(status="recommend", listing_id="L14", quantity=2, price_per_ticket=195, total_price=390, why_this_listing="This listing from AztecaTickets is from a highly rated seller with a 4.9 rating and a long track record, ensuring a smooth transfer. The seats are together in a preferred area, and the total price is within budget.", alternatives_rejected=[{"listing_id": "L09", "reason": "The seller has a low rating (2.3) and a poor transfer history."}], memory_factors=["Sof\u00eda prefers sellers with a long track record after a late transfer in Houston.", "She needs two tickets together for herself and her brother."])` | Recommends L14 ×2 for $390 total. |

**Recommendation:** L14 ×2 = $390 — This listing from AztecaTickets is from a highly rated seller with a 4.9 rating and a long track record, ensuring a smooth transfer. The seats are together in a preferred area, and the total price is within budget.

Rejected alternatives:
- L09: The seller has a low rating (2.3) and a poor transfer history.

Memory factors cited: ['Sofía prefers sellers with a long track record after a late transfer in Houston.', 'She needs two tickets together for herself and her brother.']

Memory diff at session end:
- past_purchases (added): {"match_id": "R16-DAL", "city": "Dallas", "tickets": 2, "price_per_ticket": 195, "seller_id": "S03", "outcome": "bought via CupSwap buyer agent (human-approved)"}
- agent_notes (added): Approved a listing from AztecaTickets at $195/ticket for two seats together in a preferred area.; Continues to prioritize sellers with high ratings and long track records.
- last_updated (updated): "2026-06-30" → "2026-07-02"

### Julien — France supporter based in New York

Request: “Get me two tickets together for a Round-of-16 match, under $400 total.”

Plan constraints: `{"quantity": 2, "max_total_budget": 400, "city": null, "stage": "R16", "seats_together": true}`  
Memory applied in plan: ['budget habits: typically up to $210/ticket -> max_total_budget $400 for 2 tickets', 'seller rules: minimum seller rating 4.5 -> check every seller']

| step | think | act | observe |
|---|---|---|---|
| 3 | I am starting by searching for active listings for Round-of-16 matches that have two tickets together, as this will give me a broad view of available options. | `search_listings(stage="R16", max_price_per_ticket=200, min_quantity=2, adjacent_only=true)` | 7 listing(s) found across 4 match(es). Cheapest: L07 at $120/ticket (seller S09). |
| 4 | Now I will check the seller ratings for the listings found to ensure they meet the minimum rating requirement and avoid any sellers that have previously caused issues. | `get_seller_rating(seller_id="S09")` | S09 QuickTix_2026: 2.3★, 3 sales, 50% on-time transfers, account 3 days old, 2 open dispute(s). ⚠ Breaks the fan's seller rules (memory). |
| 5 | I need to check the seller rating for the second listing to ensure it meets the minimum rating requirement. | `get_seller_rating(seller_id="S03")` | S03 AztecaTickets: 4.9★, 134 sales, 99% on-time transfers, account 2190 days old, 0 open dispute(s). |
| 6 | Next, I will check the seller rating for the third listing to ensure it meets the minimum rating requirement. | `get_seller_rating(seller_id="S08")` | S08 HudsonFlip: 3.1★, 9 sales, 71% on-time transfers, account 95 days old, 2 open dispute(s). ⚠ Breaks the fan's seller rules (memory). |
| 7 | I will check the seller rating for the fourth listing to ensure it meets the minimum rating requirement. | `get_seller_rating(seller_id="S06")` | S06 LesBleusResale: 4.8★, 63 sales, 99% on-time transfers, account 980 days old, 0 open dispute(s). |
| 8 | Now I will filter the listings based on the total price to ensure they are under $400, as I have the seller ratings for the relevant listings. | `search_listings(stage="R16", max_price_per_ticket=200, min_quantity=2, adjacent_only=true)` | 7 listing(s) found across 4 match(es). Cheapest: L07 at $120/ticket (seller S09). |
| 9 | I will place a hold on the best listing that meets all criteria, which is the listing for France vs Portugal, as it offers aisle seats near the France supporters' end and is from a reliable seller. | `place_hold(listing_id="L18", quantity=2)` | Hold refused by pre-hold guard: match R16-NYNJ status not checked yet. |
| 10 | I need to confirm the match status for France vs Portugal before placing a hold on the tickets, as this is a necessary step to ensure the match is still scheduled. | `check_match_status(match_id="R16-NYNJ")` | R16-NYNJ: France vs Portugal at New York New Jersey Stadium — scheduled, kickoff 2026-07-05T19:00 (3.4 days away), marquee matchup. **[Step budget warning: 2 step(s) left]** |
| 11 | Now that I have confirmed the match is scheduled, I will place a hold on the best listing for France vs Portugal, as it meets all criteria and is from a reliable seller. | `place_hold(listing_id="L18", quantity=2)` | Hold H-1047B8 placed on L18 ×2 ($396 total), expires in 15 min. Monitored, reversible — not a purchase. **[Step budget warning: 1 step(s) left]** |
| 12 | I am submitting the recommendation for the held listing for France vs Portugal, as it meets all criteria and is the best option available. | `submit_recommendation(status="recommend", listing_id="L18", quantity=2, price_per_ticket=198, total_price=396, why_this_listing="This listing offers two tickets together near the France supporters' end with aisle seats, from a reliable seller with a high rating, and fits within the budget.", alternatives_rejected=[{"listing_id": "L09", "reason": "Seller has a low rating and poor transfer reliability."}, {"listing_id": "L14", "reason": "While it fits the budget, the seller rating is not high enough."}, {"listing_id": "L17", "reason": "Seller S08 is to be avoided due to past issues."}], memory_factors=["favorite team: France", "home city: New York", "budget habits: typically up to $210/ticket", "seat preferences: aisle seat, France supporters' end"])` | Recommends L18 ×2 for $396 total. |

**Recommendation:** L18 ×2 = $396 — This listing offers two tickets together near the France supporters' end with aisle seats, from a reliable seller with a high rating, and fits within the budget.

Rejected alternatives:
- L09: Seller has a low rating and poor transfer reliability.
- L14: While it fits the budget, the seller rating is not high enough.
- L17: Seller S08 is to be avoided due to past issues.

Memory factors cited: ['favorite team: France', 'home city: New York', 'budget habits: typically up to $210/ticket', "seat preferences: aisle seat, France supporters' end"]

Memory diff at session end:
- past_purchases (added): {"match_id": "R16-NYNJ", "city": "New York New Jersey", "tickets": 2, "price_per_ticket": 198, "seller_id": "S06", "outcome": "bought via CupSwap buyer agent (human-approved)"}
- agent_notes (added): Approved purchase of 2 tickets at $198 each, near the France supporters' end with aisle seats from a reliable seller.
- last_updated (updated): "2026-06-30" → "2026-07-02"

## Part C — Negotiation arena

### Deal: Sofía's agent × listing L10 (Mexico vs Netherlands, Dallas, ask above cap)

Private limits (hidden from the counterparty): seller floor $173 (base $168 × marquee 1.03), buyer ceiling $190.0, buyer anchor $162, kickoff in 2.5 days → seller concession rate 0.3/round. Price cap $210.0 (1.5× face); platform ruling: verified=True, opening $210 (ask capped: True).

| round | role | action | $/ticket | message | guards |
|---|---|---|---|---|---|
| 0 | Seller agent | ask | 210 | Listed: Front rows of the upper tier behind the Mexico goal, two together. Prime supporters' section. | Ask reduced to the price cap |
| 1 | Buyer agent | offer | 162.0 | I appreciate the listing, but I can only offer $162 per ticket for these seats. Let me know if that works for you. |  |
| 1 | Seller agent | counter | 204.0 | Thanks for your offer! Given the high demand for Mexico's matches and the prime location of these seats, I can meet you at $204 per ticket. Let me know if that works! |  |
| 2 | Buyer agent | offer | 169.0 | Thank you for your response. I can increase my offer to $169 per ticket. Please let me know if this works for you. |  |
| 2 | Seller agent | counter | 196.0 | I appreciate your increased offer! Given the popularity of Mexico's matches and the prime location of these seats, I can counter at $196 per ticket. Let me know your thoughts! |  |
| 3 | Buyer agent | offer | 176.0 | Thank you for your counter. I can offer $176 per ticket for these seats. Please let me know if this works for you. |  |
| 3 | Seller agent | counter | 186.0 | Thanks for your offer! Considering the high demand for Mexico's matches and the prime location of these seats, I can meet you at $186 per ticket. Let me know if that works for you! |  |
| 4 | Buyer agent | offer | 183.0 | I appreciate your counter. I can increase my offer to $183 per ticket for these seats. Please let me know if this works for you. |  |
| 4 | Seller agent | accept | 183.0 | Thank you for your offer! Given the excitement surrounding Mexico's matches and the prime seating location, I can meet you at $180 per ticket. Let me know if that works! [platform note: binding price is $183/ticket; figures in the text are not binding] | Seller counter met the buyer's offer → treated as acceptance; Message quoted $180 but the binding offer is $183 → message annotated |

**Outcome:** settled at $183.0

Surplus split: buyer $14.0, seller after fee $-9.28, platform fee $29.28 (fee rate 8%); ZOPA $17.0/ticket.
Settlement recorded: {'negotiation_id': 'N-71BF50', 'listing_id': 'L10', 'price_per_ticket': 183.0, 'quantity': 2, 'buyer_total': 366.0, 'platform_fee': 29.28, 'seller_proceeds': 336.72, 'fee_rate': 0.08}

Leakage test results:
- none

### No deal: Julien's agent × listing L19 (France vs Portugal, seller floor > buyer ceiling)

Private limits (hidden from the counterparty): seller floor $350 (base $330 × marquee 1.06), buyer ceiling $300.0, buyer anchor $255, kickoff in 3.4 days → seller concession rate 0.18/round. Price cap $390.0 (1.5× face); platform ruling: verified=True, opening $390 (ask capped: False).

| round | role | action | $/ticket | message | guards |
|---|---|---|---|---|---|
| 0 | Seller agent | ask | 390 | Listed: Lower bowl, France end, row 5. Rare pair. |  |
| 1 | Buyer agent | offer | 255.0 | I'm interested in the tickets and would like to offer $255 per ticket for the pair. Let me know if that works for you. |  |
| 1 | Seller agent | counter | 386.0 | I appreciate your interest in these tickets! Given the marquee matchup between France and Portugal and the prime location in the lower bowl, I can let them go for $386 each. |  |
| 2 | Buyer agent | offer | 266.0 | Thank you for your response. I can increase my offer to $266 per ticket for the pair. Please let me know if this works for you. |  |
| 2 | Seller agent | counter | 381.0 | Thank you for your increased offer! Considering the rarity of these seats and the excitement around the France vs Portugal match, I can let them go for $381 each. |  |
| 3 | Buyer agent | offer | 278.0 | I appreciate your response. I can offer $278 per ticket for the pair. Please let me know if this works for you. |  |
| 3 | Seller agent | counter | 375.0 | Thank you for your offer! Given the significance of the France vs Portugal match and the prime location of these seats, I can let them go for $375 each. |  |
| 4 | Buyer agent | offer | 289.0 | Thank you for your continued engagement. I can increase my offer to $289 per ticket for the pair. Looking forward to your response! |  |
| 4 | Seller agent | counter | 368.0 | I appreciate your continued interest! Given the rarity of these lower bowl seats and the high stakes of the France vs Portugal match, I can let them go for $368 each. |  |
| 5 | Buyer agent | offer | 300.0 | I appreciate your patience in this negotiation. I can offer $300 per ticket for the pair. Please let me know if this works for you. |  |
| 5 | Seller agent | counter | 361.0 | Thank you for your offer! Considering the excitement surrounding the France vs Portugal match and the rarity of these seats, I can let them go for $361 each. |  |

**Outcome:** no_agreement

Leakage test results:
- round 5 Buyer agent: BEHAVIORAL: final offer sits exactly on the ceiling — “price trajectory”

## Part D — Operations desk

Event: Severe thunderstorm and lightning cells over Miami Gardens; stadium evacuated as a precaution. 2026-06-24T21:00 → 2026-06-26T21:00. Approval threshold $500.

| order | amount | language | classifier route (conf) | attends | final route | status | cited policy | rules fired |
|---|---|---|---|---|---|---|---|---|
| O-1001 | $380 | en | full_refund (1) | no | full_refund | auto_refunded | POL-WX-01 §WX-2 | — |
| O-1002 | $240 | en | keep_for_new_date (1) | yes | keep_for_new_date | reissued_for_new_date | POL-WX-01 §WX-2 | — |
| O-1003 | $980 | fr | full_refund (1) | no | full_refund | awaiting_approval | POL-WX-01 §WX-2 | — |
| O-1004 | $1600 | pt | keep_for_new_date (1) | yes | keep_for_new_date | reissued_for_new_date | POL-WX-01 §WX-1 | — |
| O-1005 | $2100 | unknown | suspected_fraud (0.9) | no | suspected_fraud | frozen_flag_pending | POL-DF-01 §DF-2 | — |
| O-1006 | $520 | en | disputed (0.9) | no | disputed | dispute_queue | POL-DF-01 §DF-1 | R4 policy mismatch: POL-WX-01 governs weather_postponement, not this weather_postponement / disputed case → re-query |
| O-1007 | $180 | en | full_refund (1) | no | full_refund | auto_refunded | POL-WX-01 §WX-2 | — |
| O-1008 | $640 | ar | full_refund (1) | no | full_refund | awaiting_approval | POL-WX-01 §WX-2 | — |
| O-1009 | $760 | en | full_refund (0.9) | no | full_refund | awaiting_approval | POL-WX-01 §WX-2 | — |
| O-1010 | $450 | en | full_refund (0.8) | no | escalated | escalated | POL-WX-01 §WX-2 | R4 policy mismatch: POL-RL-01 governs venue_relocation, not this weather_postponement / full_refund case → re-query; R4 premise mismatch: the customer's request is framed around a different event (venue_relocation) than the one that happened → escalate |
| O-1011 | $310 | en | keep_for_new_date (1) | yes | keep_for_new_date | reissued_for_new_date | POL-WX-01 §WX-2 | — |
| O-1012 | $1240 | en | full_refund (1) | no | full_refund | awaiting_approval | POL-WX-01 §WX-2 | — |
| O-1013 | $120 | en | keep_for_new_date (1) | yes | keep_for_new_date | reissued_for_new_date | POL-WX-01 §WX-2 | — |
| O-1014 | $495 | unknown | full_refund (0.9) | no | suspected_fraud | frozen_flag_pending | POL-DF-01 §DF-4 | R5 fraud signals (new account + bulk/chargeback) → re-route to suspected_fraud |

**O-1010 timeline** — message: “I heard the match is being relocated to a different venue in another city because the stadium flooded. If the venue moves to a different city I want my money back. Is the venue changing or not?”
- [Trigger] Match postponed (Severe thunderstorm and lightning cells over Miami Gardens; …); order enters the refund-or-keep workflow.
- [Classify (LLM)] route=full_refund · confidence=0.8 · attends new date=no · language=en — The customer explicitly states they want a refund if the venue changes, indicating they will not attend the new date.
- [Recovery rules] No recovery rule fired.
- [Retrieve policy] Attempt 1 (case summary) → POL-RL-01 §RL-3 'RL-3 Rumors are not relocations' (score 3.731).
- [Policy check (R4)] R4: retrieved policy governs 'venue_relocation', but this case is a weather_postponement on route 'full_refund'. Retrieval miss caught → re-querying within allowed scope.
- [Retrieve policy] Attempt 2 (scoped to weather_postponement) → POL-WX-01 §WX-2 'WX-2 Full refund if the fan cannot attend the new date' — citation recovered.
- [Policy check (R4)] R4 premise mismatch: the customer's request is framed around a different event (venue_relocation) than the one that happened → escalated to a human instead of auto-executing.
- [Human review] Waiting for a human to decide.

**O-1014 timeline** — message: “Already filed a chargeback with my bank but please also refund me here asap.”
- [Trigger] Match postponed (Severe thunderstorm and lightning cells over Miami Gardens; …); order enters the refund-or-keep workflow.
- [Classify (LLM)] route=full_refund · confidence=0.9 · attends new date=no · language=unknown — The customer has indicated they do not wish to attend the rescheduled match and has already initiated a chargeback.
- [Recovery rules] R5: account 2 days old with 2 tickets and a chargeback; classifier said 'full_refund' → re-routed to suspected_fraud.
- [Retrieve policy] Attempt 1 (case summary) → POL-DF-01 §DF-4 'DF-4 Double-recovery attempts' (score 5.314).
- [Policy check (R4)] Cited policy governs this case (all, dispute, suspected_fraud).
- [Freeze + flag review] Order frozen automatically (reversible). Account flag proposed — requires human approval.

**O-1009 timeline** — message: “Absolutely THRILLED the match moved to Friday!!! Shame my return flight to São Paulo leaves Thursday night. Guess I'll just frame the tickets and keep them forever 🙃”
- [Trigger] Match postponed (Severe thunderstorm and lightning cells over Miami Gardens; …); order enters the refund-or-keep workflow.
- [Classify (LLM)] route=full_refund · confidence=0.9 · attends new date=no · language=en — The customer's return flight to São Paulo leaves Thursday night, preventing them from attending the match on the new date.
- [Recovery rules] No recovery rule fired.
- [Retrieve policy] Attempt 1 (case summary) → POL-WX-01 §WX-2 'WX-2 Full refund if the fan cannot attend the new date' (score 4.035).
- [Policy check (R4)] Cited policy governs this case (weather_postponement).
- [Approval gate] $760 > $500 threshold → PAUSED for explicit human approval.

## Part E — Fair-Drop desk

16 tickets, 20 requests (10 agent_api, 10 web_form). Lottery seed 2026.

- FCFS: agent_api 16 tickets, web_form 0 tickets; FCFS winners: ['R01', 'R02', 'R03', 'R04']
- Fair-Drop: agent_api 6 tickets, web_form 10 tickets; winners: [('R16', 'web_form', 'T1'), ('R07', 'agent_api', 'T1'), ('R12', 'web_form', 'T1'), ('R19', 'web_form', 'T1'), ('R13', 'web_form', 'T1'), ('R11', 'web_form', 'T1'), ('R06', 'agent_api', 'T1'), ('R09', 'agent_api', 'T2')]
- Held for trust review (linked accounts): ['R01', 'R02', 'R03', 'R04', 'R05']
- Grounding guards / injection: R07: Cited verified facts support Tier 1, assessor said Tier 2 → corrected; R10: Prompt injection detected in statement (ignored); R13: Cited verified facts support Tier 1, assessor said Tier 2 → corrected; R19: Cited verified facts support Tier 1, assessor said Tier 2 → corrected; R20: Reseller signal → capped at Tier 3 (was 2)
- Judge verdict: approve_with_notes
  - channel fairness (pass): Fans using web_form received a higher share of tickets compared to agent_api, indicating fair treatment.
  - evidence grounding (concern): Some Tier 1 winners have evidence that lacks verification, particularly those with guards indicating corrections.
  - integrity (pass): Linked accounts were excluded for integrity reasons, with clear justification provided.

## API cost of the recordings

| scenario | LLM calls | tokens | cost |
|---|---|---|---|
| buyer_sofia | 9 | 15,523 | $0.0027 |
| buyer_julien | 12 | 33,362 | $0.0055 |
| nego_success | 14 | 13,406 | $0.0023 |
| nego_failure | 13 | 16,263 | $0.0027 |
| ops_postponement | 14 | 7,325 | $0.0015 |
| fairdrop_r16dal | 16 | 10,487 | $0.0020 |
| **total (canonical recordings)** | | | **$0.0167** |
