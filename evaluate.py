#!/usr/bin/env python3
"""
WonderLens Prompt Engineering Evaluator

Scores a conversation transcript against expected outputs on 6 dimensions.
Produces a composite Dialogue Quality Score (DQS) from 0.0 to 1.0.

Usage:
    uv run evaluate.py --transcript transcripts/latest.json --scenario scenarios/polka_dot_patrol.yaml
"""

import argparse
import json
import os
import re
import yaml
from dotenv import load_dotenv

load_dotenv()

# --- LLM-as-judge via OpenAI-compatible API ---
from openai import OpenAI

EVAL_MODEL = os.environ.get("EVAL_MODEL", "gpt-4o-mini")
EVAL_BASE_URL = os.environ.get("EVAL_BASE_URL", "https://api.openai.com/v1")
EVAL_API_KEY = os.environ.get("EVAL_API_KEY", os.environ.get("OPENAI_API_KEY", ""))

eval_client = OpenAI(base_url=EVAL_BASE_URL, api_key=EVAL_API_KEY)


def call_judge(prompt, model_name=None):
    """Call LLM as an evaluator judge via OpenAI-compatible API. Returns the response text."""
    model = model_name or EVAL_MODEL
    try:
        response = eval_client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.1,
            max_tokens=200,
        )
        result = response.choices[0].message.content
        return result if result else "5"
    except Exception as e:
        print(f"  [Judge error: {str(e)[:100]}]")
        return "5"  # Default mid-score on error


def extract_score(judge_response):
    """Extract a numeric score from the judge's response."""
    # Look for patterns like "Score: 8/10", "7/10", "score: 0.8", just "8"
    patterns = [
        r"(\d+(?:\.\d+)?)\s*/\s*10",  # N/10
        r"[Ss]core[:\s]+(\d+(?:\.\d+)?)",  # Score: N
        r"^(\d+(?:\.\d+)?)$",  # Just a number
    ]
    for pattern in patterns:
        match = re.search(pattern, judge_response.strip())
        if match:
            val = float(match.group(1))
            return val / 10.0 if val > 1.0 else val
    return 0.5  # Default if parsing fails


# =========================================================================
# Dimension 1: Hook Rule (GATE — binary pass/fail)
# =========================================================================
def evaluate_hook_rule(transcript, scenario):
    """Check if the AI's first substantive turn uses emotional hook, not knowledge testing."""

    # Find first AI turn
    first_ai = None
    for turn in transcript.get("turns", []):
        if turn["role"] == "ai":
            first_ai = turn
            break

    if not first_ai:
        return False, "No AI turn found"

    ai_text = first_ai.get("text", "")
    expected = first_ai.get("expected", {})

    # Check must_not_contain (knowledge testing phrases)
    must_not = expected.get("must_not_contain", [])
    for phrase in must_not:
        if phrase.lower() in ai_text.lower():
            return False, f"Hook rule violation: contains '{phrase}'"

    # LLM judge: is this an emotional hook or knowledge test?
    prompt = f"""You are evaluating a children's educational AI. The AI's first response to a child photographing an object must use EMOTIONAL engagement (wonder, excitement, imagination) and must NOT test the child's knowledge (asking factual questions like "what color is it?" or "how many legs does it have?").

AI's first response:
"{ai_text}"

Does this response use emotional engagement (PASS) or knowledge testing (FAIL)?
Answer with ONLY "PASS" or "FAIL" followed by a brief reason."""

    result = call_judge(prompt)
    passed = "PASS" in result.upper().split("\n")[0]
    return passed, result.strip()


# =========================================================================
# Dimension 2: Content Match (0.0–1.0)
# =========================================================================
def evaluate_content_match(transcript, scenario):
    """How well does the AI output match the designed dialogue's intent and content?"""

    ai_turns = [t for t in transcript.get("turns", []) if t["role"] == "ai"]
    if not ai_turns:
        return 0.0

    scores = []
    for turn in ai_turns:
        expected = turn.get("expected", {})
        must_contain = expected.get("must_contain", [])
        ai_text = turn.get("text", "")

        if must_contain:
            # Check how many required elements are present
            found = sum(
                1 for phrase in must_contain if phrase.lower() in ai_text.lower()
            )
            scores.append(found / len(must_contain))

        # LLM judge for overall content quality
        prompt = f"""Rate this AI response in a children's educational conversation on a scale of 1-10.

AI response: "{ai_text[:500]}"

Criteria:
- Does it sound natural and warm (not robotic)?
- Is it specific and concrete (not vague)?
- Does it match the expected step: "{turn.get('step', 'unknown')}"?
- Does it advance the activity meaningfully?

Respond with ONLY a number from 1-10."""

        result = call_judge(prompt)
        scores.append(extract_score(result))

    return sum(scores) / len(scores) if scores else 0.0


