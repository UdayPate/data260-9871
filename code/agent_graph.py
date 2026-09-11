"""
DATA-260 Homework 2 - Part 3: Stateful Agent Graph
Refactors the HW1 sequential Planner -> Reviewer -> Finalizer script into
a stateful LangGraph implementing the supervisor pattern: a Supervisor
node routes between Planner and Reviewer nodes based on the current
state, and can loop back to Planner for self-correction if the Reviewer
finds issues. A turn_count ceiling prevents infinite loops.

All LLM calls inside nodes go through src/model_client.py's ModelClient
adapter (per the assignment's requirement), not directly through
LangChain/Ollama.
"""

import json
import re
import sys
from pathlib import Path
from typing import Any, Dict, TypedDict

from langgraph.graph import StateGraph, END

# src/ is a sibling of code/ at the repo root - add it to the import path
REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

from model_client import ModelClient  # noqa: E402


# ---------------------------------------------------------------------
# Step 2: Shared state
# ---------------------------------------------------------------------

class AgentState(TypedDict):
    title: str
    content: str
    email: str
    strict: bool
    task: str
    llm: Any
    planner_proposal: Dict[str, Any]
    reviewer_feedback: Dict[str, Any]
    turn_count: int
    turn_ceiling: int


# ---------------------------------------------------------------------
# JSON helpers (same approach as agents_demo.py)
# ---------------------------------------------------------------------

def extract_json(text: str) -> Dict[str, Any]:
    text = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL)
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if not match:
        raise ValueError(f"No JSON object found in model output:\n{text}")
    return json.loads(match.group())


# ---------------------------------------------------------------------
# Step 3: Agent nodes
# ---------------------------------------------------------------------

def planner_node(state: AgentState) -> Dict[str, Any]:
    print("---NODE: Planner---")
    llm: ModelClient = state["llm"]

    feedback_note = ""
    if state.get("reviewer_feedback") and state["reviewer_feedback"].get("issues"):
        issues = state["reviewer_feedback"]["issues"]
        feedback_note = (
            f"\n\nThe Reviewer found issues with your previous attempt: {issues}. "
            f"Fix these issues in this new attempt."
        )

    messages = [
        {
            "role": "system",
            "content": "You are a Planner agent. Given a title and content, propose "
                       "exactly 3 short topical tags (lowercase, 1-3 words each) and a "
                       "one-sentence summary of at most 25 words. Derive both purely "
                       "from the input text, not fixed categories.",
        },
        {
            "role": "user",
            "content": f"Title: {state['title']}\nContent: {state['content']}"
                       f"{feedback_note}\n\n"
                       f'Respond ONLY with valid JSON: {{"tags": ["tag1", "tag2", "tag3"], '
                       f'"summary": "your summary here"}}',
        },
    ]
    raw = llm.complete(messages)
    proposal = extract_json(raw)
    print(f"  Proposal: {proposal}")
    # Clear any stale reviewer_feedback from a previous attempt - a fresh
    # proposal has not been reviewed yet, so the router must send it back
    # to the Reviewer next, not loop straight back to the Planner again.
    return {"planner_proposal": proposal, "reviewer_feedback": {}}


def reviewer_node(state: AgentState) -> Dict[str, Any]:
    print("---NODE: Reviewer---")
    llm: ModelClient = state["llm"]
    proposal = state["planner_proposal"]

    messages = [
        {
            "role": "system",
            "content": "You are a Reviewer agent. Check a draft's tags and summary "
                       "for quality against these rules: (1) exactly 3 tags, each "
                       "1-3 words, lowercase, genuinely specific to the content; "
                       "(2) summary is one sentence, at most 25 words, and accurate.",
        },
        {
            "role": "user",
            "content": f"Title: {state['title']}\nContent: {state['content']}\n\n"
                       f"Draft to review: {json.dumps(proposal)}\n\n"
                       f'Respond ONLY with valid JSON: {{"issues": ["issue1", ...]}} '
                       f'(use an empty list if there are no issues).',
        },
    ]
    raw = llm.complete(messages)
    feedback = extract_json(raw)
    print(f"  Feedback: {feedback}")
    return {"reviewer_feedback": feedback}


def supervisor_node(state: AgentState) -> Dict[str, Any]:
    """Only job: update state (increment the turn counter)."""
    new_turn_count = state.get("turn_count", 0) + 1
    print(f"---NODE: Supervisor (turn {new_turn_count})---")
    return {"turn_count": new_turn_count}


# ---------------------------------------------------------------------
# Step 4: Routing function (reads state, decides where to go next)
# ---------------------------------------------------------------------

def router_logic(state: AgentState) -> str:
    ceiling = state.get("turn_ceiling", 6)

    if state["turn_count"] >= ceiling:
        print(f"  [ROUTER] turn_count={state['turn_count']} >= ceiling={ceiling} -> END")
        return "end"

    if not state.get("planner_proposal"):
        print("  [ROUTER] no proposal yet -> planner")
        return "planner"

    feedback = state.get("reviewer_feedback")
    if not feedback:
        print("  [ROUTER] has proposal, not yet reviewed -> reviewer")
        return "reviewer"

    if feedback.get("issues"):
        print(f"  [ROUTER] reviewer found issues {feedback['issues']} -> planner (retry)")
        return "planner"

    print("  [ROUTER] reviewed, no issues -> END")
    return "end"


# ---------------------------------------------------------------------
# Step 5: Assemble the graph
# ---------------------------------------------------------------------

def build_graph():
    builder = StateGraph(AgentState)

    builder.add_node("supervisor", supervisor_node)
    builder.add_node("planner", planner_node)
    builder.add_node("reviewer", reviewer_node)

    builder.set_entry_point("supervisor")

    builder.add_conditional_edges(
        "supervisor",
        router_logic,
        {"planner": "planner", "reviewer": "reviewer", "end": END},
    )
    builder.add_edge("planner", "supervisor")
    builder.add_edge("reviewer", "supervisor")

    return builder.compile()


# ---------------------------------------------------------------------
# Step 6: Run and test
# ---------------------------------------------------------------------

def main():
    graph = build_graph()

    llm = ModelClient(model="qwen3:8b", temperature=0.7)
    initial_state: AgentState = {
        "title": "San Jose Strikers vs Milpitas Warriors - Rivalry Clash",
        "content": (
            "The San Jose Strikers and Milpitas Warriors renew their fierce Bay Area "
            "rivalry this weekend at Cricket Ground South. Gates open at 9:00 AM with "
            "the toss scheduled for 9:30 AM."
        ),
        "email": "student@example.com",
        "strict": False,
        "task": "generate_tags_and_summary",
        "llm": llm,
        "planner_proposal": {},
        "reviewer_feedback": {},
        "turn_count": 0,
        "turn_ceiling": 6,
    }

    print("=== Streaming graph execution ===\n")
    current_state = dict(initial_state)  # our own running copy, merged manually

    for step in graph.stream(initial_state):
        for node_name, updates in step.items():
            print(f"STREAM STEP: node='{node_name}' updated keys={list(updates.keys())}")
            current_state.update(updates)  # merge this node's returned updates in

    print("\n=== Final state (llm object omitted) ===")
    printable_state = {k: v for k, v in current_state.items() if k != "llm"}
    print(json.dumps(printable_state, indent=2))

    print("\n=== Final token stats for this run ===")
    print(json.dumps(llm.stats(), indent=2))


if __name__ == "__main__":
    main()