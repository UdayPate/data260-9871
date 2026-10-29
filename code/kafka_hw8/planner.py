"""HW8 Part 2 - Planner: reads a question from <PREFIX>_inbox, sends a 3-step plan to <PREFIX>_tasks."""

from agent_common import INBOX, PREFIX, TASKS, ask_model, parse_json_object, run_stage

SYSTEM = (
    "You are the Planner for a community sports league office. Break the user's question into exactly 3 short "
    "steps that a writer will follow to answer it. Reply with JSON only, in this shape: "
    '{"steps": ["<step one>", "<step two>", "<step three>"]}'
)


def plan(message: dict) -> dict:
    for _ in range(2):  # one retry if the model's reply is not the requested JSON
        try:
            steps = parse_json_object(ask_model(SYSTEM, message["question"]))["steps"]
            if isinstance(steps, list) and len(steps) == 3 and all(isinstance(s, str) and s.strip() for s in steps):
                return {"question": message["question"], "plan": steps}
        except (ValueError, KeyError):
            pass
    raise RuntimeError("planner could not get a valid 3-step plan from the model")


if __name__ == "__main__":
    run_stage("planner", INBOX, TASKS, f"{PREFIX}_planners", plan)
