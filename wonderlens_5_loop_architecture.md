# WonderLens Demo Implementation — 5-Loop Autoresearch Architecture

> **Purpose**: Map out how to use the autoresearch pattern (agent modifies → runs → evaluates → keeps/reverts)
> across all 5 domains needed to go from activity designs to a working demo.
>
> **Prerequisite**: Completed activity designs from Loop 0 (the activity auto-design system we already built).

---

## The Big Picture

```
                    LOOP 0 (DONE)                         LOOP 1-5 (THIS DOCUMENT)
               ┌─────────────────┐
               │ Activity Design │
               │  Auto-Designer  │
               │ (program.md)    │
               └───────┬─────────┘
                       │ produces
                       ▼
              ┌─────────────────┐
              │ Completed       │
              │ Activity Designs│──────────────────────────────────┐
              │ (gold standard) │                                  │
              └───┬───┬───┬─────┘                                  │
                  │   │   │                                        │
       ┌──────────┘   │   └──────────┐                             │
       ▼              ▼              ▼                             ▼
  ┌─────────┐   ┌──────────┐   ┌──────────┐   ┌──────────┐  ┌──────────┐
  │ LOOP 1  │   │ LOOP 2   │   │ LOOP 3   │   │ LOOP 4   │  │ LOOP 5   │
  │ Prompt  │──▶│ Frontend │──▶│ Asset    │──▶│Animation │  │ Pipeline │
  │ Eng.    │   │ UI       │   │ Gen.     │   │ & Audio  │  │ Integr.  │
  └─────────┘   └──────────┘   └──────────┘   └──────────┘  └──────────┘
       │              │              │              │              │
       └──────────────┴──────────────┴──────────────┴──────────────┘
                                     │
                                     ▼
                            ┌─────────────────┐
                            │   WORKING DEMO  │
                            │  (one activity, │
                            │   end to end)   │
                            └─────────────────┘
```

### Dependency Order

```
Loop 1 (Prompt Eng.)     — can start IMMEDIATELY, no dependencies
Loop 2 (Frontend UI)     — can start IMMEDIATELY, uses placeholder assets
Loop 3 (Asset Gen.)      — can start IMMEDIATELY, independent of code
Loop 4 (Animation/Audio) — depends on Loop 3 outputs (static assets → animate)
Loop 5 (Pipeline Integr.)— depends on Loop 1 + 2 (needs prompts + UI to wire together)
```

**Parallelization**: Loops 1, 2, 3 can run simultaneously on separate machines/sessions. Loop 4 follows Loop 3. Loop 5 is the integration pass that wires everything together.

---

## Loop 1: Prompt Engineering & Context Engineering

> **Analogy to autoresearch**: Closest match. System prompt = `train.py`. Dialogue quality score = `val_bpb`.

### What It Does

Takes a completed activity design (e.g., "Polka-Dot Patrol") and iterates on the **Gemini system prompt + few-shot examples** until the LLM produces dialogue that matches the designed interaction flow in tone, structure, and educational quality.

### Files

```
loop1_prompts/
├── program.md              — Agent instructions for prompt iteration
├── activity_designs/       — Input: completed designs from Loop 0 (read-only)
│   └── ladybug_cat5.md
├── prompts/                — The file the agent modifies (= train.py)
│   ├── system_prompt.md    — Main system prompt for Gemini
│   ├── few_shot_examples.yaml — Few-shot conversation examples
│   └── activity_context.yaml  — Per-activity context template
├── simulator.py            — Runs simulated conversations (= train.py runner)
├── evaluator.py            — Scores output against gold standard (= val_bpb)
└── results.tsv             — Experiment log
```

### The Loop

