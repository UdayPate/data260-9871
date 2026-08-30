"""
DATA-260 Homework 1 - Part 2: Agentic AI
Two small agents (Planner, Reviewer) plus a finalization step that produce
exactly 3 topical tags and a <=25 word summary from a domain entity's
title/content, using a local LLM served through Ollama.

Domain: Community sports league fixtures (DOMAIN_ID = 7)
Model: qwen3:8b
"""

import json
import re

from langchain_ollama import ChatOllama

# Model client - temperature is intentionally a parameter here since
# Part 3 requires re-running this pipeline at temperature 0.7 and 0.0.
model = ChatOllama(model="qwen3:8b", temperature=0.7)


def run_planner(title, content, llm=None):
    """Planner agent: proposes 3 tags + a <=25 word summary from the input."""
    llm = llm or model
    prompt = f"""You are a Planner agent. Given a title and content, propose:
- exactly 3 short topical tags (lowercase, 1-3 words each)
- a one-sentence summary of at most 25 words

Do not use fixed categories - derive tags and summary purely from the input text.

Title: {title}
Content: {content}

Respond ONLY with valid JSON in this exact format, nothing else:
{{"tags": ["tag1", "tag2", "tag3"], "summary": "your summary here"}}
"""
    response = llm.invoke(prompt)
    return response.content


def run_reviewer(planner_output, title, content, llm=None):
    """Reviewer agent: checks the Planner's draft and corrects it if needed."""
    llm = llm or model
    prompt = f"""You are a Reviewer agent. You will check another AI's draft tags and summary for quality.

Original title: {title}
Original content: {content}

Draft to review:
{planner_output}

Check that:
1. There are EXACTLY 3 tags, each 1-3 words, lowercase, genuinely specific to the content (not generic).
2. The summary is ONE sentence, at most 25 words, and accurately reflects the content.

If the draft already satisfies both conditions, return it unchanged.
If not, correct it yourself.

Respond ONLY with valid JSON in this exact format, nothing else:
{{"tags": ["tag1", "tag2", "tag3"], "summary": "your summary here"}}
"""
    response = llm.invoke(prompt)
    return response.content


def extract_json(text):
    """Strip any reasoning/thinking blocks and pull out the first JSON object."""
    # Remove <think>...</think> reasoning blocks some Ollama models emit
    text = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL)
    # Extract the first {...} block found
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if not match:
        raise ValueError(f"No JSON object found in model output:\n{text}")
    return json.loads(match.group())


def finalize(reviewer_output):
    """Finalizer: parses the Reviewer's output into the final clean JSON."""
    parsed = extract_json(reviewer_output)
    return {
        "tags": parsed["tags"],
        "summary": parsed["summary"],
    }


def main():
    title = "San Jose Strikers vs Milpitas Warriors - Rivalry Clash"
    content = (
        "The San Jose Strikers and Milpitas Warriors renew their fierce Bay Area "
        "rivalry this weekend at Cricket Ground South. The two clubs have split "
        "their last six meetings evenly, and this fixture carries extra weight as "
        "both teams sit near the top of the league standings. San Jose's fast "
        "bowlers will look to exploit a green pitch early, while Milpitas counts "
        "on its experienced middle order to chase down any target. Gates open at "
        "9:00 AM with the toss scheduled for 9:30 AM."
    )

    print("=== Planner Output ===")
    planner_raw = run_planner(title, content)
    print(planner_raw)

    print("\n=== Reviewer Output ===")
    reviewer_raw = run_reviewer(planner_raw, title, content)
    print(reviewer_raw)

    print("\n=== Finalized Output ===")
    final_result = finalize(reviewer_raw)
    print(json.dumps(final_result, indent=2))


if __name__ == "__main__":
    main()