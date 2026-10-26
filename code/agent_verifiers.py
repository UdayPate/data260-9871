"""
DATA-260 Homework 7 - Part 3: deterministic verifiers for the three fixed verification cases.

verify() judges ONE finished agent run. Each case is a short list of CLAIMS the final answer must make, and a
claim only counts as supported if the data the tools actually returned in THAT run backs it up (grounding), for example
"the fixture shown is the first search result" is checked against the order of the search results the agent was given.
It never calls a model and never touches the database, so it is deterministic and testable offline.

oracle() answers a different question - "is the answer true?" - by comparing it with ground truth read from MySQL. It
exists only so the experiment can count the verifier's own mistakes:
    false rejection  = the verifier rejected an answer the oracle says is correct (for example a true fact the agent
                       never confirmed with a tool, which the grounding rule refuses to accept)
    false acceptance = the verifier accepted an answer the oracle says is wrong
Both share the same text parsing, so a parsing blind spot would show up in both; that limit is stated in the report.
"""

import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

CODE_RE = re.compile(r"FX-9871-\d{5}")
HOME_LABEL_RE = re.compile(r"(?:home\s*team|hosted\s*by|host(?:ed)?(?:\s*team)?)\s*[:\-]?\s*", re.IGNORECASE)


# --------------------------------------------------------------------------- what the tools actually returned
def observations(messages: list[dict]) -> dict:
    """Facts returned by the tools during one run, rebuilt from the transcript (assistant tool_calls + tool messages)."""
    calls, searches, cards, details, counts = {}, [], {}, {}, None
    for m in messages:
        if m["role"] == "assistant":
            for c in m.get("tool_calls", []):
                calls[c["id"]] = (c["name"], c["args"] if isinstance(c["args"], dict) else {})
        elif m["role"] == "tool":
            name, args = calls.get(m["tool_call_id"], (m.get("name"), {}))
            try:
                env = json.loads(m["content"])
            except (TypeError, ValueError):
                continue
            if not env.get("ok"):
                continue
            data = env["data"]
            if name == "search_fixtures":
                for card in data:
                    cards[card["id"]] = card
                searches.append({"query": str(args.get("query", "")), "ids": [card["id"] for card in data]})
            elif name == "fixture_details":
                details[data["id"]] = data
                cards.setdefault(data["id"], {k: v for k, v in data.items() if k != "home_team"})
            elif name == "team_fixture_counts":
                counts = data
    team_names = {t["team_id"]: t["team_name"] for t in (counts or [])}
    for d in details.values():
        if d.get("home_team"):
            team_names[d["home_team"]["id"]] = d["home_team"]["team_name"]
    code_to_id = {c["fixture_code"]: i for i, c in cards.items() if "fixture_code" in c}
    return {"searches": searches, "cards": cards, "details": details, "counts": counts,
            "team_names": team_names, "code_to_id": code_to_id}


def home_team_id(obs: dict, fixture_id: int):
    if fixture_id in obs["details"] and obs["details"][fixture_id].get("home_team"):
        return obs["details"][fixture_id]["home_team"]["id"]
    return obs["cards"].get(fixture_id, {}).get("home_team_id")


def home_team_name(obs: dict, fixture_id: int):
    """The home team's name IF the run produced evidence for it (a details lookup, or a card id plus a name table)."""
    tid = home_team_id(obs, fixture_id)
    return obs["team_names"].get(tid) if tid is not None else None


# --------------------------------------------------------------------------- reading the final answer
def codes_in(answer: str) -> list[str]:
    seen = []
    for c in CODE_RE.findall(answer):
        if c not in seen:
            seen.append(c)
    return seen


def names_in(text: str, universe: list[str]) -> list[str]:
    low = text.lower()
    return [n for n in sorted(universe, key=len, reverse=True) if n.lower() in low]


def segment_for(answer: str, code: str, codes: list[str]) -> str:
    """The part of the answer that talks about `code`: from its first mention to the next fixture code (or the end)."""
    start = answer.find(code)
    if start < 0:
        return ""
    later = [answer.find(c, start + len(code)) for c in codes if c != code]
    later = [p for p in later if p > start]
    return answer[start: min(later) if later else len(answer)]


def stated_home_names(segment: str, universe: list[str]) -> list[str]:
    """Team names the segment states as the home team: whatever follows a 'Home Team' / 'hosted by' label,
    otherwise every team named in the segment."""
    labelled = []
    for m in HOME_LABEL_RE.finditer(segment):
        labelled += names_in(segment[m.end(): m.end() + 60].split("\n")[0], universe)
    return labelled or names_in(segment, universe)


def _claim(cid: str, text: str, ok: bool, why: str) -> dict:
    return {"id": cid, "claim": text, "supported": bool(ok), "why": why}


def _home_claim(cid, code, expected, answer, codes, universe, evidence_missing_msg):
    if expected is None:
        return _claim(cid, f"home team stated for {code}", False, evidence_missing_msg)
    names = stated_home_names(segment_for(answer, code, codes), universe)
    ok = expected in names
    return _claim(cid, f"home team stated for {code} matches the details the tool returned", ok,
                  f"tool data says {expected}; the answer says {names or 'no team'}")


