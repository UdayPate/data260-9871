"""HW8 Part 2 - Reviewer: reads a draft from <PREFIX>_drafts, sends {status, answer} to <PREFIX>_final."""

from agent_common import DRAFTS, FINAL, PREFIX, ask_model, parse_json_object, run_stage

SYSTEM = (
    "You are the Reviewer for a community sports league office. Check that the draft answers the question, "
    "follows the plan and is clear. Reply with JSON only: "
    '{"approved": true or false, "comment": "<one short sentence>"}'
)


def review(message: dict) -> dict:
    draft = message["draft"].strip()
    if not draft:  # deterministic guard: never approve an empty answer, whatever the model says
        return {"status": "rejected", "answer": draft, "review": "draft is empty"}
    try:
        verdict = parse_json_object(ask_model(
            SYSTEM, f"Question: {message['question']}\n\nPlan: {message['plan']}\n\nDraft:\n{draft}"))
        approved, comment = verdict.get("approved") is True, str(verdict.get("comment", ""))
    except ValueError:
        approved, comment = False, "reviewer could not parse the model's verdict"
    return {"status": "approved" if approved else "rejected", "answer": draft, "review": comment}


if __name__ == "__main__":
    run_stage("reviewer", DRAFTS, FINAL, f"{PREFIX}_reviewers", review)
