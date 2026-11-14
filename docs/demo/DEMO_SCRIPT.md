# 3-minute demo script

**Setup (before you present):**
- Run `make all` (about 90 s), then `make dashboard`. Use the full-size data: on the small
  dataset, experiments are underpowered.
- Keep the README "Key results" open in a second tab as a fallback.
- No Wi-Fi or LLM key needed: the AI analyst runs offline.

| Time | Say | Click |
|---|---|---|
| **0:00** | "Product teams ship features based on A/B readouts they can't fully trust: broken assignment, peeking, a guardrail no one checked. PulseIQ is a full analytics and experimentation platform that I **proved correct** against a simulation with planted ground truth." | Home page already open |
| **0:20** | "Executive view: daily actives, MAU, stickiness, conversions and revenue, each with the change vs the previous period. Every number comes from a dbt warehouse with 70 data tests." | Point at the KPI cards, then the DAU chart |
| **0:40** | "The funnel tells us where we lose people. The biggest drop is onboarded → trial, and it's computed automatically, not eyeballed." | **Funnel** → the yellow "Biggest drop" callout → the segment split by channel |
| **1:00** | "Three experiments. First, `streak_reminder`. The engine refuses to give a readout. There's a **sample ratio mismatch**, and it localises it to **Android**. That was a planted logging bug." | **Experiments** → select streak_reminder → INVESTIGATE badge → treatment-share chart |
| **1:20** | "`paywall_redesign`: **SHIP**. CUPED uses each user's sessions before the test to remove noise. It narrows the confidence interval by about a third, which means shorter tests." | Select paywall_redesign → the blue CUPED info box → forest plot |
| **1:35** | "`onboarding_flow_v2` is the interesting one. Onboarding is clearly up, but the paid-conversion guardrail **isn't yet proven safe**. So the answer is KEEP RUNNING, with an estimate of how many days are left." | Select onboarding_flow_v2 → the reasons list |
| **1:50** | "Why not just check p-values every day? In 2,000 simulated A/A tests, peeking gives a false positive almost 3 times in 10. The sequential test stays under 5 %." | Scroll to "Why peeking is dangerous" |
| **2:10** | "Retention model. v1 claimed 85 % accuracy by predicting that nobody stays. This one is leakage-tested and triples PR-AUC. Here's the threshold trade-off and the at-risk users a campaign should contact." | **Retention Model** → metrics table → move the threshold slider → at-risk table / download |
| **2:30** | "And an AI analyst. Plain English in, guarded SQL out." Ask one question, then the malicious one: "it refuses to delete data, and every query is parsed, allow-listed and run read-only." | **AI Analyst** → "Which acquisition channel has the best D7 retention?" → open "SQL used" → click "Delete the users table" |
| **2:50** | "The difference from a typical dashboard: I planted the truth and **proved** the engine recovers it. All 12 planted effects fall inside the confidence intervals, and the bug was caught. Everything rebuilds from one seed with one command." | Back to README "Key results" |

## 60-second version
1. **Problem (10 s):** teams ship on readouts they can't trust.
2. **Experiments page (25 s):**
   - `streak_reminder` → SRM caught and localised to Android → INVESTIGATE;
   - `paywall_redesign` → CUPED narrows the CI → SHIP.
3. **Retention model (10 s):** the PR-AUC table, compared with v1's useless 85 % accuracy.
4. **AI analyst (10 s):** one question, then the blocked "delete" query.
5. **Close (5 s):** "Proved correct against planted ground truth; one command rebuilds everything."

## Fallback plan
- **No Wi-Fi / no LLM key:** the analyst is already offline (look for the banner). Nothing else
  needs the network.
- **Dashboard won't start:** show `docs/images/*.png` and the README key results. Then run
  `pulseiq analyze paywall_redesign` and `pulseiq ask "..."` live in the terminal.
- **Laptop too slow for full data:** run `make all-small`. Say that small data is underpowered,
  which is why the hosted demo shows KEEP RUNNING, and show the full-size results in the README.