# =========================================================================
# Dimension 3: Edge Case Handling (0.0–1.0)
# =========================================================================
def evaluate_edge_cases(transcript, scenario):
    """For unexpected/silent child turns, does the AI validate first then redirect?"""

    # Find AI responses to unexpected/silent child turns
    turns = transcript.get("turns", [])
    edge_scores = []

    for i, turn in enumerate(turns):
        if turn["role"] == "child" and turn.get("type") in ["unexpected", "silent"]:
            # Find the next AI turn
            next_ai = None
            for j in range(i + 1, len(turns)):
                if turns[j]["role"] == "ai":
                    next_ai = turns[j]
                    break

            if next_ai:
                child_type = turn.get("type")
                child_text = turn.get("text", "[silent]")
                ai_text = next_ai.get("text", "")
                must_validate = next_ai.get("expected", {}).get(
                    "must_validate_first", False
                )

                prompt = f"""A child in an educational activity gave an {"unexpected response" if child_type == "unexpected" else "no response (silence)"}.

Child said: "{child_text}"
AI responded: "{ai_text[:500]}"

Rate on 1-10:
- {"Does the AI acknowledge/validate the child's response BEFORE redirecting?" if child_type == "unexpected" else "Does the AI gently re-engage without pressure?"}
- Is the response warm and non-judgmental?
- Does the AI successfully guide back to the activity?

Respond with ONLY a number from 1-10."""

                result = call_judge(prompt)
                edge_scores.append(extract_score(result))

    # Also check graceful exit quality if the conversation exited early
    exit_turns = [
        t
        for t in turns
        if t.get("role") == "ai" and t.get("exit_reason") == "consecutive_silence"
    ]
    for exit_turn in exit_turns:
        ai_text = exit_turn.get("text", "")
        prompt = f"""A children's educational AI had to end an activity early because the child was silent for 2 consecutive turns. The AI must exit GRACEFULLY.

AI's exit message: "{ai_text[:500]}"

Rate on 1-10:
- Does it celebrate what the child DID accomplish (even if very little)?
- Is the tone warm, zero-pressure, and cheerful (not disappointed or guilt-tripping)?
- Does it include a "tomorrow hook" (something to look forward to next time)?
- Does it avoid naming IB concepts (since the activity wasn't completed)?
- Is it SHORT and sweet (not a long summary)?

Respond with ONLY a number from 1-10."""

        result = call_judge(prompt)
        edge_scores.append(extract_score(result))

    return (
        sum(edge_scores) / len(edge_scores) if edge_scores else 0.8
    )  # Default OK if no edge cases


# =========================================================================
# Dimension 4: Tier Language (0.0–1.0)
# =========================================================================
def load_tier_rules():
    """Load age-tier rules from tier_rules.yaml."""
    try:
        with open("tier_rules.yaml", "r", encoding="utf-8") as f:
            return yaml.safe_load(f)
    except FileNotFoundError:
        return {"tiers": {}}


