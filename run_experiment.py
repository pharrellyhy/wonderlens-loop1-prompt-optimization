#!/usr/bin/env python3
"""Wrapper that runs simulate + evaluate with retry logic for rate limits."""

import subprocess
import time
import json

SCENARIOS = [
    ("scenarios/polka_dot_patrol.yaml", "transcripts/latest_polka.json"),
    ("scenarios/fluffy_expedition_dandelion.yaml", "transcripts/latest_fluffy.json"),
    ("scenarios/mood_changer_dog.yaml", "transcripts/latest_mood.json"),
    ("scenarios/dream_whisperer_cat.yaml", "transcripts/latest_dream.json"),
    ("scenarios/time_machine_dinosaur.yaml", "transcripts/latest_dino.json"),
    ("scenarios/mood_changer_dog_silent_exit.yaml", "transcripts/latest_silent.json"),
]


def run_with_retry(cmd, max_retries=5, base_wait=30):
    """Run a command, retrying on 429 errors."""
    for attempt in range(max_retries):
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
        output = result.stdout + result.stderr
        if result.returncode == 0:
            return output
        if "429" in output or "RESOURCE_EXHAUSTED" in output:
            wait = base_wait * (2**attempt)
            print(
                f"  Rate limited (attempt {attempt+1}/{max_retries}), waiting {wait}s..."
            )
            time.sleep(wait)
        else:
            print(f"  Error: {output[-300:]}")
            return None
    print("  Max retries exceeded")
    return None


def transcript_has_errors(path):
    """Check if a transcript has API errors in AI turns."""
    try:
        with open(path) as f:
            t = json.load(f)
        for turn in t.get("turns", []):
            if turn.get("role") == "ai" and "[ERROR:" in turn.get("text", ""):
                return True
    except Exception:
        return True
    return False


def parse_result(output):
    """Extract RESULT line from evaluator output."""
    for line in output.split("\n"):
        if line.startswith("RESULT:"):
            scores = {}
            for pair in line.replace("RESULT: ", "").split():
                k, v = pair.split("=")
                scores[k] = v
            return scores
    return None


def run_experiment(scenarios=None):
    """Run simulate + evaluate for all scenarios, return average DQS."""
    if scenarios is None:
        scenarios = SCENARIOS

    results = {}
    for scenario_path, output_path in scenarios:
        name = scenario_path.split("/")[-1].replace(".yaml", "")
        print(f"\n--- {name} ---")

        # Simulate (with retry for rate limits)
        print("  Simulating...")
        for sim_attempt in range(3):
            sim_output = run_with_retry(
                [
                    "uv",
                    "run",
                    "simulate.py",
                    "--scenario",
                    scenario_path,
                    "--output",
                    output_path,
                ]
            )
            if sim_output is None:
                break
            if not transcript_has_errors(output_path):
                break
            print(
                f"  Transcript has API errors, retrying sim (attempt {sim_attempt+2}/3)..."
            )
            time.sleep(20)
        else:
            if transcript_has_errors(output_path):
                print("  FAILED — transcript still has errors after retries")
                results[name] = None
                continue

        if sim_output is None:
            print(f"  FAILED to simulate {name}")
            results[name] = None
            continue

        # Small delay between sim and eval
        time.sleep(5)

        # Evaluate
        print("  Evaluating...")
        eval_output = run_with_retry(
            [
                "uv",
                "run",
                "evaluate.py",
                "--transcript",
                output_path,
                "--scenario",
                scenario_path,
            ]
        )
        if eval_output is None:
            print(f"  FAILED to evaluate {name}")
            results[name] = None
            continue

        scores = parse_result(eval_output)
        if scores:
            results[name] = scores
            print(
                f"  DQS={scores['DQS']} hook={scores['hook']} content={scores['content']} edge={scores['edge']} tier={scores['tier']} transition={scores['transition']} closing={scores['closing']} multimedia={scores['multimedia']}"
            )
        else:
            print("  Could not parse scores from eval output")
            results[name] = None

        # Delay between scenarios (for Gemini sim rate limits)
        time.sleep(10)

    # Compute average
    dqs_values = [float(r["DQS"]) for r in results.values() if r is not None]
    if dqs_values:
        avg = sum(dqs_values) / len(dqs_values)
        print(
            f"\n=== Average DQS: {avg:.4f} ({len(dqs_values)}/{len(scenarios)} scenarios) ==="
        )
        # Per-scenario summary
        for name, r in results.items():
            if r:
                print(f"  {name}: DQS={r['DQS']} hook={r['hook']}")
            else:
                print(f"  {name}: FAILED")
        return avg, results
    else:
        print("\n=== No valid results ===")
        return None, results


if __name__ == "__main__":
    avg, results = run_experiment()
    if avg is not None:
        print(f"\nFINAL_AVG_DQS={avg:.4f}")
