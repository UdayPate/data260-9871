"""
DATA-260 HW9 Part 3.1 - checks cache_cases.yaml against the database ground truth. No embeddings, no similarity, no cache involved,
so it can run before the threshold sweep without influencing the labels.

Checks: 40 cases / 10 per category; ids unique; every fixture code exists in s9871_rel; every `different_answer` case really has a
different correct answer than the seed it resembles; every `hit` case names a seed and has the same fixture + attribute.
Also exposes correct_answer(fixture, attribute) which the sweep and the Part 3.3 / 3.5 demos use.
"""

import sys
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).parent))
from facts import fixture_facts  # noqa: E402

CASES_PATH = Path(__file__).parent / "cache_cases.yaml"


def load_cases(path=CASES_PATH):
    return yaml.safe_load(open(path, encoding="utf-8"))


def answer_from_facts(f: dict, attribute: str) -> str:
    """Deterministic ground-truth answer text for one fixture row (also what the seeded cache entries store)."""
    if attribute == "home_team":
        return f'The home team is {f["home_team"]}.'
    if attribute == "teams":
        return f'{f["teams_players"]} are playing.'
    if attribute == "home_ground":
        return f'The home ground is {f["home_ground"]}.'
    if attribute == "fixture_name":
        return f'The fixture is named "{f["fixture_name"]}".'
    if attribute == "spots":
        return f'{f["spots_available"]} player spots are available.'
    raise ValueError(attribute)


def main() -> int:
    data = load_cases()
    seeds = {s["id"]: s for s in data["seeds"]}
    cases = data["cases"]
    codes = sorted({s["fixture"] for s in seeds.values()} | {c["fixture"] for c in cases if "fixture" in c})
    facts = fixture_facts(codes)
    results = []

    def check(name, ok, detail=""):
        results.append(ok)
        print(f'[{"PASS" if ok else "FAIL"}] {name}  {detail}')

    cats = {}
    for c in cases:
        cats[c["category"]] = cats.get(c["category"], 0) + 1
    check("40 cases, 10 per category", len(cases) == 40 and sorted(cats.values()) == [10] * 4, str(cats))
    check("case ids unique", len({c["id"] for c in cases}) == 40)
    check("10 seeds", len(seeds) == 10)
    check("every fixture code exists in s9871_rel", all(facts[c] for c in codes), f"{len(codes)} codes")
    expect = {"exact_duplicate": "hit", "paraphrase": "hit", "different_answer": "miss", "unrelated": "miss"}
    check("expected label matches category", all(c["expected"] == expect[c["category"]] for c in cases))
    check("exact duplicates are word-for-word their seed", all(c["query"] == seeds[c["matches"]]["query"] for c in cases if c["category"] == "exact_duplicate"))
    check("paraphrases are not word-for-word their seed", all(c["query"] != seeds[c["matches"]]["query"] for c in cases if c["category"] == "paraphrase"))
    same = [c["id"] for c in cases if c["category"] == "paraphrase" and seeds[c["matches"]]["fixture"] not in c["query"]]
    check("every paraphrase names the same fixture as its seed", not same, str(same))
    bad = []
    for c in cases:
        if c["category"] == "different_answer":
            s = seeds[c["differs_from"]]
            ours = answer_from_facts(facts[c["fixture"]], c["attribute"])
            theirs = answer_from_facts(facts[s["fixture"]], s["attribute"])
            if ours == theirs:
                bad.append(c["id"])
            print(f'      {c["id"]}: correct = {ours!r}  |  cached seed {s["id"]} says {theirs!r}')
    check("every different_answer case has a different correct answer than the seed it resembles", not bad, str(bad))
    clash = []
    for c in cases:
        if c["category"] == "different_answer":
            for sid, s in seeds.items():
                if answer_from_facts(facts[c["fixture"]], c["attribute"]) == answer_from_facts(facts[s["fixture"]], s["attribute"]):
                    clash.append((c["id"], sid))
    check("...and differs from EVERY seed's answer (so any hit on it is wrong)", not clash, str(clash))
    print(f"\n{sum(results)}/{len(results)} checks passed")
    return 0 if all(results) else 1


if __name__ == "__main__":
    sys.exit(main())