```
1. Agent reads the gold-standard activity design
2. Agent modifies system_prompt.md or few_shot_examples.yaml
3. simulator.py runs a multi-turn simulated conversation:
   - Gemini (with current prompts) plays the AI role
   - A second LLM call simulates the child (ideal, unexpected, silent responses)
   - Produces a full conversation transcript
4. evaluator.py scores the transcript on 6 dimensions:
   a. Hook compliance: Does turn 1 use emotional hook? (binary)
   b. Dialogue match: How close is AI output to designed dialogue? (0-10)
   c. Edge case handling: Did AI handle unexpected/silent correctly? (0-10)
   d. Tier language: Vocabulary/sentence length appropriate? (0-10)
   e. Transition naturalness: Does activity emerge from conversation? (0-10)
   f. IB closing: Are concepts named naturally? (0-10)
   COMPOSITE SCORE = weighted average (hook is pass/fail gate)
5. If composite > best_score → commit. If not → revert.
6. Repeat.
```

### Metric: Dialogue Quality Score (DQS)

```python
def evaluate(transcript, gold_standard):
    # Binary gate — instant fail if violated
    hook_pass = check_hook_rule(transcript.turn_1)
    if not hook_pass:
        return 0.0  # Fail

    scores = {
        "dialogue_match": llm_judge_similarity(transcript, gold_standard, weight=0.3),
        "edge_cases":     llm_judge_edge_handling(transcript, weight=0.2),
        "tier_language":  vocabulary_check(transcript, tier=gold_standard.tier, weight=0.2),
        "transition":     llm_judge_naturalness(transcript, weight=0.15),
        "ib_closing":     llm_judge_closing(transcript, gold_standard.concepts, weight=0.15),
    }
    return weighted_sum(scores)
```

### What the Agent Modifies

| Component | Type of Change | Example |
|---|---|---|
| System prompt preamble | Tone/role framing | "You are a warm, playful companion" → "You are a curious co-explorer who gets excited about discoveries" |
| Activity entry instructions | How to open the activity | Adding "Always reference the child's previous answer in your first activity line" |
| Few-shot examples | Concrete demonstrations | Adding a 3-turn example showing how to handle a silent child |
| Constraint rules | Hard rules in the prompt | "NEVER ask 'what color is it' as your first question" |
| Context template | Per-activity variables | How entity name, visual features, IB concepts are injected |

### Cost & Speed

- ~$0.02 per simulated conversation (Gemini Flash in + out)
- ~$0.05 per LLM-as-judge evaluation (6 dimension scores)
- ~$0.07 per iteration total
- ~30 seconds per iteration (API calls are the bottleneck)
- **~120 iterations/hour, ~1000 overnight**
- $70 per overnight run

### What "Good" Looks Like

- Start: DQS ~0.5 (generic system prompt, LLM produces vaguely on-topic but flat dialogue)
- Target: DQS ~0.85 (dialogue closely matches designed flow, handles edge cases well, natural transitions)
- Stretch: DQS ~0.95 (indistinguishable from a human-written script in blind evaluation)

---

## Loop 2: Frontend UI Components

> **Analogy to autoresearch**: Agent modifies React components → headless browser renders → screenshot comparison evaluates.

### What It Does

For each activity step's "Screen" description in the design, generates the React/HTML component that renders it. Iterates until the rendered output matches the spec.

### Files

```
loop2_frontend/
├── program.md               — Agent instructions for UI iteration
├── activity_designs/        — Input: screen descriptions from designs (read-only)
├── src/                     — The files the agent modifies
│   ├── widgets/             — 12 widget primitives (reusable)
│   │   ├── MissionCard.jsx
│   │   ├── PhotoGrid.jsx
│   │   ├── BadgeAward.jsx
│   │   ├── ProgressTracker.jsx
│   │   ├── CelebrationOverlay.jsx
│   │   └── ...
│   ├── activities/          — Per-activity screen compositions
│   │   └── PolkaDotPatrol/
│   │       ├── Step1_Transition.jsx
│   │       ├── Step2_Mission.jsx
│   │       ├── Step3_Exploration.jsx
│   │       ├── Step4_Celebration.jsx
│   │       └── Step5_Closing.jsx
│   └── theme/               — Color palette, fonts, spacing
│       └── wonderlens.css
├── render_test.js           — Puppeteer: renders each step, takes screenshot
├── evaluate.py              — Compares screenshots against spec
└── results.tsv
```