# --------------------------------------------------------------------------- the verifier
def verify(case_id: str, run: dict, universe: list[str]) -> dict:
    """Judge one finished run. `universe` = every team name (used only to read team names out of the answer text)."""
    answer = run.get("final_answer")
    if not answer:
        return {"passed": False, "claims": [], "unsupported_claims": 0,
                "feedback": [f"no final answer was produced (stop_reason={run.get('stop_reason')})"]}
    obs = observations(run["messages"])
    codes = codes_in(answer)
    claims = []

    if case_id == "A":
        search = next((s for s in obs["searches"] if "lions" in s["query"].lower()), None)
        if search is None or not search["ids"]:
            claims.append(_claim("A0", "searched for 'Lions' and got results", False, "no successful search for 'Lions' in this run"))
        else:
            first = search["ids"][0]
            fcode = obs["cards"][first]["fixture_code"]
            claims.append(_claim("A1", "the fixture shown is the FIRST search result", codes == [fcode],
                                 f"answer shows {codes or 'no fixture code'}; the search listed fixture {first} ({fcode}) first, "
                                 f"in the order {search['ids'][:6]}"))
            claims.append(_home_claim("A2", fcode, home_team_name(obs, first), answer, codes or [fcode], universe,
                                      f"fixture_details was never called on the first result (id {first}), so its home team is unverified"))

    elif case_id == "B":
        counts = obs["counts"]
        if not counts:
            claims.append(_claim("B0", "fetched the per-team fixture counts", False, "team_fixture_counts never returned data"))
        else:
            top = sorted(counts, key=lambda t: (-t["fixture_count"], t["team_id"]))[0]
            claims.append(_claim("B1", "the team named is the one with the most fixtures", top["team_name"].lower() in answer.lower(),
                                 f"the counts put {top['team_name']} first; the answer names {names_in(answer, universe) or 'no team'}"))
            claims.append(_claim("B2", "the fixture count stated matches the aggregate",
                                 re.search(rf"(?<!\d){top['fixture_count']}(?!\d)", answer) is not None,
                                 f"the aggregate says {top['fixture_count']}"))
            if not codes:
                claims.append(_claim("B3", "an example fixture is named", False, "no fixture code appears in the answer"))
            for code in codes:
                fid = obs["code_to_id"].get(code)
                host = home_team_id(obs, fid) if fid is not None else None
                if fid is None:
                    claims.append(_claim("B3", f"{code} is hosted by the top team", False, f"{code} never appeared in any tool result"))
                elif host is None:
                    claims.append(_claim("B3", f"{code} is hosted by the top team", False, f"no evidence of who hosts {code}"))
                else:
                    claims.append(_claim("B3", f"{code} is hosted by the top team", host == top["team_id"],
                                         f"the tool data says {code} is hosted by {obs['team_names'].get(host, 'team ' + str(host))}, "
                                         f"not {top['team_name']}" if host != top["team_id"] else f"hosted by {top['team_name']}"))

    elif case_id == "C":
        search = next((s for s in obs["searches"] if "basketball" in s["query"].lower()), None)
        if search is None or len(search["ids"]) < 2:
            claims.append(_claim("C0", "searched for 'Basketball' and got two results", False, "no successful 'Basketball' search with two results"))
        else:
            want = [obs["cards"][i]["fixture_code"] for i in search["ids"][:2]]
            claims.append(_claim("C1", "the two fixtures shown are the first two search results", set(codes) == set(want),
                                 f"answer shows {codes or 'no codes'}; the first two results were {want}"))
            for n, code in enumerate(want, start=2):
                fid = obs["code_to_id"][code]
                claims.append(_home_claim(f"C{n}", code, home_team_name(obs, fid), answer, codes or want, universe,
                                          f"fixture_details was never called on {code}, so its home team is unverified"))
    else:
        raise ValueError(f"unknown case {case_id!r}")

    failed = [c for c in claims if not c["supported"]]
    return {"passed": not failed, "claims": claims, "unsupported_claims": len(failed),
            "feedback": [f"[{c['id']}] {c['claim']}: {c['why']}" for c in failed]}


# --------------------------------------------------------------------------- the oracle (database truth)
def oracle(case_id: str, answer: str | None, truth: dict) -> bool:
    """Is the answer TRUE? `truth` comes from ground_truth_extended(); no tool-grounding is required here."""
    if not answer:
        return False
    universe, codes = truth["team_names"], codes_in(answer)
    code_home = truth["code_home"]

    def home_ok(code):
        return code_home.get(code) in stated_home_names(segment_for(answer, code, codes), universe)

    if case_id == "A":
        return codes == [truth["A_first"]["fixture_code"]] and home_ok(codes[0])
    if case_id == "B":
        top = truth["B_top_team"]
        return (top["team_name"].lower() in answer.lower()
                and re.search(rf"(?<!\d){top['fixture_count']}(?!\d)", answer) is not None
                and bool(codes) and all(code_home.get(c) == top["team_name"] for c in codes))
    if case_id == "C":
        want = [f["fixture_code"] for f in truth["C_fixtures"]]
        return set(codes) == set(want) and all(home_ok(c) for c in want)
    raise ValueError(f"unknown case {case_id!r}")


def disagreement(verifier_passed: bool, oracle_ok: bool):
    """How the verifier and the oracle differ on one answer (None when they agree)."""
    if not verifier_passed and oracle_ok:
        return "false_rejection"
    if verifier_passed and not oracle_ok:
        return "false_acceptance"
    return None


def ground_truth_extended() -> dict:
    """ground_truth() plus the full fixture-code -> home-team table and the list of team names (one read-only SQL query)."""
    from agent_cases import ground_truth
    from agent_loop import quiet_noisy_loggers

    truth = ground_truth()
    quiet_noisy_loggers()
    sys.path.insert(0, str(Path(__file__).resolve().parent / "web_application"))
    from db import db_session_basede26
    from models import Fixture, Team

    db = db_session_basede26()
    try:
        truth["code_home"] = {code: name for code, name in
                              db.query(Fixture.fixture_code, Team.team_name).join(Team, Fixture.home_team_id == Team.id)}
        truth["team_names"] = [t.team_name for t in db.query(Team).order_by(Team.id)]
    finally:
        db.close()
    return truth
