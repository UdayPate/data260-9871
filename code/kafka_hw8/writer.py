"""HW8 Part 2 - Writer: reads a plan from <PREFIX>_tasks, sends a draft answer to <PREFIX>_drafts.
All Writer instances share one consumer group, so Kafka splits the tasks topic's partitions between them."""

from agent_common import DRAFTS, PREFIX, TASKS, ask_model, run_stage

SYSTEM = (
    "You are the Writer for a community sports league office. Answer the question by following the plan "
    "step by step. Write plain prose, at most 120 words, no markdown headings."
)


def write(message: dict) -> dict:
    steps = "\n".join(f"{i}. {s}" for i, s in enumerate(message["plan"], 1))
    draft = ask_model(SYSTEM, f"Question: {message['question']}\n\nPlan:\n{steps}", temperature=0.5)
    return {"question": message["question"], "plan": message["plan"], "draft": draft}


if __name__ == "__main__":
    run_stage("writer", TASKS, DRAFTS, f"{PREFIX}_writers", write)