### The Loop

```
1. Agent reads the screen description for a specific step:
   "Mission card with 'Polka-Dot Patrol' badge, 4 empty circle slots,
    first filled with ladybug photo, numbered task list with icons"
2. Agent writes/modifies the React component
3. render_test.js renders the component in a headless browser at device resolution
   (320x240 px — the WonderLens 2.0-2.4" LCD) and takes a screenshot
4. evaluate.py checks:
   a. Does it render without errors? (binary — console errors = fail)
   b. DOM structure check: expected elements present? (badge, 4 slots, task list)
   c. Readability: text contrast ratio ≥ 4.5:1 (WCAG AA, critical for kids)
   d. Layout: no overflow, no overlapping elements, fits within viewport
   e. Style consistency: colors match wonderlens theme palette
5. If all checks pass AND visual quality improved → commit
6. If errors → agent reads error message, fixes, retries
```

### Metric: UI Quality Score (UQS)

```python
def evaluate(screenshot, dom_tree, spec):
    # Binary gates
    if console_errors(dom_tree): return 0.0
    if overflow_detected(dom_tree): return 0.0

    scores = {
        "elements_present": check_required_elements(dom_tree, spec.elements, weight=0.3),
        "contrast":         check_color_contrast(screenshot, weight=0.15),
        "layout":           check_no_overlap(dom_tree, weight=0.15),
        "theme_match":      check_palette_compliance(screenshot, theme, weight=0.15),
        "visual_quality":   llm_vision_judge(screenshot, spec.description, weight=0.25),
    }
    return weighted_sum(scores)
```

### Key Constraint: Device Resolution

WonderLens has a **2.0–2.4" LCD**, roughly **320x240 pixels**. Every UI component must be designed for this tiny screen. This is actually an advantage for autoresearch — fewer pixels = faster rendering = more iterations.

### Cost & Speed

- Rendering: ~2 seconds per screenshot (Puppeteer)
- Evaluation: ~$0.03 per LLM vision judge call (screenshot → score)
- ~20 iterations per hour per component
- 12 widget primitives × 5 activity steps = ~60 components to build
- But widgets are reusable — most effort goes into the 12 primitives

---

## Loop 3: Asset Generation (Images)

> **Analogy to autoresearch**: Agent modifies image generation prompts → calls image API → vision model evaluates style consistency.

### What It Does

Generates the flat vector SVG/PNG assets needed for activities: entity cards, emoji icons, badges, scene backgrounds. Iterates on the generation prompt until output matches the WonderLens art direction.

### Files

```
loop3_assets/
├── program.md               — Agent instructions for asset generation
├── style_guide/             — Read-only reference
│   ├── master_prompt.md     — Base style prompt all generation shares
│   ├── color_palette.yaml   — Hex codes + usage rules
│   ├── reference_images/    — 5-10 approved reference assets
│   └── anti_examples/       — "NOT like this" examples
├── prompts/                 — The files the agent modifies
│   ├── entity_card.md       — Prompt template for entity illustrations
│   ├── badge.md             — Prompt template for achievement badges
│   ├── emoji.md             — Prompt template for emoji icons
│   └── background.md        — Prompt template for scene backgrounds
├── outputs/                 — Generated images (agent adds here)
│   ├── card_animal_ladybug.svg
│   ├── badge_polka_dot_patrol.svg
│   └── ...
├── evaluate.py              — Style consistency scoring
└── results.tsv
```

### The Loop

