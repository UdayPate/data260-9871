"""
DATA-260 Homework 9 - Part 4: builds the reference dataset and the three INPUT datasets (SEED 9871).

reference_dataset.json  ground truth: the s9871_rel facts for every fixture used in any question (the Evaluator reads only this)
training_data.json / validation_data.json / test_data.json   [{"id", "question"}] only - no expected answers, no categories
Each split uses different fixtures (the test fixtures are never seen while developing). The generator checks that the Evaluator's
reading of every question (qa_rules) matches what the template intended, so a template typo cannot silently change a label.
"""

import json
import random
import sys
from pathlib import Path

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent / "cache_hw9"))
from facts import fixture_facts  # noqa: E402
from qa_rules import asks_unrecorded, attributes_asked, fixture_codes  # noqa: E402

SEED = 9871
DATA = HERE / "data"
ASK = {  # attribute -> question templates (two phrasings, picked by the seeded RNG)
    "home_team": ["Which team is the home team for fixture {c}?", "Who hosts fixture {c}?"],
    "home_ground": ["What is the home ground for fixture {c}?", "At which venue is fixture {c} played?"],
    "teams": ["Who is playing in fixture {c}?"],
    "spots": ["How many player spots are available for fixture {c}?", "How many open slots are left on fixture {c}?"],
    "fixture_name": ["What is the name of fixture {c}?"],
}
COMPOUND = [  # (template, attributes it asks for)
    ("For fixture {c}, which team is the home team and what is its home ground?", {"home_team", "home_ground"}),
    ("Who is playing in fixture {c} and how many spots are left?", {"teams", "spots"}),
    ("What is the name of fixture {c} and where is it played?", {"fixture_name", "home_ground"}),
    ("Tell me the home team and the number of open slots for fixture {c}.", {"home_team", "spots"}),
]
UNRECORDED_Q = ["Who is the referee for fixture {c}?", "What time does fixture {c} kick off?", "What is the ticket price for fixture {c}?",
                "What was the final score of fixture {c}?"]
UNRELATED = {"training": ["What is the capital of France?", "Write a short poem about autumn."],
             "validation": ["What is 15 times 12?", "Recommend a good pasta recipe."],
             "test": ["What is the tallest mountain in the world?", "Translate 'good morning' into Spanish.", "Explain how photosynthesis works."]}
#            simple  compound two-fixture nonexistent unrecorded
PLAN = {"training": (5, 3, 1, 1, 2), "validation": (5, 3, 1, 1, 2), "test": (6, 4, 2, 1, 2)}
GHOST = {"training": "FX-9871-09101", "validation": "FX-9871-09102", "test": "FX-9871-09103"}  # beyond the last fixture id (5004)


def all_fixtures() -> dict:
    from sqlalchemy import text

    from facts import engine
    with engine().connect() as conn:
        rows = conn.execute(text("SELECT f.fixture_code, f.fixture_name, f.teams_players, f.spots_available, t.team_name, t.home_ground "
                                 "FROM fixtures f JOIN teams t ON t.id = f.home_team_id ORDER BY f.fixture_code")).all()
    return {c: {"fixture_name": n, "teams_players": tp, "home_team": ht, "home_ground": hg, "spots_available": sp} for c, n, tp, sp, ht, hg in rows}


def main() -> None:
    rng = random.Random(SEED)
    pool = [f"FX-9871-{i:05d}" for i in rng.sample(range(5, 5000), 80)]
    found = {c: f for c, f in fixture_facts(pool).items() if f}
    pool = [c for c in pool if c in found]
    cursor = 0
    splits = {}
    for split, (n_simple, n_comp, n_two, n_ghost, n_unrec) in PLAN.items():
        need = n_simple + n_comp + 2 * n_two + n_unrec
        codes, cursor = pool[cursor:cursor + need], cursor + need
        assert len(codes) == need
        it = iter(codes)
        items = []  # (question, intended attribute set or None)
        attrs = list(ASK)
        for i in range(n_simple):
            a = attrs[i % len(attrs)]
            items.append((rng.choice(ASK[a]).format(c=next(it)), {a}))
        for i in range(n_comp):
            t, a = COMPOUND[i % len(COMPOUND)]
            items.append((t.format(c=next(it)), a))
        for i in range(n_two):
            a = ["home_ground", "home_team"][i % 2]
            c1, c2 = next(it), next(it)
            items.append((f"What is the {'home ground' if a == 'home_ground' else 'home team'} of fixture {c1} and of fixture {c2}?", {a}))
        for _ in range(n_ghost):
            items.append((ASK["home_team"][0].format(c=GHOST[split]), {"home_team"}))
        for i in range(n_unrec):
            items.append((UNRECORDED_Q[(i + (2 if split == "test" else 1 if split == "validation" else 0)) % 4].format(c=next(it)), None))
        for q in UNRELATED[split]:
            items.append((q, None))
        rng.shuffle(items)
        splits[split] = items
    reference = all_fixtures()  # the WHOLE table: a code that is not listed here really does not exist
    # the labels the Evaluator will derive from the question text must equal what each template intended
    for split, items in splits.items():
        for q, intended in items:
            read = set(attributes_asked(q)) if not asks_unrecorded(q) else None
            if fixture_codes(q) and intended is not None:
                assert read == intended, (q, read, intended)
            if intended is None and fixture_codes(q):
                assert asks_unrecorded(q), q
    for split, items in splits.items():
        data = [{"id": f"{split[:3]}_{i + 1:02d}", "question": q} for i, (q, _) in enumerate(items)]
        (DATA / f"{split}_data.json").write_text(json.dumps(data, indent=2), encoding="utf-8")
        print(f"{split}_data.json: {len(data)} questions")
    head = {"description": "Ground truth for the Part 4 Evaluator Agent: every league fixture exported from s9871_rel (fixtures JOIN teams). "
                           "A fixture code that is not listed here does not exist in the league.",
            "source": "MySQL s9871_rel", "seed": SEED, "fixture_count": len(reference)}
    body = ",\n".join(f"    {json.dumps(c)}: {json.dumps(f)}" for c, f in reference.items())  # one fixture per line
    (DATA / "reference_dataset.json").write_text(json.dumps(head, indent=2)[:-2] + ',\n  "fixtures": {\n' + body + "\n  }\n}\n", encoding="utf-8")
    print(f"reference_dataset.json: {len(reference)} fixtures")
    codes_by_split = {s: {c for q, _ in it for c in fixture_codes(q)} for s, it in splits.items()}
    assert not (codes_by_split["training"] & codes_by_split["test"]) and not (codes_by_split["validation"] & codes_by_split["test"])
    assert not (codes_by_split["training"] & codes_by_split["validation"] - set(GHOST.values()))
    print("no fixture appears in more than one split")


if __name__ == "__main__":
    main()
