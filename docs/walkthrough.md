# TripSync, explained: one real trip, step by step

This guide explains how TripSync works without assuming you can code. It follows one real trip that was run on
31 October 2026, and every number below comes from that run's "Under the hood" record.

---

## 1. The short answer

TripSync is a team of **agents**. Each agent is a worker with one job. They share one notebook: the trip so far.

- The **Budget** agent sets a spending limit for travel, stay, activities and food *before* anything is searched.
- Three agents then search **at the same time**, each inside its own limit:
  - the **Transport** agent finds flights, trains and buses;
  - the **Accommodation** agent finds hotels;
  - the **Activity** agent finds places and checks the weather.
- **You** pick the places, hotel and transport.
- The **Planner** builds the days.
- The **Critic** checks the plan against rules. If something is wrong, it sends the work back to the one agent that
  can fix it, and the loop runs again.

The facts (places, prices, distances, weather) come only from **real services on the internet**. An **AI model**
helps where judgement or language matters, and the code checks every AI answer before it is used. You can watch all
of it in the **Under the hood** panel.

---

## 2. What "agent" means here

An agent in TripSync is a step in a workflow (built with a library called **LangGraph**) that:

1. reads the shared trip notebook (called the **state**);
2. does one job, often by calling a real service (a flight search, a hotel search, a map service);
3. writes its result back into the notebook, plus a short note on what it decided and why.

LangGraph decides which agent runs next. Sometimes several run in parallel. When the Critic finds a problem,
LangGraph follows an arrow *back* to an earlier agent. That loop is what makes it an agent *system* rather than a
straight script.

```
 Your message
     │
 Intake ──▶ Budget ──┬──▶ Transport ─────┐
                     ├──▶ Accommodation ─┼──▶ You choose ──▶ Planner ──▶ Critic ──▶ Final plan
                     └──▶ Activity ──────┘                                 │
                            ▲                                              │
                            └──── sent back to the agent that can fix it ──┘
                                   (at most 3 rounds, then it rebalances or asks you)
```

---

## 3. One real trip, step by step

**The request:** "4 days from Bengaluru to Goa on 21 Nov 2026 for 2 people, budget ₹40000, interested in beach and
history, keep it balanced."

### Step 1: Intake agent (reads the request)
- Pattern rules (no AI) found everything:
  - from Bengaluru, to Goa
  - leaving 21 Nov, back 24 Nov
  - 2 travellers, budget ₹40,000
- Because nothing was missing, **the AI was not called**. The AI is asked only when the rules miss something, for
  example "a long weekend in the hills with my parents, about 50k".

### Step 2: Budget agent (sets the limits)
- A typical trip like this costs about **₹39,645**.
- The stay estimate came from **23 real mid-range hotel prices in Goa**, stored in TripSync's own database from
  earlier searches (median ₹5,615 a room a night).
- Limits: transport ₹6,200, stay ₹15,300, activities ₹5,100, food ₹9,400, with ₹4,000 (10%) kept back as a buffer.

### Step 3: Three agents search at the same time

**Transport agent**
- Asked **Kiwi.com** (through its MCP flight-search service) and found 10 options, 8 of them live.
- Live IndiGo non-stop flights cost about **₹21,736** for both people, both ways. That is far over the ₹6,200 limit.
- The train (₹4,800, 13 h) and the AC sleeper bus (₹5,600, 11 h) both fit.
- It picked the **bus**: the most convenient option within the limit (fewest hours).
- Bus and train fares are typical fares, not live ones, and the app says so.

**Accommodation agent**
- Asked **LiteAPI** for real hotel rates.
- Picked **Sort By Stays, Grand Peddem, Anjuna**: mid-range, rated 8.3/10, **₹6,363** for 3 nights. It was the
  first mid-range stay within the limit.

**Activity agent**
- **OpenStreetMap was down.** It timed out after 40 seconds, and a second server also failed. The Under the hood
  panel shows both failures in red.
- So the agent used **Wikivoyage** and TripSync's bundled list instead: **19 real places** and 16 places to eat.
- Weather came from **Open-Meteo**. The trip was 3 weeks away, so it used last year's weather for the same dates.
- **The AI suggested 12 of the 19 places**, each with a reason. For example:
  - Fort Aguada: "Well-preserved fort with sea views and a lighthouse."
  - Basilica of Bom Jesus: "Iconic baroque church housing St. Francis Xavier's tomb."
- The code checked that every suggestion was a number from the real list. All 12 were real, so all 12 were kept.