```
1. Agent reads the activity design to know what assets are needed:
   "Ladybug entity card, Polka-Dot Patrol badge, park background"
2. Agent modifies the prompt template (inject entity-specific details)
3. Call image generation API (e.g., DALL-E 3 / Flux / Midjourney)
   with the combined master_prompt + entity_prompt
4. evaluate.py scores the output:
   a. Style consistency: CLIP similarity to reference images (>0.85 threshold)
   b. Transparent background: alpha channel check for entity cards
   c. Color palette compliance: >90% of pixels within allowed palette
   d. Complexity: not too detailed for small screen (edge count heuristic)
   e. Age-appropriateness: LLM vision check for scary/inappropriate elements
   f. Resolution: meets minimum (512x512 for cards, 1024x768 for backgrounds)
5. If all checks pass → save to outputs/, commit
6. If style is off → agent adjusts prompt, retries (up to 5 attempts per asset)
7. If 5 attempts fail → flag for human review
```

### Metric: Asset Quality Score (AQS)

```python
def evaluate(image, reference_set, asset_type):
    # Binary gates
    if asset_type == "card" and not has_transparency(image): return 0.0
    if below_min_resolution(image, asset_type): return 0.0

    scores = {
        "style_clip":      clip_similarity(image, reference_set, weight=0.35),
        "palette":         palette_compliance(image, allowed_colors, weight=0.2),
        "complexity":      edge_density_check(image, max_threshold, weight=0.15),
        "age_appropriate": llm_vision_safety(image, weight=0.15),
        "aesthetics":      llm_vision_judge(image, style_description, weight=0.15),
    }
    return weighted_sum(scores)
```

### Important Limitation

Image generation has the **lowest iteration speed** of all 5 loops — each generation takes 10-30 seconds and costs $0.04-0.08. This limits throughput to ~60-120 assets per overnight run. But you only need ~20-30 assets per activity demo, so this is manageable.

### Human Review Gate

Unlike Loops 1-2, asset generation **should** have a human review step. The LLM evaluator catches obvious failures (wrong style, inappropriate content) but can't judge subtle aesthetic quality. Recommendation: auto-generate → auto-evaluate → queue the top 3 candidates per asset for human pick.

---

## Loop 4: Animation & Audio

> **Analogy to autoresearch**: Weakest fit. More like a build pipeline with quality gates than a true optimization loop.

### What It Does

Takes static SVG assets from Loop 3 and:
1. Separates into animation layers (body, limbs, eyes, etc.)
2. Applies Lottie animation presets (idle_bounce, celebration, appear, etc.)
3. Generates/selects sound effects and music loops
4. Validates that animations play correctly and match dialogue timing

### Files

```
loop4_animation/
├── program.md
├── static_assets/           — Input from Loop 3 (read-only)
├── lottie/                  — Agent generates/modifies these
│   ├── ladybug_idle.json
│   ├── badge_reveal.json
│   ├── celebration_sparkle.json
│   └── ...
├── audio/
│   ├── sfx_celebration.opus
│   ├── sfx_photo_shutter.opus
│   └── ambient_park.opus
├── animation_presets/       — 9 preset templates (read-only)
│   ├── idle_bounce.json
│   ├── celebration.json
│   └── ...
├── validate.js              — Lottie player: does it render? Timing correct?
└── results.tsv
```

### The Loop

```
1. Agent reads the activity design's screen descriptions to identify animations needed:
   "Step 1: sparkle animation on each spot of the ladybug"
   "Step 4: all 4 photos glow with golden border"
   "Step 5: badge reveal with celebration"
2. For each animation:
   a. Select the closest preset (e.g., "celebration" for badge reveal)
   b. Modify the Lottie JSON: inject asset-specific layers, colors, timing
   c. validate.js renders 3 seconds into a headless Lottie player
   d. Check: does it play without errors? Duration match spec? No visual glitches?
3. For audio:
   a. Select from curated library OR generate via audio API
   b. Check: duration fits the step? Volume normalized? Format correct (opus)?
4. If all pass → commit
```

### Metric: Animation/Audio Quality Score (AAQS)

