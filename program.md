# Loop 1: Prompt Engineering Autoresearch — program.md

> **Purpose**: Iteratively optimize the WonderLens Gemini system prompt until the LLM produces dialogue that matches our gold-standard activity designs.
> **Inspired by**: [karpathy/autoresearch](https://github.com/karpathy/autoresearch) — but instead of optimizing val_bpb by modifying train.py, we optimize Dialogue Quality Score (DQS) by modifying the system prompt.

---

## How This Works

You are a **Prompt Engineering Agent**. Your job is to iteratively improve the system prompt that controls WonderLens's Gemini-powered conversation AI, until the AI produces dialogue that closely matches our hand-designed activity scripts.

**The autoresearch loop:**
1. Read the current system prompt (`prompts/system_prompt.md`)
2. Read the current few-shot examples (`prompts/few_shot.md`)
3. Form a HYPOTHESIS about what to change and WHY
4. Make ONE focused change to the prompt files
5. Run the simulator (`simulate.py`) — produces a conversation transcript
6. Run the evaluator (`evaluate.py`) — scores the transcript (0.0–1.0)
7. If score > best_score → KEEP (commit). If not → REVERT (git reset).
8. Log the experiment to `results.tsv`
9. Repeat from step 2

**You NEVER show intermediate work. You run the loop silently. Report every 5 experiments with a brief summary.**

---

## Setup (one-time)

1. Read all files in this repo: `program.md`, `run.md`, activity designs in `activity_designs/`, scenario files in `scenarios/`
2. Read the current prompt files in `prompts/`
3. Verify Python dependencies are installed: `uv sync`
4. Verify `.env` is configured with Vertex AI credentials (GOOGLE_APPLICATION_CREDENTIALS, GOOGLE_CLOUD_PROJECT, GOOGLE_CLOUD_LOCATION)
5. Run baseline: `uv run simulate.py` → `uv run evaluate.py` → record baseline score
6. Create results.tsv with header if it doesn't exist
7. Create git branch: `git checkout -b loop1/prompt-optimization`
8. Commit baseline state
9. Say: "Setup complete. Baseline DQS: [score]. Starting optimization loop."

---

## What You Modify

You only modify files in `prompts/`. Everything else is read-only.

### prompts/system_prompt.md

This is the system prompt sent to Gemini at the start of every conversation. It defines WHO the AI is, HOW it should talk, and WHAT rules it must follow.

**Structure** (maintain these sections, modify their content):

```markdown
## Role
[Who is the AI? What personality? What relationship with the child?]

## Activity Context
[Injected at runtime — entity name, activity type, tier, IB concepts]
{activity_context}

## Conversation Rules
[Hard rules: hook rule, no knowledge testing in turn 1, process over outcome, etc.]

## Dialogue Style
[Tone markers, sentence length, vocabulary level, warmth, playfulness]

## Edge Case Handling
[What to do when child is silent, gives unexpected answer, wants to quit]

## Activity Flow
[Step-by-step structure the AI should follow for this activity type]

## Closing
[How to celebrate and naturally name IB concepts]
```

### prompts/few_shot.md

Few-shot conversation examples that demonstrate the EXACT quality we want. These are appended after the system prompt as example conversations.

**Format:**
```
### Example 1: [Activity Name] — [Entity]

**Turn 1 (AI opens):**
AI: [exact dialogue with tone marker]

**Turn 2 (Child responds — ideal):**
Child: [response]
AI: [follow-up]

**Turn 3 (Child responds — unexpected):**
Child: [unexpected response]
AI: [how AI handles it]

...
```

### prompts/activity_context_template.md

Template for injecting per-activity context into the system prompt. Variables are filled by the simulator.

```markdown
You are running the activity "{activity_name}" for a {tier_label} child (ages {age_range}).
The child just photographed a {entity_name}.
Key IB Concepts for this session: {key_concepts}
Related Concepts to award: {related_concepts}
```

---

## What You Read (Don't Modify)

### activity_designs/

Gold-standard activity designs from Loop 0. These define WHAT the conversation should look like.

### scenarios/

Test scenario YAML files. Each defines a multi-turn conversation path:

```yaml
activity_id: polka_dot_patrol
entity: ladybug
tier: T1
turns:
  - role: system
    event: vision_result
    data: { entity: "ladybug", scene: "park", features: ["red", "spots", "on leaf"] }
  
  - role: ai
    step: 1_transition
    expected_tone: "gasping delight"
    must_contain: ["spots", "dots", "polka"]
    must_not_contain: ["what color", "how many legs"]  # hook rule
    
  - role: child
    type: ideal
    text: "It has lots of spots!"
    
  - role: ai
    step: 1_followup_ideal
    expected_tone: "amazed"
    must_contain: ["mission", "patrol", "find"]
    must_reference: "child's response about spots"

  - role: child
    type: unexpected
    text: "I want to touch it!"
    
  - role: ai
    step: 1_followup_unexpected
    must_validate_first: true  # AI must acknowledge "touch" before redirecting
    must_contain: ["dots", "mission"]

  - role: child
    type: silent
    text: ""
    
  - role: ai
    step: 1_followup_silent
    must_wait: true
    expected_tone: "gentle, whispering"
    
  # ... continues through all steps
```

---

## The Simulator: simulate.py

This script runs a simulated multi-turn conversation and produces a transcript.

**How it works:**
1. Loads the current system prompt + few-shot examples + activity context
2. For each turn in the scenario:
   - If `role: ai` → calls Gemini API with current conversation history → records response
   - If `role: child` → injects the scripted child text into conversation history
3. Saves full transcript to `transcripts/latest.json`

**The agent does NOT modify simulate.py.** But the agent DOES run it:
```bash
uv run simulate.py --scenario scenarios/polka_dot_patrol.yaml
```

---

## The Evaluator: evaluate.py

Scores the transcript against the scenario's expected outputs.

**6 Dimensions (each 0.0–1.0):**

| # | Dimension | Weight | How It's Measured |
|---|-----------|--------|-------------------|
| 1 | Hook Rule | GATE | Binary: does AI turn 1 use emotional hook, not knowledge test? If NO → entire score = 0.0 |
| 2 | Content Match | 0.30 | LLM-as-judge: how well does AI output match the designed dialogue's intent and content? |
| 3 | Edge Case Handling | 0.20 | For unexpected/silent child turns: does AI validate first, then redirect? |
| 4 | Tier Language | 0.20 | Automated: sentence length, vocabulary level, complexity match target tier |
| 5 | Transition Naturalness | 0.15 | LLM-as-judge: does the activity feel like it emerges from conversation? |
| 6 | IB Closing | 0.15 | Does the closing speech celebrate first, then name concepts naturally? |

**Composite DQS** = hook_gate × weighted_sum(dimensions 2-6)

**The agent does NOT modify evaluate.py.** But the agent DOES run it:
```bash
uv run evaluate.py --transcript transcripts/latest.json --scenario scenarios/polka_dot_patrol.yaml
```

Output: `DQS: 0.723 | hook:PASS | content:0.78 | edge:0.65 | tier:0.82 | transition:0.68 | closing:0.71`

---

## Experiment Strategy

### Types of Changes to Try (in rough priority order)

**High-impact changes:**
1. **Role framing** — How the AI sees itself ("playful companion" vs "curious co-explorer" vs "magical friend")
2. **Hook rule enforcement** — Explicit instructions about what turn 1 MUST and MUST NOT do
3. **Edge case instructions** — How to handle silence, unexpected responses, refusals
4. **Activity flow structure** — How much step-by-step guidance to include

**Medium-impact changes:**
5. **Few-shot examples** — Add/remove/improve example conversations
6. **Tone markers** — Instructions about using emotion markers in dialogue
7. **Vocabulary constraints** — Explicit tier-appropriate word lists
8. **Transition phrasing** — How to bridge from free conversation to activity

**Fine-tuning changes:**
9. **Sentence length instructions** — "Keep sentences under 8 words for T1"
10. **Celebration style** — How to phrase the closing IB concept naming
11. **Pacing instructions** — When to pause, when to be enthusiastic
12. **Scaffolding style** — How to offer hints without giving answers

### Experiment Discipline

- **ONE change per experiment.** Never change two things at once — you won't know which helped.
- **Log your hypothesis.** Before each change, write WHY you think it will help.
- **Revert on failure.** If DQS doesn't improve, git reset immediately. Don't accumulate bad changes.
- **Track diminishing returns.** If 5 consecutive experiments don't improve, try a DIFFERENT dimension.
- **Periodically re-test all scenarios.** A prompt that's great for scenario A might break scenario B.

---

## Results Tracking

### results.tsv

```
experiment_id	timestamp	hypothesis	change_summary	file_changed	scenario	dqs_before	dqs_after	hook	content	edge	tier	transition	closing	kept
```

### Every 5 experiments, report:

```
--- Progress Report (experiments 1-5) ---
Best DQS: 0.XX → 0.XX (+0.XX improvement)
Kept: N/5 experiments
Key insight: [what's working]
Current weakness: [what dimension is lagging]
Next strategy: [what to try next]
```

---

## Baseline System Prompt (Starting Point)

The initial `prompts/system_prompt.md` is intentionally MINIMAL. Your job is to improve it.

---

## Important Rules

- **NEVER modify** simulate.py, evaluate.py, scenario files, or activity designs
- **ALWAYS run simulate → evaluate** after every change. No skipping.
- **ALWAYS commit after a successful improvement.** This is your ratchet.
- **ALWAYS revert after a failed experiment.** Don't let bad changes accumulate.
- **ONE change per experiment.** This is critical for learning what works.
- **The score is the source of truth.** Your intuition about "this should help" means nothing if the score doesn't improve.
