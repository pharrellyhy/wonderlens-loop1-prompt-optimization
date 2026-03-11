# WonderLens Loop 1: Prompt Engineering Autoresearch

> Iteratively optimize the Gemini system prompt for WonderLens activity conversations.
> Agent modifies prompts → simulates conversation → evaluates quality → keeps or reverts.

## Quick Start

```bash
# Prerequisites: install uv (if you don't have it)
curl -LsSf https://astral.sh/uv/install.sh | sh

# Configure .env with your Vertex AI credentials
cp .env.example .env
# Edit .env:
#   GOOGLE_APPLICATION_CREDENTIALS="/path/to/service-account.json"
#   GOOGLE_CLOUD_PROJECT="your-project-id"
#   GOOGLE_CLOUD_LOCATION="us-central1"

# Install dependencies
uv sync

# Copy a completed activity design from Loop 0
cp ../wonderlens-activity-autodesign/designs/ladybug_cat5.md activity_designs/

# Launch Claude Code
claude --dangerously-skip-permissions

# Prompt
Read program.md, run.md, and all files. Then begin the prompt optimization loop.
```

## How It Works

```
┌──────────────────────────────────────────────┐
│  Agent reads current system prompt           │
│  Forms hypothesis: "If I add X, Y improves"  │
│  Makes ONE change to prompts/                │
│           │                                  │
│           ▼                                  │
│  simulate.py: Gemini generates conversation  │
│           │                                  │
│           ▼                                  │
│  evaluate.py: 6-dimension scoring (DQS)      │
│           │                                  │
│     ┌─────┴─────┐                            │
│     │ improved?  │                            │
│     ├─yes─► KEEP (git commit)                │
│     └─no──► REVERT (git checkout)            │
│                                              │
│  Repeat ~120 times/hour                      │
└──────────────────────────────────────────────┘
```

## Files

```
program.md                    — Agent instructions (read this first)
run.md                        — Step-by-step loop execution
simulate.py                   — Conversation simulator (DO NOT MODIFY)
evaluate.py                   — 6-dimension quality scorer (DO NOT MODIFY)
prompts/                      — Agent modifies these
  ├── system_prompt.md        — Main Gemini system prompt
  ├── few_shot.md             — Example conversations
  └── activity_context_template.md — Per-activity variable injection
scenarios/                    — Test conversation paths (DO NOT MODIFY)
  └── polka_dot_patrol.yaml
activity_designs/             — Gold standard designs (DO NOT MODIFY)
transcripts/                  — Simulator output (auto-generated)
results.tsv                   — Experiment log
```

## Scoring Dimensions

| # | Dimension | Weight | Method |
|---|-----------|--------|--------|
| 1 | Hook Rule | GATE | Binary: emotional hook, not knowledge test |
| 2 | Content Match | 0.30 | LLM-as-judge + keyword matching |
| 3 | Edge Case Handling | 0.20 | LLM-as-judge: validate-first pattern |
| 4 | Tier Language | 0.20 | Automated: sentence length, vocabulary |
| 5 | Transition Naturalness | 0.15 | LLM-as-judge: organic vs forced |
| 6 | IB Closing | 0.15 | LLM-as-judge + concept coverage |

## Cost

Uses Gemini via Vertex AI. ~$0.07 per iteration × ~120/hour = ~$8/hour or ~$70 for an overnight run (1000 iterations).

## License

MIT