```python
def evaluate(lottie_json, audio_file, step_spec):
    # Binary gates
    if not lottie_renders(lottie_json): return 0.0
    if duration_mismatch(lottie_json, step_spec.duration, tolerance=0.5): return 0.0

    scores = {
        "renders_clean":   no_visual_glitches(lottie_json, weight=0.3),
        "timing_match":    duration_within_range(lottie_json, step_spec, weight=0.25),
        "color_on_brand":  palette_check(lottie_json, theme, weight=0.2),
        "audio_quality":   audio_format_check(audio_file, weight=0.15),
        "loop_seamless":   loop_check(lottie_json, weight=0.1),  # for idle animations
    }
    return weighted_sum(scores)
```

### Why This Is the Weakest Loop

- Lottie JSON is complex — LLMs can generate it but error rate is high
- "Does this animation feel good?" is almost impossible to auto-evaluate
- Audio selection is mostly a lookup problem, not an optimization problem
- **Recommendation**: Use this loop for validation and simple modifications, not generation from scratch. Pre-build the 9 preset templates manually, then let the agent customize (colors, timing, layers) per activity.

---

## Loop 5: Pipeline Integration

> **Analogy to autoresearch**: Integration tests = `val_bpb`. Pipeline orchestration code = `train.py`.

### What It Does

Wires everything together into a working end-to-end demo: photo input → vision → conversation → activity transition → screen rendering → TTS. Iterates on the orchestration code until the full pipeline produces a correct demo run.

### Files

```
loop5_pipeline/
├── program.md
├── activity_designs/        — Gold standard (read-only)
├── prompts/                 — From Loop 1 (read-only)
├── frontend/                — From Loop 2 (read-only)
├── assets/                  — From Loop 3+4 (read-only)
├── src/                     — The files the agent modifies
│   ├── pipeline.py          — Main orchestration (FastAPI endpoint)
│   ├── conversation.py      — ConversationService (state machine)
│   ├── activity_orchestrator.py — Activity selection + execution
│   ├── recipe_generator.py  — LLM → JSON composition recipe
│   └── config.yaml          — Wiring configuration
├── test_scenarios/          — Integration test scripts
│   ├── scenario_ladybug.yaml  — Full expected conversation flow
│   └── scenario_toy_dinosaur.yaml
├── run_demo.py              — Runs a full simulated demo session
├── evaluate.py              — Checks pipeline output against expected
└── results.tsv
```

### The Loop

```
1. Agent reads a test scenario:
   "Child photographs ladybug → system should produce Step 1 dialogue →
    child says 'It has spots!' → system should transition to mission →
    child takes 3 more photos → system should celebrate → close with IB concepts"
2. Agent modifies pipeline code (orchestrator, state machine, recipe generator)
3. run_demo.py executes the full scenario:
   - Simulates vision API (returns "ladybug" classification)
   - Feeds turns through conversation service
   - Captures: response text, screen recipe JSON, timing, errors
4. evaluate.py checks:
   a. Does each turn produce a response? (no crashes, no timeouts)
   b. Does conversation phase transition correctly? (FREE_FORM → ACTIVITY → ENDING)
   c. Does the recipe JSON validate against widget schema?
   d. Is response latency < 2 seconds per turn?
   e. Does the dialogue match the prompt-engineered output from Loop 1?
   f. Does the recipe reference valid asset IDs from Loop 3?
5. If all checks pass → commit
6. If integration error → agent reads traceback, fixes, retries
```

### Metric: Pipeline Integration Score (PIS)

```python
def evaluate(demo_run, scenario):
    # Binary gates
    if any_crashes(demo_run): return 0.0
    if any_timeout(demo_run, max_seconds=5): return 0.0

    scores = {
        "phase_transitions": correct_phase_sequence(demo_run, scenario, weight=0.25),
        "dialogue_quality":  compare_to_loop1_output(demo_run.responses, weight=0.25),
        "recipe_valid":      schema_validate_all_recipes(demo_run.recipes, weight=0.2),
        "latency":           all_turns_under_threshold(demo_run.latencies, 2.0, weight=0.15),
        "asset_refs_valid":  all_asset_ids_exist(demo_run.recipes, asset_library, weight=0.15),
    }
    return weighted_sum(scores)
```

