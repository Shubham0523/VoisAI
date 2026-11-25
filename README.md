# VoisAI

An AI friend you call every day. It feels like a chat with a friend, and underneath it quietly
works out your English level, remembers your life, and steers each conversation toward what
you need to practise next. It can also show, with evidence, whether you're improving.

**Live demo:** https://voisai-eight.vercel.app (allow the microphone, Chrome works best)
· growth page: [/progress](https://voisai-eight.vercel.app/progress)
· simulation results: [/eval](https://voisai-eight.vercel.app/eval)

Everything runs on free tiers: Vercel, Render, LiveKit Cloud, Neon, Groq, Google AI Studio and
Deepgram's free credit. Embeddings run locally.

## The idea: two systems pretending to be one

| | **Friend** (real-time) | **Tutor** (background) |
|---|---|---|
| Job | Be fast, warm, never teach | Measure, model, plan |
| Latency budget | ~1 s per reply | seconds, off the hot path |
| Model | Groq gpt-oss-120b | Gemini 3.5 Flash-Lite (structured output) |
| Talks to user? | Yes | Never. It reaches the Friend only through hidden `[tutor]` notes |

```
 Browser (Next.js) ──WebRTC──► LiveKit ──► Agent worker (Python, LiveKit Agents)
                                            │  Deepgram STT (verbatim: fillers kept, word timings)
                                            │  → Friend LLM (+ one hidden tutor note) → Deepgram TTS
                                            │
                                            └─► Tutor, per user turn, async
                                                  Analyst   LLM tags evidence per skill, rules normalise it
                                                  Learner   Beta mastery per skill · vocab uptake · fluency
                                                  Memory    facts + follow-ups (pgvector, local embeddings)
                                                  Steer     next turn's hidden note
                                                at call end: metrics, level, recap card, summary
                                                before next call: Planner picks targets, words, opener
 FastAPI ── tokens · growth data · eval results ◄── Postgres + pgvector
```

### What happens on one turn

1. The learner says *"Yesterday I go to office and manager give me new project."*
2. `Steer` adds one hidden note for the Friend's next reply. Notes are conversational moves only,
   e.g. *"Conversation idea: ask what they did last weekend"* or *"use the phrase 'hectic'"*.
3. The Friend replies in ~1 s, using the correct form naturally where it can: *"Oh nice, your
   manager gave you a new project?"*
4. In the background, the Analyst returns evidence: `past_simple ✗ "I go" → "I went" (0.95)`,
   `articles ✗ "to office" → "to the office"`, plus memories such as *"Has an interview Friday"*
   (a follow-up, due on that date).
5. Mastery updates; repeated in-session errors make that skill a live target, and the next
   note asks the Friend to model the correct phrase in its own sentence.
6. When the call ends, the session's metrics, CEFR estimate and an optional "by the way" card
   are computed from stored evidence. Before the next call, the Planner opens with *"How did
   the interview go?"* (real past-tense practice that just feels like a caring friend).

## How we know it works: simulated learners

You can't show weeks of learning in a short take-home build, so `backend/sim/` runs **simulated learners
through the real pipeline** (the same `FriendAgent`, Tutor and DB code as a voice call, in text
mode):

- An LLM plays the learner (persona, life, style) and writes **correct** English.
- A rule-based **error injector** then plants that persona's weaknesses at known rates (e.g.
  Rahul, Hindi L1: drops 60% of articles, says "I am knowing" 70% of the time). LLMs can't hold
  an error rate; rules can, and they log exact ground truth.
- Learning is simulated and stated openly: a skill the Planner targeted drops its error rate
  25% per session, others 3%; a word the Friend introduced has a chance of being reused later.

What the simulation then measures is **our system**, against ground truth:

| Question | Metric |
|---|---|
| Does the Analyst find the planted errors? | precision / recall per skill |
| Does the Planner target the real weaknesses? | share of sessions targeting a planted skill |
| Does the growth view track the truth? | true error rate vs measured (1 − mastery) per session |
| Does the Friend stay a friend? | teacher-leak rate (`tutor/guard.py`), recast rate |
| Does planning matter? | same learner, same seed, **random-target control** |

Results are on the `/eval` page; raw output is in `backend/sim/results/*.json`.

## Results

Cloud run: 2 simulated learners × 5 chats × 5 turns, Friend on Groq `gpt-oss-120b`, Analyst on
Gemini 3.5 Flash-Lite, learners on Groq `gpt-oss-20b`.

| | Rahul (Hindi L1) | Priya (Tamil L1) |
|---|---|---|
| Analyst precision on errors | **0.90** | **0.91** |
| Analyst recall on errors | 0.48 | 0.53 |
| Chats whose plan targeted a planted weakness | **80%** | **80%** |
| Teacher-mode leaks in Friend replies | **0%** | **0%** |
| Friend modelled the correct form within 2 replies of an error | 17% | 23% |
| True planted error rate, chat 1 → chat 5 | 57.5% → 37.8% | 56.0% → 45.8% |

**Planner vs random targets (control).** Same learner and seed, but each chat targets random
skills. After 3 chats Rahul's planted error rate was **44.4% with the planner vs 48.8% with random
targets**, and the planner aimed at a real weakness in 80% of chats vs 50%. Gemini's free daily
quota cut the control short (Rahul 4 chats, Priya none), so treat this as an early signal, not
proof. `/eval` compares the two runs at equal chat counts.

How to read it: precision is the number that protects trust (a wrong "you made a mistake" is the
worst failure), so the Analyst is tuned to be sure before it flags anything, and recall is where
the next gains are. The learning itself is simulated (see above); what the run measures is
whether our system notices, targets and tracks the planted weaknesses.

### Known issues

- **Recall is about half.** The Analyst misses roughly one planted error in two. Next step:
  few-shot examples per skill and batching 3–4 turns so it sees more context.
- **Too few recasts.** The Friend rarely models the correct form right after an error. The 0.8
  confidence gate on recasts is likely too strict; 0.7 is the next experiment.
- **The Planner can fixate.** After chat 2 it steered Priya toward `stative_continuous` every
  time. Her native language defaults to Hindi, so the L1 error priors are wrong for a Tamil
  speaker. L1 should be asked during onboarding, and a skill targeted twice without new evidence
  should rest.
- **Mastery leans pessimistic.** Correct uses are logged less reliably than errors. Counting
  correct uses deterministically from the obligatory contexts the rules already detect would fix it.
- **Free-tier ceilings.** Gemini's daily quota can leave turns unanalysed under load (the
  simulator detects this and stops a learner rather than report skewed scores), and Groq's
  8k tokens/minute limits concurrent callers. Fine for a demo, not for real traffic.
