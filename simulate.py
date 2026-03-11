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

from google import genai
from google.genai import types

load_dotenv()


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


def build_system_message(system_prompt, few_shot, context_template, scenario):
    """Assemble the full system message from components + scenario context."""

    # Fill activity context template
    activity_context = context_template.format(
        activity_name=scenario.get("activity_name", "Unknown Activity"),
        tier_label=scenario.get("tier", "T1"),
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
    )

    # Replace the {activity_context} placeholder in system prompt
    full_system = system_prompt.replace("{activity_context}", activity_context)

    # Append few-shot examples
    full_system += "\n\n---\n\n" + few_shot

    return full_system


def call_gemini(
    system_message, conversation_history, model_name="gemini-3.1-flash-lite-preview", max_retries=5
):
    """Call Gemini via Vertex AI and return the response text."""

    # Build messages
    messages = []
    for turn in conversation_history:
        role = "user" if turn["role"] == "child" else "model"
        messages.append(types.Content(role=role, parts=[types.Part(text=turn["text"])]))

    for attempt in range(max_retries):
        try:
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
        except Exception as e:
            if "429" in str(e) and attempt < max_retries - 1:
                wait = 2 ** attempt
                print(f"    Rate limited, waiting {wait}s...")
                time.sleep(wait)
            else:
                raise


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

    for turn_spec in scenario.get("turns", []):
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

            if child_text:  # Non-empty child turn
                conversation_history.append({"role": "child", "text": child_text})
            else:  # Silent — send a marker
                conversation_history.append(
                    {
                        "role": "child",
                        "text": "[Child is silent, no response after 3 seconds]",
                    }
                )

            transcript["turns"].append(
                {
                    "role": "child",
                    "type": response_type,
                    "text": child_text,
                }
            )

        elif role == "ai":
            # Generate AI response
            start_time = time.time()

            try:
                ai_response = call_gemini(system_message, conversation_history)
                latency = time.time() - start_time
            except Exception as e:
                ai_response = f"[ERROR: {str(e)}]"
                latency = -1

            conversation_history.append({"role": "ai", "text": ai_response})

            transcript["turns"].append(
                {
                    "role": "ai",
                    "step": turn_spec.get("step", "unknown"),
                    "text": ai_response,
                    "latency_seconds": round(latency, 2),
                    "expected": {
                        k: v for k, v in turn_spec.items() if k not in ["role", "step"]
                    },
                }
            )

            print(
                f"  Step {turn_spec.get('step', '?')}: {ai_response[:80]}... ({latency:.1f}s)"
            )

    # Save transcript
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
        "--model", default="gemini-3.1-flash-lite-preview", help="Gemini model name"
    )
    args = parser.parse_args()

    run_simulation(args.scenario, args.output)