### What the Agent Modifies

| Component | Type of Change | Example |
|---|---|---|
| State machine transitions | When to move between phases | "Transition to ACTIVITY after 3 turns, not 5" |
| Activity selection logic | Which activity to pick | "If entity has visual patterns, prefer category 5" |
| Recipe generation prompt | How to produce screen JSON | "Include progress_tracker widget in mission steps" |
| Error handling | Graceful degradation | "If recipe validation fails, use default recipe" |
| Config wiring | Which providers to use | "Use Gemini Flash for conversation, Pro for evaluation" |

---

## Cross-Loop Data Flow

```
Loop 0 (Activity Design)
  │
  ├──→ Loop 1: Activity design → system prompt optimization
  │         └──→ Optimized prompts ──→ Loop 5 (pipeline uses them)
  │
  ├──→ Loop 2: Screen descriptions → React components
  │         └──→ Widget components ──→ Loop 5 (pipeline renders them)
  │
  ├──→ Loop 3: Entity list → asset generation
  │         └──→ Static SVG/PNG ──→ Loop 4 (animate them)
  │                              ──→ Loop 5 (pipeline references them)
  │
  └──→ Loop 4: Static assets → Lottie animations + audio
            └──→ Animation JSON ──→ Loop 5 (pipeline plays them)

Loop 5 (Integration) consumes outputs from ALL other loops.
```

---

## Execution Plan: How to Run All 5

### Phase 1: Parallel Start (Day 1)

Run simultaneously on separate machines/sessions:

| Machine | Loop | Estimated Time | Output |
|---|---|---|---|
| Machine A | Loop 1 (Prompts) | 4-6 hours | Optimized system prompt + few-shot examples |
| Machine B | Loop 2 (Frontend) | 4-8 hours | 12 widget primitives + 5 activity step components |
| Machine C | Loop 3 (Assets) | 6-8 hours | ~30 static assets (cards, badges, backgrounds) |

### Phase 2: Sequential (Day 2 morning)

| Machine | Loop | Input | Estimated Time | Output |
|---|---|---|---|---|
| Machine C | Loop 4 (Animation) | Loop 3 assets | 2-4 hours | Animated Lottie files + audio selection |

### Phase 3: Integration (Day 2 afternoon)

| Machine | Loop | Input | Estimated Time | Output |
|---|---|---|---|---|
| Machine A | Loop 5 (Pipeline) | All above | 4-8 hours | Working end-to-end demo |

### Total: ~2 days from activity designs to working demo

(Assuming one activity as the target. Scale linearly for more activities.)

---

## Risk Assessment: Where Each Loop Might Fail

| Loop | Biggest Risk | Mitigation |
|---|---|---|
| 1 (Prompts) | LLM-as-judge scores plateau — prompt changes stop improving | Add more evaluation dimensions, try different base models |
| 2 (Frontend) | Tiny screen (320×240) makes layout extremely constrained | Build mobile-first, test at actual resolution from the start |
| 3 (Assets) | Style inconsistency across different entities | Strong master prompt + CLIP scoring with tight threshold |
| 4 (Animation) | Lottie JSON is brittle — LLM edits break rendering | Use presets as templates, only modify parameters (colors, timing), not structure |
| 5 (Pipeline) | Integration bugs are combinatorial — many failure modes | Narrow test scenarios to ONE activity first, expand after success |

---

## Recommended Starting Point

**Start with Loop 1 + Loop 2 in parallel.**

Why:
- Loop 1 (Prompts) is cheapest, fastest, highest-ROI, and validates whether the activity designs translate into actual LLM-generated conversation
- Loop 2 (Frontend) unblocks Loop 5, and the 12 widget primitives are reusable across ALL activities
- Loop 3 (Assets) can wait — placeholder images work fine for pipeline testing
- Together, Loop 1 + 2 give you a "conversation works + screens look right" demo within 24 hours, even with placeholder art

---

*End of 5-Loop Architecture Map*
