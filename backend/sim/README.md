# Simulated learners

The eval suite. An LLM plays a learner (persona, life, speaking style) and writes correct
English; `injector.py` then plants that persona's weaknesses at known rates and logs the ground
truth. The learner talks to the real Friend and Tutor in text mode, and `run.py` scores the
system against that ground truth: Analyst precision/recall, Planner targeting, teacher leaks,
recasts, and true vs measured error rates per session.

| File | Purpose |
|---|---|
| `personas.py` | Rahul (Hindi L1), Priya (Tamil L1), Arjun (Hindi L1): level, life, error rates per skill |
| `injector.py` | Rule-based error planting with exact ground-truth logging |
| `run.py` | Runs learners through the pipeline and writes `results/<tag>.json` |
| `results/main.json` | Planner run (2 learners × 5 chats) |
| `results/control.json` | Random-target control |

```bash
uv run python -m sim.run --sessions 5 --turns 5 --tag main
uv run python -m sim.run --personas sim-rahul --sessions 5 --turns 5 --planner random --tag control
```

`--personas` takes a comma-separated list (default: all). Turns are paced by `SIM_TURN_GAP_S`
(default 9 s) to stay under Groq's free tokens-per-minute limit. A learner is stopped if its turns
go unanalysed (provider quota), so a partial result is never scored as a clean one.