### Step 4: You choose
- The plan pauses. You see every place (with the AI's reason on the suggested ones), every hotel and every way to
  travel, with road distances from your hotel.
- In this run 15 places were kept.

### Step 5: Planner agent (builds the days)
- It grouped places by area around the hotel and ordered each day to avoid going back and forth.
- Road distances and times came from **OSRM**, a free routing service, and were saved for reuse.
- Result: 4 days, 13 stops, total **₹30,073** of ₹40,000.

### Step 6: Critic agent (checks the plan)
- **Round 1 found a problem.** Transport, activities and food were each a little over their *own* limits, but the
  whole trip was about ₹10,000 *under* budget.
- So the Critic sent the work **back to the Budget agent** to re-split the money around the real plan, all in one go.
- New limits: transport ₹7,781, stay ₹7,617, activities ₹8,152, food ₹12,449.
- The three search agents and the Planner ran again with the new limits.
- **Round 2: every rule passed.**
- Then the **AI gave a second opinion.** It noticed temperatures of about 33–34 °C on days 1 and 2 and suggested water
  and shade. These were not problems that change the plan, so the code showed them as **tips**.
- If the AI had said a day was too full, the code would first have checked that the day exists and has more than
  one stop. Then it would have sent that day back once to be lightened.

### Step 7: Final step
- The AI wrote a short overview and one line per day on why its stops belong together, using the real distances.
  For example, day 2: "A cultural day of birds, art and history … museum and basilica sites that sit close together."
- This is text only. No place, price or distance can change at this step.
- "What changed and why" explains that Calangute Beach and Church of St. Cajetan were left out because they didn't
  fit in the time at your pace.

---

## 4. Where AI is used, and where it isn't

| Decision | Who decides | AI's role | How the code checks it |
|---|---|---|---|
| Reading your message | Rules first | Fills only what the rules missed | Dates, cities and numbers are validated; anything the rules found wins |
| Spending limits | Code | none | n/a |
| Choosing transport and hotel | Code (limits and convenience) | none | n/a |
| Which places to suggest | **AI** | Picks from the real list, by number, with a reason | Numbers not on the list are thrown away |
| Building the days | Code (area grouping, route order, opening hours) | none | n/a |
| Checking the plan | Code (budget, rain, opening hours, invented places) | none | n/a |
| Which problem to fix first | **AI**, when the choices lead to different agents | Picks one of the problems the rules allow | Must be one of the given numbers |
| Is a day too much? | **AI** second opinion | Flags a day, or gives tips | Must be a real day with more than one stop; at most once per plan |
| Explaining each day | **AI** | One sentence per day | Text only; nothing in the plan changes |
| Understanding a change request | Rules first | Classifies into fixed change types | Only those types can run |

**Why not let the AI do everything?** AI models can invent things that sound right: a fort that doesn't exist, a
price, a train time. So TripSync uses this rule: **AI proposes, code verifies.**
- The AI only ever chooses among real options it is shown.
- Code throws away anything else.
- If no AI model answers (no internet, rate limit, no key), the rules decide and the app still works.

All AI decisions live in one file, `backend/tripsync/agents/ai.py`.

**Which AI?** Free models, tried in order:
1. Groq (`gpt-oss-120b`)
2. Google Gemini, if Groq fails
3. A local model (Ollama), if one is running

In one earlier test run, Groq failed and Gemini answered instead. The panel showed both.

---

## 5. What happens when things fail

| Failure | What TripSync does | Seen in this run? |
|---|---|---|
| OpenStreetMap times out | Uses saved places, then Wikivoyage, then a bundled list | Yes: 40 s timeout, then Wikivoyage |
| No live flights | Says so and links to Google Flights and Kiwi.com; never invents flights | No |
| Hotel search fails | Typical prices by tier, clearly labelled "not a live quote" | No |
| Routing service down | Straight-line distance × 1.4, labelled "estimate" | No |
| An AI provider fails | Next provider; if none, the rules | Yes, in an earlier run: Groq → Gemini |
| Still over budget after 3 rounds | Asks you: raise the budget, cut a day, or accept | No |

---

## 6. How to demo it (about 3 minutes)

1. **Start the app.** In one terminal:
   ```bash
   cd backend && python3.12 -m uvicorn tripsync.api:app --reload --port 8000
   ```
   In another:
   ```bash
   npm --prefix frontend run dev
   ```
   Then open http://localhost:5173.
2. **Plan a trip** (for example Bengaluru → Goa, 4 days, 2 people, ₹40,000).
3. **While it runs**, point at **"Under the hood, live"**. Each agent card appears as it finishes, with green
   "Live", blue "Saved", amber "Estimate" or red "Failed" badges on every real service call.
4. **On the choose screen:**
   - Show a "Why the AI suggested it" line on a place card.
   - Change the hotel and show that the distances update.
5. **Click Generate.** Open **Under the hood** at the bottom of the plan and show:
   - the Critic card and the arrow "Critic sent this back to the Budget agent", with its reason;
   - an **AI** box: what the AI suggested, and "Checked: used" or "Checked: not used";
   - the summary line at the top (how many steps, real calls and AI suggestions).
6. **Ask for a change** ("cheaper hotel"). Show that only the affected agents rerun, and that "What changed and why"
   lists the differences.

---

## 7. Likely viva questions

1. **Are these real agents or just one program?**
   Each agent is a separate step in a LangGraph workflow, with its own job, tools and budget limit. They share state.
   They run in parallel where possible, and the Critic can send work back to a specific agent. The Under the hood
   panel shows each one running.

2. **Is it all AI?**
   No, and on purpose. Facts come from real services. Rules handle money, routes and checks. The AI handles judgement
   and language: suggesting places, picking which problem to fix first, a second opinion on the days, and
   explanations. Its answers are checked before use.

3. **How do you stop the AI from making things up?**
   It only chooses from numbered lists of real items, and the code discards anything else. The Critic also rejects
   any place in the plan that didn't come from a real source. Our 16-trip evaluation found 0 invented places.

4. **What is LangGraph?**
   A library for building workflows as a graph of steps. It handles running steps in parallel, loops back to earlier
   steps, pausing for the user (`interrupt`), and saving progress (a "checkpointer") so a trip can be changed later.

5. **What does the Critic check?**
   - every category within its limit, and the total within budget;
   - no outdoor stops on rainy days;
   - every place open at the planned time;
   - no day too long;
   - every place from a real source.

6. **What if the Critic can't fix it?**
   After 3 rounds: if the whole trip still fits, it rebalances the budget; otherwise it asks you to raise the budget,
   cut a day, or accept the plan.

7. **Which real services do you use, and do they cost money?**
   All free: Kiwi.com (flights, via MCP), LiteAPI and SerpApi (hotels, free tiers), OpenStreetMap (places and
   geocoding), Wikivoyage and Wikipedia, Open-Meteo (weather), OSRM (road routes), Frankfurter (currency).

8. **What is MCP?**
   Model Context Protocol, a standard way to call a tool server. Kiwi.com offers its flight search as a public MCP
   server, and TripSync calls it directly.

9. **What happens with no internet or no API keys?**
   It still plans: rule-based reading, bundled places, typical prices and estimated distances, all clearly labelled.

10. **Why have the budget step first?**
    Most planners add up the cost at the end. TripSync sets hard limits first, so every agent searches inside its
    share.

11. **Why does the user choose in the middle?**
    So the plan is built around what you want, instead of you editing the AI's guesses afterwards. LangGraph
    pauses the workflow and resumes it with your choices.

12. **Does it learn?**
    It stores what it finds in its own SQLite database: places, hotel prices, fares, routes, and what travellers
    pick or skip. Later trips get better estimates, survive outages, and rank popular places higher. In this run,
    the stay limit used 23 hotel prices saved earlier.

13. **How do you know it works?**
    - 62 automated tests that run offline, including tests that feed the AI deliberately wrong answers and check
      they are rejected;
    - an evaluation over 16 trips (all within budget, 0 invented places);
    - the live Under the hood record.

14. **What are its limits?**
    - Train and bus fares and times are typical, not live.
    - Weather more than about 2 weeks ahead is last year's.
    - The free AI and map services can be slow or rate-limited.
    - Bookings happen on the linked sites, not in TripSync.

15. **What did you do yourself?**
    Answer this honestly in your own words: the idea, the requirements, the design decisions you made, and what you
    tested.

---

## 8. Small glossary

| Term | Meaning |
|---|---|
| **API** | A way for one program to ask another for data, e.g. "hotels in Goa for these dates". |
| **State** | The shared notebook every agent reads and writes. |
| **Interrupt** | LangGraph pausing the workflow to ask you something. |
| **Checkpointer** | Saves the state after each step, so the trip can be resumed or changed. |
| **Cache / "Saved"** | An answer reused from an earlier identical request, to save time and free quota. |
| **LLM** | Large language model: the AI (Groq, Gemini). |
| **Structured output** | Asking the AI to answer in a fixed format (e.g. a list of numbers), so code can check it. |
| **OSRM** | A free service that gives road distance and driving time between points. |

## 9. Where things are in the code

| What | File |
|---|---|
| The workflow (which agent runs after which) | `backend/tripsync/graph.py` |
| Each agent | `backend/tripsync/agents/*.py` |
| Every AI decision and its checks | `backend/tripsync/agents/ai.py` |
| The Under the hood record | `backend/tripsync/trace.py` |
| The Critic's rules | `backend/tripsync/agents/critic.py` |
| The travel database | `backend/tripsync/db.py` |
| The Under the hood panel | `frontend/src/components/UnderTheHood.tsx` |
| Tests | `backend/tests/` (`test_trace.py` covers the AI checks) |