def evaluate_tier_language(transcript, scenario):
    """Check: sentence length, sentence count, vocabulary, hook rule, and closing speech match tier rules."""

    tier_key = scenario.get("tier", "T1")
    tier_rules = load_tier_rules()
    tier = tier_rules.get("tiers", {}).get(tier_key)

    if not tier:
        # Fallback if tier_rules.yaml not found
        tier = {
            "words_per_sentence": [5, 12],
            "max_sentences": 2,
            "max_concept_badges": 1,
            "hook_rule": "personal_feeling_hook",
            "response_style": ["simple"],
        }

    wps_min, wps_max = tier["words_per_sentence"]
    max_sentences = tier["max_sentences"]
    max_badges = tier["max_concept_badges"]

    ai_turns = [t for t in transcript.get("turns", []) if t["role"] == "ai"]
    if not ai_turns:
        return 0.0

    scores = []
    for i, turn in enumerate(ai_turns):
        text = turn.get("text", "")
        # Remove tone markers in parens and [SCREEN]/[AUDIO] lines
        clean = re.sub(r"\([^)]*\)", "", text)
        clean = re.sub(r"\[SCREEN\].*", "", clean)
        clean = re.sub(r"\[AUDIO\].*", "", clean)
        clean = clean.strip()

        # Split into sentences
        sentences = re.split(r"[.!?]+", clean)
        sentences = [s.strip() for s in sentences if s.strip()]

        if not sentences:
            scores.append(0.5)
            continue

        turn_score = 0.0
        checks = 0

        # Check 1: Words per sentence within range
        avg_words = sum(len(s.split()) for s in sentences) / len(sentences)
        if avg_words <= wps_max:
            turn_score += 1.0
        elif avg_words <= wps_max * 1.5:
            turn_score += 0.5  # Slightly over
        else:
            turn_score += 0.0  # Way over
        checks += 1

        # Check 2: Sentence count within max
        if len(sentences) <= max_sentences:
            turn_score += 1.0
        elif len(sentences) <= max_sentences + 1:
            turn_score += 0.5  # One sentence over
        else:
            turn_score += 0.0  # Way over
        checks += 1

        # Check 3: First AI turn — hook rule compliance (extra strict)
        if i == 0:
            hook_rule = tier.get("hook_rule", "")
            if hook_rule == "exclamation_name_sound_celebrate_no_question":
                # T0: NO questions at all in first turn
                has_question = "?" in text
                turn_score += 0.0 if has_question else 1.0
            elif hook_rule == "personal_feeling_hook":
                # T1: First question must be about feelings, not facts
                prompt = f"""Is this a personal feeling/emotional question (PASS) or a factual/knowledge question (FAIL)?
First AI turn: "{text[:300]}"
Answer PASS or FAIL only."""
                result = call_judge(prompt)
                turn_score += 1.0 if "PASS" in result.upper() else 0.0
            else:
                turn_score += 0.8  # No specific check for T2/T3 hooks here
            checks += 1

        # Check 4: Last AI turn — closing speech badges count
        if i == len(ai_turns) - 1:
            concept_keywords = [
                "Form",
                "Function",
                "Causation",
                "Change",
                "Connection",
                "Perspective",
                "Responsibility",
            ]
            concepts_named = sum(
                1 for c in concept_keywords if c.lower() in text.lower()
            )
            if max_badges == 0:
                # T0: should NOT name any concepts
                turn_score += 1.0 if concepts_named == 0 else 0.3
            else:
                # T1-T3: should name the right number
                if concepts_named == max_badges:
                    turn_score += 1.0
                elif concepts_named <= max_badges + 1:
                    turn_score += 0.6
                else:
                    turn_score += 0.3
            checks += 1

        # Check 5: Response style markers present
        style_tags = tier.get("response_style", [])
        if "onomatopoeia" in style_tags:
            # Check for sound words
            has_sounds = bool(
                re.search(
                    r"(woof|meow|roar|boom|splash|crunch|buzz|quack|moo|baa|whoosh|pop)",
                    text.lower(),
                )
            )
            turn_score += 1.0 if has_sounds else 0.3
            checks += 1

        scores.append(turn_score / checks if checks > 0 else 0.5)

    return sum(scores) / len(scores)


# =========================================================================
# Dimension 5: Transition Naturalness (0.0–1.0)
# =========================================================================
def evaluate_transition(transcript, scenario):
    """LLM judge: does the activity feel like it emerges from conversation?"""

    # Get first 3 AI turns (the transition phase)
    ai_turns = [t for t in transcript.get("turns", []) if t["role"] == "ai"][:3]
    if not ai_turns:
        return 0.0

    conversation_text = "\n".join([f"AI: {t.get('text', '')[:300]}" for t in ai_turns])

    prompt = f"""In a children's educational product, the AI must transition from observing a photographed object into a structured activity. The transition must feel NATURAL — like the activity "grows out of" the conversation, not like a sudden task assignment.

GOOD: "You noticed the spots! I wonder if anything else nearby has spots too... want to be a Spot Detective?"
BAD: "Now let's play a game! The rules are: find 3 things with spots."

Here's the actual conversation opening:
{conversation_text}

Rate the transition naturalness from 1-10. Does it feel organic or forced?
Respond with ONLY a number from 1-10."""

    result = call_judge(prompt)
    return extract_score(result)


# =========================================================================
# Dimension 6: IB Closing (0.0–1.0)
# =========================================================================
def evaluate_closing(transcript, scenario):
    """Does the closing celebrate first, then name concepts naturally?"""

    # Get last AI turn
    ai_turns = [t for t in transcript.get("turns", []) if t["role"] == "ai"]
    if not ai_turns:
        return 0.0

    last_ai = ai_turns[-1]
    ai_text = last_ai.get("text", "")
    expected_concepts = scenario.get("key_concepts", [])

    # Check if concepts are mentioned
    concepts_found = sum(1 for c in expected_concepts if c.lower() in ai_text.lower())
    concept_coverage = concepts_found / max(len(expected_concepts), 1)

    prompt = f"""The AI just delivered a closing speech to a child after an educational activity.

Closing speech: "{ai_text[:500]}"

Expected IB concepts to name: {expected_concepts}

Rate on 1-10:
- Does it CELEBRATE the child's achievement FIRST (before any concept naming)?
- Are the concepts named NATURALLY (as praise, not as vocabulary drill)?
- Does it feel like a satisfying ending?

Respond with ONLY a number from 1-10."""

    result = call_judge(prompt)
    judge_score = extract_score(result)

    # Blend judge score with concept coverage
    return 0.6 * judge_score + 0.4 * concept_coverage