- **Fluency on real speech is unverified.** Fluency metrics come from STT word timings and are
  unit-tested, but the simulator runs in text, so they haven't been validated on audio.

## Design decisions

- **Pipeline, not speech-to-speech.** Separate STT → LLM → TTS costs some latency but gives word
  timings and confidences for fluency, and a place to inject the Tutor's note on every turn.
- **Verbatim STT.** Most STT quietly fixes grammar ("he go" → "he goes") and drops "umm". Deepgram
  runs with `filler_words=True` and `smart_format=False` so the Analyst sees what was said.
- **Patient turn-taking.** Endpointing waits 0.8–4 s, not native-speaker defaults. Learners pause
  to find words, and getting cut off feels like being judged.
- **Hidden notes never name grammar.** First prototype: telling the Friend "practise past_simple"
  made it start teaching (*"You said 'I go', but we usually say..."*). Notes now carry only
  conversational moves, and a guard measures leaks in every eval run.
- **The LLM detects, rules normalise.** Small models misfile a missing article as a tense error,
  count one error twice, or return stylistic rewrites. A word-level diff of span vs correction
  relabels article/preposition-only changes, drops rewrites and notes, and dedupes.
- **Errors need high confidence (0.8), correct uses less (0.5).** A false "you got this wrong" kills
  trust; a missed correct use just slows the estimate down. Correct uses are logged too,
  otherwise mastery could only ever fall.
- **Beta mastery instead of full knowledge tracing.** Interpretable counts, a confidence interval
  for free (the Planner can tell weak from unknown, the UI shows the likely range), and decay so
  old evidence fades. BKT needs fitted per-skill parameters we don't have data for yet.
- **Beliefs are derived, never edited.** Mastery is a function of stored observations; the
  dashboard replays history from them, and a test asserts the replay equals the stored belief.
- **Recap is deterministic.** The "by the way" card is picked from stored high-confidence
  evidence, so it can never invent a mistake the learner didn't make.
- **Growth is opt-in.** The call screen shows no scores; the growth page is a separate place the
  learner chooses to visit. Measurement is invisible, and progress is there when you want it.
- **Vocabulary uptake is strict.** A word counts as *used* only if the Friend introduced it
  earlier and didn't say it in the immediately preceding reply (echoing isn't acquiring).
- **Free tier by design.** Every LLM role is OpenAI-compatible and set per role in env; the
  Friend and Analyst use different providers so the Analyst can never queue in front of a
  reply (found the hard way when both shared one local GPU). Embeddings run locally.
- **DB writes never block or crash a call.** Persistence is best-effort and off the audio path.

## Taking it to production

Known gaps in the prototype, and what I'd do:

- **Identity.** The browser keeps a random `user_id` in localStorage and the API trusts it. Add
  real auth (phone OTP fits the market) and sign the user id into the LiveKit token.
- **Analyst quality is the product.** Ship it on the eval harness, not on vibes: run the
  simulated-learner suite in CI on every prompt or model change, gate on precision ≥ 0.9 for
  errors (false corrections destroy trust) and track recall. Add a small human-labelled set of
  real (consented) learner turns, since simulated errors are cleaner than real ones.
- **Cost per daily user.** One 10-minute call is roughly 40 turns: 40 Friend calls (small, fast
  model), 40 Analyst calls (batch them 3–4 turns at a time once latency allows), STT/TTS minutes.
  Analyst batching and prompt caching are the main levers; speech is the main cost.
- **Latency.** Measure end-of-speech → first audio per turn (LiveKit metrics are already
  emitted). Preemptive generation and a fast TTS voice are the next wins.
