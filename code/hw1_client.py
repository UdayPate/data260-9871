"""
DATA-260 Homework 1 - Part 4: hw1_client.py
A small command-line demo that imports the reusable model-adapter
(src/model_client.py) and runs an interactive chat loop. Supports a
/stats command that shows turn count, cumulative token counts, and
serialized conversation-history length, without altering the history.

Run with: python hw1_client.py
Type /stats to see current stats, /exit to quit.
"""

import sys
from pathlib import Path

# src/ is a sibling of code/ at the repo root - add it to the import path
REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

from model_client import ModelClient  # noqa: E402  (import after path setup)


SYSTEM_PROMPT_PATH = REPO_ROOT / "AGENT.md"


def load_system_prompt():
    """Load AGENT.md as the system prompt, if it exists."""
    if SYSTEM_PROMPT_PATH.exists():
        return SYSTEM_PROMPT_PATH.read_text(encoding="utf-8")
    return "You are a helpful assistant."


def print_stats(client):
    stats = client.stats()
    print("\n--- /stats ---")
    print(f"Turn count: {stats['turn_count']}")
    print(f"Cumulative input tokens: {stats['cumulative_input_tokens']}")
    print(f"Cumulative output tokens: {stats['cumulative_output_tokens']}")
    print(f"Cumulative total tokens: {stats['cumulative_total_tokens']}")
    print(f"Serialized history length (chars): {stats['history_length_chars']}")
    print("--------------\n")


def main():
    client = ModelClient(model="qwen3:8b", temperature=0.7)
    system_prompt = load_system_prompt()

    print("DATA-260 HW1 - hw1_client.py")
    print("Type your message, /stats to see stats, or /exit to quit.\n")

    while True:
        user_input = input("You: ").strip()

        if not user_input:
            continue

        if user_input == "/exit":
            client.print_final_summary()
            break

        if user_input == "/stats":
            print_stats(client)
            continue

        # Build the message list: system prompt + full history so far + new user message
        messages = [{"role": "system", "content": system_prompt}]
        messages += client.history
        messages.append({"role": "user", "content": user_input})

        reply = client.complete(messages)
        print(f"\nAssistant: {reply}\n")


if __name__ == "__main__":
    main()