# =========================================================================
# Composite Score
# =========================================================================
def evaluate_multimedia(transcript, scenario):
    """Check if screen/audio directives are present and coherent with dialogue."""

    ai_turns = [t for t in transcript.get("turns", []) if t["role"] == "ai"]
    if not ai_turns:
        return 0.0

    scores = []
    for turn in ai_turns:
        screen = turn.get("screen", {})
        audio = turn.get("audio", {})
        text = turn.get("text", "")
        expected = turn.get("expected", {})
        expected_screen = expected.get("expected_screen", {})

        # Check 1: Did the AI output screen directives at all?
        has_screen = bool(
            screen and screen.get("widget") != "no_change" and len(screen) > 0
        )

        # Check 2: If expected_screen has a widget, does the output match?
        if expected_screen and expected_screen.get("widget"):
            widget_match = expected_screen["widget"].lower() in str(screen).lower()
            scores.append(1.0 if widget_match else 0.3)
        elif has_screen:
            scores.append(0.8)  # Has screen output, no specific expectation
        else:
            scores.append(0.4)  # No screen output at all

        # Check 3: Does the screen description make sense for the dialogue?
        if has_screen and screen.get("description"):
            # Simple coherence: are there shared keywords?
            screen_words = set(screen.get("description", "").lower().split())
            text_words = set(text.lower().split())
            overlap = len(screen_words & text_words)
            coherence = min(1.0, overlap / 3) if screen_words else 0.5
            scores.append(coherence)

    return sum(scores) / len(scores) if scores else 0.5


def evaluate_transcript(transcript_path, scenario_path):
    """Run all 7 dimensions and produce composite DQS."""

    with open(transcript_path, "r", encoding="utf-8") as f:
        transcript = json.load(f)
    with open(scenario_path, "r", encoding="utf-8") as f:
        scenario = yaml.safe_load(f)

    print(f"Evaluating: {transcript_path}")
    print(f"Scenario: {scenario_path}")
    print()

    # Dimension 1: Hook Rule (GATE)
    hook_pass, hook_reason = evaluate_hook_rule(transcript, scenario)
    print(f"  D1 Hook Rule:    {'PASS' if hook_pass else 'FAIL'} — {hook_reason[:80]}")

    if not hook_pass:
        print("\n  DQS: 0.000 (Hook rule FAILED — all other dimensions moot)")
        return {
            "dqs": 0.0,
            "hook": "FAIL",
            "content": 0.0,
            "edge": 0.0,
            "tier": 0.0,
            "transition": 0.0,
            "closing": 0.0,
            "multimedia": 0.0,
        }

    # Dimensions 2-7
    content = evaluate_content_match(transcript, scenario)
    print(f"  D2 Content:      {content:.3f}")

    edge = evaluate_edge_cases(transcript, scenario)
    print(f"  D3 Edge Cases:   {edge:.3f}")

    tier = evaluate_tier_language(transcript, scenario)
    print(f"  D4 Tier Lang:    {tier:.3f}")

    transition = evaluate_transition(transcript, scenario)
    print(f"  D5 Transition:   {transition:.3f}")

    closing = evaluate_closing(transcript, scenario)
    print(f"  D6 IB Closing:   {closing:.3f}")

    multimedia = evaluate_multimedia(transcript, scenario)
    print(f"  D7 Multimedia:   {multimedia:.3f}")

    # Weighted composite
    dqs = (
        0.25 * content
        + 0.18 * edge
        + 0.17 * tier
        + 0.13 * transition
        + 0.13 * closing
        + 0.14 * multimedia
    )

    print(f"\n  DQS: {dqs:.3f}")

    return {
        "dqs": round(dqs, 4),
        "hook": "PASS",
        "content": round(content, 4),
        "edge": round(edge, 4),
        "tier": round(tier, 4),
        "transition": round(transition, 4),
        "closing": round(closing, 4),
        "multimedia": round(multimedia, 4),
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="WonderLens Dialogue Evaluator")
    parser.add_argument("--transcript", default="transcripts/latest.json")
    parser.add_argument("--scenario", required=True)
    args = parser.parse_args()

    scores = evaluate_transcript(args.transcript, args.scenario)

    # Output as parseable line for the agent
    print(
        f"\nRESULT: DQS={scores['dqs']} hook={scores['hook']} content={scores['content']} edge={scores['edge']} tier={scores['tier']} transition={scores['transition']} closing={scores['closing']} multimedia={scores['multimedia']}"
    )
