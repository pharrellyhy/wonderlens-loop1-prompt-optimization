# Run Instructions — Loop 1 Prompt Optimization

## Setup (one-time)

1. Read `program.md` fully
2. Read the activity designs in `activity_designs/` (copy from Loop 0 output)
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
6. Run baseline against ALL 6 scenarios:
   ```bash
   uv run simulate.py --scenario scenarios/polka_dot_patrol.yaml --output transcripts/baseline_polka.json
   uv run evaluate.py --transcript transcripts/baseline_polka.json --scenario scenarios/polka_dot_patrol.yaml

   uv run simulate.py --scenario scenarios/fluffy_expedition_dandelion.yaml --output transcripts/baseline_fluffy.json
   uv run evaluate.py --transcript transcripts/baseline_fluffy.json --scenario scenarios/fluffy_expedition_dandelion.yaml

   uv run simulate.py --scenario scenarios/mood_changer_dog.yaml --output transcripts/baseline_mood.json
   uv run evaluate.py --transcript transcripts/baseline_mood.json --scenario scenarios/mood_changer_dog.yaml

   uv run simulate.py --scenario scenarios/dream_whisperer_cat.yaml --output transcripts/baseline_dream.json
   uv run evaluate.py --transcript transcripts/baseline_dream.json --scenario scenarios/dream_whisperer_cat.yaml

   uv run simulate.py --scenario scenarios/time_machine_dinosaur.yaml --output transcripts/baseline_dino.json
   uv run evaluate.py --transcript transcripts/baseline_dino.json --scenario scenarios/time_machine_dinosaur.yaml

   uv run simulate.py --scenario scenarios/mood_changer_dog_silent_exit.yaml --output transcripts/baseline_silent.json
   uv run evaluate.py --transcript transcripts/baseline_silent.json --scenario scenarios/mood_changer_dog_silent_exit.yaml
   ```
   Record average DQS across all 6 as the baseline.
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
Run against ALL 6 scenarios and compute average DQS:

```bash
uv run simulate.py --scenario scenarios/polka_dot_patrol.yaml --output transcripts/latest_polka.json
uv run evaluate.py --transcript transcripts/latest_polka.json --scenario scenarios/polka_dot_patrol.yaml

uv run simulate.py --scenario scenarios/fluffy_expedition_dandelion.yaml --output transcripts/latest_fluffy.json
uv run evaluate.py --transcript transcripts/latest_fluffy.json --scenario scenarios/fluffy_expedition_dandelion.yaml

uv run simulate.py --scenario scenarios/mood_changer_dog.yaml --output transcripts/latest_mood.json
uv run evaluate.py --transcript transcripts/latest_mood.json --scenario scenarios/mood_changer_dog.yaml

uv run simulate.py --scenario scenarios/dream_whisperer_cat.yaml --output transcripts/latest_dream.json
uv run evaluate.py --transcript transcripts/latest_dream.json --scenario scenarios/dream_whisperer_cat.yaml

uv run simulate.py --scenario scenarios/time_machine_dinosaur.yaml --output transcripts/latest_dino.json
uv run evaluate.py --transcript transcripts/latest_dino.json --scenario scenarios/time_machine_dinosaur.yaml

uv run simulate.py --scenario scenarios/mood_changer_dog_silent_exit.yaml --output transcripts/latest_silent.json
uv run evaluate.py --transcript transcripts/latest_silent.json --scenario scenarios/mood_changer_dog_silent_exit.yaml
```

**Composite score = average DQS across all 6 scenarios.** This prevents overfitting to one conversation path.

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
[exp_id]\t[timestamp]\t[hypothesis]\t[change]\t[file]\t[dqs_polka]\t[dqs_fluffy]\t[dqs_mood]\t[dqs_dream]\t[dqs_dino]\t[avg_dqs_before]\t[avg_dqs_after]\t[kept:yes/no]
```

### Step 6: Report (every 5 experiments)
Print a progress summary with per-scenario breakdown. Then continue.

### Step 7: Next
Go to Step 1. Stop after 50 experiments or when avg DQS > 0.85.

## The 6 Scenarios

| Scenario | Category | Tier | Entity | What It Tests |
|---|---|---|---|---|
| `polka_dot_patrol.yaml` | Cat 5 (Collection) | T1 | Ladybug | Outdoor collection — visual feature = spots |
| `fluffy_expedition_dandelion.yaml` | Cat 5 (Collection) | T1 | Dandelion | Outdoor collection — visual feature = texture |
| `mood_changer_dog.yaml` | Cat 1 (Verbal) | T0 | Stuffed dog | In-device verbal — emotional scenarios (happy path) |
| `dream_whisperer_cat.yaml` | Cat 1 (Verbal) | T0 | Stuffed cat | In-device verbal — imagination/dreams |
| `time_machine_dinosaur.yaml` | Cat 1 (Verbal) | T0 | Toy dinosaur | In-device verbal — time travel description |
| `mood_changer_dog_silent_exit.yaml` | Cat 1 (Verbal) | T0 | Stuffed dog | **Stress test** — child goes silent 2x → graceful exit |

This mix ensures the prompt generalizes across:
- Activity categories (verbal × 4 vs collection × 2)
- Age tiers (T0 × 4 vs T1 × 2)
- Child engagement levels (cooperative × 5 vs disengaged × 1)
- Metaphor types (emotions, dreams, time travel, spots, texture)

## Important
- ONE change per experiment
- ALWAYS test ALL 6 scenarios after every change (not just one)
- ALWAYS revert on failure
- ALWAYS commit on success
- The average score is truth, not any single scenario
