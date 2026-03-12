#!/usr/bin/env python3
"""
WonderLens Prompt Engineering Simulator

Runs a multi-turn simulated conversation using the current system prompt
and a scenario file. Produces a transcript for evaluation.

Usage:
    uv run simulate.py --scenario scenarios/polka_dot_patrol.yaml
    uv run simulate.py --scenario scenarios/polka_dot_patrol.yaml --output transcripts/latest.json
"""

import argparse
import json
import os
import time
import yaml
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

# --- Gemini via Vertex AI ---
from google import genai
from google.genai import types

client = genai.Client(
    vertexai=True,
    project=os.environ["GOOGLE_CLOUD_PROJECT"],
    location=os.environ["GOOGLE_CLOUD_LOCATION"],
)


def load_prompt_files():
    """Load all prompt components from prompts/ directory."""
    base = Path("prompts")

    system_prompt = (base / "system_prompt.md").read_text(encoding="utf-8")
    few_shot = (base / "few_shot.md").read_text(encoding="utf-8")
    context_template = (base / "activity_context_template.md").read_text(
        encoding="utf-8"
    )

    return system_prompt, few_shot, context_template


def load_tier_rules():
    """Load age-tier rules from tier_rules.yaml."""
    with open("tier_rules.yaml", "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def build_tier_constraints(tier_label, tier_rules):
    """Build a tier-specific constraint block to inject into the system prompt."""
    tier_key = tier_label  # e.g., "T0", "T1", "T2", "T3"
    tier = tier_rules.get("tiers", {}).get(tier_key)
    if not tier:
        return ""

    wps = tier["words_per_sentence"]
    return f"""
## STRICT Age-Tier Rules for {tier_key} ({tier['label']}, ages {tier['ages']})

YOU MUST FOLLOW THESE RULES — they are non-negotiable for this tier:

**Language constraints:**
- Words per sentence: {wps[0]}–{wps[1]} words. NEVER exceed {wps[1]} words in a single sentence.
- Max sentences per AI turn: {tier['max_sentences']}
- Vocabulary level: {tier['vocabulary_level']}
- Tone: {tier['tone']}
- Response style: {', '.join(tier['response_style'])}

**Conversation structure:**
- Interaction model: {tier['interaction_model']}
- Max freeform turns: {tier['max_freeform_turns']}
- Pathway rounds: {tier['pathway_rounds'][0]}–{tier['pathway_rounds'][1]}
- Question complexity: {tier['question_complexity']}
- Silent timeout: wait {tier['silent_timeout_seconds']} seconds before re-prompting

**Hook rule for {tier_key}:** {tier['hook_description']}
- GOOD example: "{tier['example_good_hook']}"
- BAD example: "{tier['example_bad_hook']}"

**Closing speech:** {tier['closing_description']}
- Max concept badges: {tier['max_concept_badges']}
- Available key concepts: {', '.join(tier['available_key_concepts'])}

**Engagement threshold:** {tier['engagement_threshold']}
"""


def build_system_message(system_prompt, few_shot, context_template, scenario):
    """Assemble the full system message from components + scenario context."""

    # Load tier rules and build tier constraint block
    tier_rules = load_tier_rules()
    tier_label = scenario.get("tier", "T1")
    tier_constraints = build_tier_constraints(tier_label, tier_rules)

    # Fill activity context template
    activity_context = context_template.format(
        activity_name=scenario.get("activity_name", "Unknown Activity"),
        tier_label=tier_label,
        age_range=scenario.get("age_range", "4-6"),
        entity_name=scenario.get("entity", "unknown"),
        scene_description=scenario.get("scene", ""),
        visual_features=", ".join(scenario.get("visual_features", [])),
        category_name=scenario.get("category", ""),
        key_concepts=", ".join(scenario.get("key_concepts", [])),
        related_concepts=", ".join(scenario.get("related_concepts", [])),
        activity_steps_summary=scenario.get(
            "activity_steps_summary", "Follow the activity as designed."
        ),
        detailed_interaction_script=scenario.get(
            "detailed_interaction_script",
            "No detailed script provided. Use the activity structure above as guidance.",
        ),
    )

    # Replace the {activity_context} placeholder in system prompt
    full_system = system_prompt.replace("{activity_context}", activity_context)

    # Inject tier constraints BEFORE few-shot examples
    full_system += "\n\n" + tier_constraints

    # Append few-shot examples
    full_system += "\n\n---\n\n" + few_shot

    return full_system


SIM_MODEL = os.environ.get("SIM_MODEL", "gemini-3.1-flash-lite-preview")


def call_gemini(
    system_message, conversation_history, model_name=None
):
    """Call Gemini via Vertex AI and return the response text."""
    if model_name is None:
        model_name = SIM_MODEL

    # Build messages
    messages = []
    for turn in conversation_history:
        role = "user" if turn["role"] == "child" else "model"
        messages.append(types.Content(role=role, parts=[types.Part(text=turn["text"])]))

    response = client.models.generate_content(
        model=model_name,
        contents=messages,
        config=types.GenerateContentConfig(
            system_instruction=system_message,
            temperature=0.7,
            max_output_tokens=500,
        ),
    )
    return response.text


def parse_multimedia(ai_response):
    """Parse [SCREEN] and [AUDIO] directives from AI response.

    Returns: (dialogue_text, screen_dict, audio_dict)
    """

    lines = ai_response.strip().split("\n")
    dialogue_lines = []
    screen_directive = {}
    audio_directive = {}

    for line in lines:
        stripped = line.strip()
        if stripped.startswith("[SCREEN]"):
            # Parse: [SCREEN] widget_type: description | animation: name
            content = stripped[len("[SCREEN]") :].strip()
            if content.lower() in ("no change", "none", ""):
                screen_directive = {"widget": "no_change"}
            else:
                parts = [p.strip() for p in content.split("|")]
                for part in parts:
                    if ":" in part:
                        key, val = part.split(":", 1)
                        screen_directive[key.strip().lower()] = val.strip()
                    elif not screen_directive:
                        screen_directive["description"] = part
        elif stripped.startswith("[AUDIO]"):
            content = stripped[len("[AUDIO]") :].strip()
            if content.lower() in ("none", "no audio", ""):
                audio_directive = {}
            else:
                parts = [p.strip() for p in content.split("|")]
                for part in parts:
                    if ":" in part:
                        key, val = part.split(":", 1)
                        audio_directive[key.strip().lower()] = val.strip()
        else:
            dialogue_lines.append(line)

    dialogue_text = "\n".join(dialogue_lines).strip()
    return dialogue_text, screen_directive, audio_directive


def run_simulation(scenario_path, output_path="transcripts/latest.json"):
    """Run a full simulated conversation and save the transcript."""

    # Load scenario
    with open(scenario_path, "r", encoding="utf-8") as f:
        scenario = yaml.safe_load(f)

    # Load prompts
    system_prompt, few_shot, context_template = load_prompt_files()
    system_message = build_system_message(
        system_prompt, few_shot, context_template, scenario
    )

    # Run conversation
    transcript = {
        "scenario": scenario_path,
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "system_prompt_length": len(system_message),
        "turns": [],
    }

    conversation_history = []
    consecutive_silence_count = 0
    exited_early = False

    for turn_spec in scenario.get("turns", []):
        if exited_early:
            break

        role = turn_spec["role"]

        if role == "system":
            # Vision result or other system event — add as context
            event_text = f"[System event: {turn_spec.get('event', 'unknown')}] {json.dumps(turn_spec.get('data', {}))}"
            conversation_history.append({"role": "child", "text": event_text})
            transcript["turns"].append(
                {
                    "role": "system",
                    "event": turn_spec.get("event"),
                    "data": turn_spec.get("data"),
                }
            )

        elif role == "child":
            child_text = turn_spec.get("text", "")
            response_type = turn_spec.get("type", "ideal")

            # Track consecutive silence
            if response_type == "silent" or (not child_text.strip()):
                consecutive_silence_count += 1
                conversation_history.append(
                    {
                        "role": "child",
                        "text": f"[Child is silent, no response. This is silence #{consecutive_silence_count} in a row]",
                    }
                )
            else:
                consecutive_silence_count = 0  # Reset on any response
                conversation_history.append({"role": "child", "text": child_text})

            transcript["turns"].append(
                {
                    "role": "child",
                    "type": response_type,
                    "text": child_text,
                    "consecutive_silence": consecutive_silence_count,
                }
            )

            # Check if we need to force a graceful exit
            if consecutive_silence_count >= 2:
                # Force the AI to generate an exit response
                conversation_history.append(
                    {
                        "role": "child",
                        "text": "[SYSTEM: Child has been silent for 2 consecutive turns. You MUST now gracefully exit the activity. Celebrate what was accomplished, say a warm goodbye, and include a tomorrow hook. Do NOT continue the activity.]",
                    }
                )

                start_time = time.time()
                try:
                    ai_response = call_gemini(system_message, conversation_history)
                    latency = time.time() - start_time
                except Exception as e:
                    ai_response = f"[ERROR: {str(e)}]"
                    latency = -1

                dialogue_text, screen_directive, audio_directive = parse_multimedia(
                    ai_response
                )

                transcript["turns"].append(
                    {
                        "role": "ai",
                        "step": "graceful_exit_consecutive_silence",
                        "text": dialogue_text,
                        "screen": screen_directive,
                        "audio": audio_directive,
                        "raw_response": ai_response,
                        "latency_seconds": round(latency, 2),
                        "exit_reason": "consecutive_silence",
                        "expected": {
                            "must_celebrate": True,
                            "must_not_contain_concepts": consecutive_silence_count <= 2,
                        },
                    }
                )

                print(
                    f"  [EXIT] Consecutive silence x{consecutive_silence_count}: {dialogue_text[:80]}..."
                )
                exited_early = True
                break

        elif role == "ai":
            # Generate AI response
            start_time = time.time()

            try:
                ai_response = call_gemini(system_message, conversation_history)
                latency = time.time() - start_time
            except Exception as e:
                ai_response = f"[ERROR: {str(e)}]"
                latency = -1

            # Parse [SCREEN] and [AUDIO] directives from response
            dialogue_text, screen_directive, audio_directive = parse_multimedia(
                ai_response
            )

            conversation_history.append({"role": "ai", "text": ai_response})

            transcript["turns"].append(
                {
                    "role": "ai",
                    "step": turn_spec.get("step", "unknown"),
                    "text": dialogue_text,
                    "screen": screen_directive,
                    "audio": audio_directive,
                    "raw_response": ai_response,
                    "latency_seconds": round(latency, 2),
                    "expected": {
                        k: v for k, v in turn_spec.items() if k not in ["role", "step"]
                    },
                }
            )

            screen_info = (
                f" | screen: {screen_directive.get('widget', 'none')}"
                if screen_directive
                else ""
            )
            print(
                f"  Step {turn_spec.get('step', '?')}: {dialogue_text[:80]}...{screen_info} ({latency:.1f}s)"
            )

    # Save transcript
    transcript["exited_early"] = exited_early
    transcript["exit_reason"] = "consecutive_silence" if exited_early else None
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(transcript, f, indent=2, ensure_ascii=False)

    print(f"\nTranscript saved: {output_path}")
    print(f"Total turns: {len(transcript['turns'])}")
    return transcript


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="WonderLens Conversation Simulator")
    parser.add_argument("--scenario", required=True, help="Path to scenario YAML file")
    parser.add_argument(
        "--output", default="transcripts/latest.json", help="Output transcript path"
    )
    parser.add_argument(
        "--model", default=None, help="Gemini model name (default: SIM_MODEL from .env)"
    )
    args = parser.parse_args()

    run_simulation(args.scenario, args.output)
