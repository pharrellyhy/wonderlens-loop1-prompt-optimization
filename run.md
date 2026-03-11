# Run Instructions — Loop 1 Prompt Optimization

## Setup (one-time)

1. Read `program.md` fully
2. Read the activity design in `activity_designs/` (copy from Loop 0 output)
3. Install dependencies:
   ```bash
   uv sync
   ```
4. Verify `.env` is configured with Vertex AI credentials:
   ```bash
   cat .env  # Should have GOOGLE_APPLICATION_CREDENTIALS, GOOGLE_CLOUD_PROJECT, GOOGLE_CLOUD_LOCATION
   ```
5. Create git branch:
   ```bash
   git checkout -b loop1/$(date +%b%d)
   ```
6. Run baseline against ALL scenarios:
   ```bash
   uv run simulate.py --scenario scenarios/polka_dot_patrol.yaml --output transcripts/baseline_polka.json
   uv run evaluate.py --transcript transcripts/baseline_polka.json --scenario scenarios/polka_dot_patrol.yaml

   uv run simulate.py --scenario scenarios/dino_time_traveler.yaml --output transcripts/baseline_dino.json
   uv run evaluate.py --transcript transcripts/baseline_dino.json --scenario scenarios/dino_time_traveler.yaml

   uv run simulate.py --scenario scenarios/polka_dot_patrol_hard.yaml --output transcripts/baseline_hard.json
   uv run evaluate.py --transcript transcripts/baseline_hard.json --scenario scenarios/polka_dot_patrol_hard.yaml
   ```
   Record average DQS across all 3 as the baseline.
7. Record baseline DQS in results.tsv
8. Commit: `git add -A && git commit -m "Baseline: avg DQS=[score]"`
9. Say: "Setup complete. Baseline avg DQS: [score]. Starting optimization."

## The Loop (repeat indefinitely)

### Step 1: Hypothesize
Look at the current scores. Identify the WEAKEST dimension across scenarios. Form a hypothesis:
"If I [specific change], the [dimension] score should improve because [reason]."

### Step 2: Edit
Make ONE focused change to a file in `prompts/`. Only change one thing at a time.

### Step 3: Test
Run against ALL 3 scenarios and compute average DQS:

```bash
uv run simulate.py --scenario scenarios/polka_dot_patrol.yaml
uv run evaluate.py --transcript transcripts/latest.json --scenario scenarios/polka_dot_patrol.yaml

uv run simulate.py --scenario scenarios/dino_time_traveler.yaml --output transcripts/latest_dino.json
uv run evaluate.py --transcript transcripts/latest_dino.json --scenario scenarios/dino_time_traveler.yaml

uv run simulate.py --scenario scenarios/polka_dot_patrol_hard.yaml --output transcripts/latest_hard.json
uv run evaluate.py --transcript transcripts/latest_hard.json --scenario scenarios/polka_dot_patrol_hard.yaml
```

**Composite score = average DQS across all 3 scenarios.** This prevents overfitting to one conversation path.

### Step 4: Decide
Compare average DQS to best_avg_score.

**If avg DQS > best_avg_score:**
```bash
git add prompts/ results.tsv
git commit -m "Exp [N]: [hypothesis] — avg DQS [before]->[after] (+[delta])"
```
Update best_avg_score.

**If avg DQS <= best_avg_score:**
```bash
git checkout -- prompts/
```
Log the failed experiment in results.tsv anyway (for learning).

### Step 5: Log
Append to results.tsv:
```
[exp_id]\t[timestamp]\t[hypothesis]\t[change]\t[file]\t[dqs_polka]\t[dqs_dino]\t[dqs_hard]\t[avg_dqs_before]\t[avg_dqs_after]\t[kept:yes/no]
```

### Step 6: Report (every 5 experiments)
Print a progress summary with per-scenario breakdown. Then continue.

### Step 7: Next
Go to Step 1. Stop after 50 experiments or when avg DQS > 0.85.

## The 3 Scenarios

| Scenario | Category | Tier | What It Tests |
|---|---|---|---|
| `polka_dot_patrol.yaml` | Cat 5 (Collection) | T1 | Happy path — ideal child, outdoor exploration |
| `dino_time_traveler.yaml` | Cat 1 (Verbal) | T0 | Different activity type, younger tier, imaginative play |
| `polka_dot_patrol_hard.yaml` | Cat 5 (Collection) | T1 | Stress test — mostly silent/unexpected child, early exit |

This mix ensures the prompt generalizes across:
- Activity categories (verbal vs collection)
- Age tiers (T0 vs T1)
- Child engagement levels (cooperative vs difficult)

## Important
- ONE change per experiment
- ALWAYS test ALL 3 scenarios after every change (not just one)
- ALWAYS revert on failure
- ALWAYS commit on success
- The average score is truth, not any single scenario
- If one scenario improves but another drops, that's a NET decision — check the average