- **Migrations and data.** Alembic instead of `create_all`; audio retention opt-in only;
  transcripts encrypted at rest; per-user export and delete.
- **Safety for a companion product.** Age gate (minors get a different persona and no romance or
  late-night nudges); distress detection with helpline hand-off (the persona already does the
  soft version); no engineered dependency: no guilt-trip notifications, session caps, and the
  Friend encourages real-world speaking (a practice goal is talking to *people* more, not to Maya).
- **Ops.** The Analyst's latency is stored per turn (`analysis_ms`); alert on it, on Analyst JSON
  failures, and on the teacher-leak rate sampled from live calls.
- **Next product bets.** Pronunciation via phoneme-level scoring of low-confidence words; Hinglish
  code-switch handling ("you mean *reluctant*?"); L1-specific priors on the Planner; a weekly
  "you vs a month ago" voice clip.

## Layout

```
backend/voisai/
  agent/    worker.py (voice), textchat.py (text, same code), lifecycle.py, friend.py, persona.py
  tutor/    analyst.py, service.py, planner.py (plan + Steer), learner_model.py, metrics.py,
            fluency.py, session_end.py, skills.py (40 skills), wordbank.py, guard.py
  memory/   store.py (pgvector recall, follow-ups)
  api/      main.py (tokens), progress.py (growth + eval read models)
  clock.py  single source of "now" (the simulator advances it a day per session)
backend/sim/  personas.py, injector.py, run.py
frontend/     /  call screen · /progress growth page · /eval simulation results
```

## Run it

Cloud (free tiers: LiveKit Cloud, Deepgram credit, Groq, Google AI Studio). Put keys in `.env`
(see `.env.example`), then:

```bash
make setup   # uv sync, pnpm install, download VAD / turn-detector models
make db      # Postgres + pgvector in Docker, create schema
make api     # terminal 1: http://localhost:8000
make agent   # terminal 2: voice worker
make web     # terminal 3: http://localhost:3000
make sim     # simulated learners + control, then open /eval
```

Fully offline, no keys (text only, needs [Ollama](https://ollama.com) with `qwen3.5:9b`):

```bash
make db
make chat-local   # talk to Maya in the terminal through the full Tutor pipeline
make sim-local    # ~1 h on a laptop GPU
```

Tests: `make test` (unit tests always; DB integration test when Postgres is up).

## Deploy (free tiers)

One repo, three hosts, each pointed at its own folder. A push redeploys only what changed.

| Piece | Host | Config |
|---|---|---|
| Frontend (`frontend/`) | Vercel, **Root Directory = `frontend`** | `frontend/vercel.json`; env `NEXT_PUBLIC_API_URL` = the Render URL |
| API (`backend/`, `SERVICE=api`) | Render free web service | `render.yaml` Blueprint (Docker, Singapore, health check, `backend/**` build filter) |
| Voice agent (`backend/`, default role) | LiveKit Cloud agent hosting | same `backend/Dockerfile`; `lk agent create` from `backend/` |
| Postgres + pgvector | Neon (recommended) or Supabase | paste its URL as `DATABASE_URL`; `postgres://…?sslmode=require` is converted automatically |

Live deployment: Vercel (frontend), Render Singapore (API), LiveKit Cloud us-east (agent, next to
the US-hosted model providers; learner audio still enters LiveKit at the nearest edge), Neon (database).

Why the agent isn't on Render: the worker holds a live WebSocket to LiveKit and runs VAD, turn detection
and embeddings on the audio. It idles at ~1.5 GB RAM; Render's free instance is 512 MB / 0.1 CPU and
sleeps after 15 idle minutes. The API idles at ~115 MB and is fine there. To stop it sleeping, the
always-on agent pings `KEEPALIVE_URL` (the API's `/api/health`) every 10 minutes; the health check
doesn't touch the database, so Neon still scales to zero. The frontend also pings `/api/health`
on page load, in case the API is waking up.

Environment variables:

- **Render (API):** `DATABASE_URL`, `LIVEKIT_URL`, `LIVEKIT_API_KEY`, `LIVEKIT_API_SECRET`,
  `API_CORS_ORIGINS` (JSON list, e.g. `["http://localhost:3000"]`), `API_CORS_ORIGIN_REGEX`
  (e.g. `https://.*\.vercel\.app`).
- **LiveKit Cloud (agent):** `DEEPGRAM_API_KEY`, `FRIEND_API_KEY`, `ANALYST_API_KEY`, `DATABASE_URL`,
  `KEEPALIVE_URL`, passed as a secrets file: `lk agent create --region us-east --secrets-file <file>`
  from `backend/`. LiveKit injects its own URL and keys. Later code changes: `lk agent deploy`.
- **Vercel:** `NEXT_PUBLIC_API_URL`.

Direct or pooled database URLs both work: for pooler hosts (Neon `-pooler`, Supabase `:6543`) the
engine turns off asyncpg's statement caches, which transaction pooling would break. Check the image
locally with
`docker build -t voisai-backend backend && docker run -e SERVICE=api -e PORT=8000 -p 8000:8000 --env-file .env voisai-backend`.
