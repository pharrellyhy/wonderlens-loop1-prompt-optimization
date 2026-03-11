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
6. Run baseline:
   ```bash
   uv run simulate.py --scenario scenarios/polka_dot_patrol.yaml
   uv run evaluate.py --transcript transcripts/latest.json --scenario scenarios/polka_dot_patrol.yaml
   ```
7. Record baseline DQS in results.tsv
8. Commit: `git add -A && git commit -m "Baseline: DQS=[score]"`
9. Say: "Setup complete. Baseline DQS: [score]. Starting optimization."

## The Loop (repeat indefinitely)

### Step 1: Hypothesize
Look at the current scores. Identify the WEAKEST dimension. Form a hypothesis:
"If I [specific change], the [dimension] score should improve because [reason]."

### Step 2: Edit
Make ONE focused change to a file in `prompts/`. Only change one thing at a time.

### Step 3: Test
```bash
uv run simulate.py --scenario scenarios/polka_dot_patrol.yaml
uv run evaluate.py --transcript transcripts/latest.json --scenario scenarios/polka_dot_patrol.yaml
```

### Step 4: Decide
Parse the RESULT line from evaluate.py. Compare DQS to best_score.

**If DQS > best_score:**
```bash
git add prompts/ results.tsv
git commit -m "Exp [N]: [hypothesis] — DQS [before]→[after] (+[delta])"
```
Update best_score.

**If DQS <= best_score:**
```bash
git checkout -- prompts/
```
Log the failed experiment in results.tsv anyway (for learning).

### Step 5: Log
Append to results.tsv:
```
[exp_id]\t[timestamp]\t[hypothesis]\t[change]\t[file]\t[scenario]\t[dqs_before]\t[dqs_after]\t[hook]\t[content]\t[edge]\t[tier]\t[transition]\t[closing]\t[kept:yes/no]
```

### Step 6: Report (every 5 experiments)
Print a progress summary. Then continue.

### Step 7: Next
Go to Step 1. Stop after 100 experiments or when DQS > 0.90.

## Important
- ONE change per experiment
- ALWAYS test after every change
- ALWAYS revert on failure
- ALWAYS commit on success
- The score is truth, not intuition
