"""
DATA-260 Homework 9 - Part 4: what a league question asks about, shared by the Answering Agent (to pick relevant lessons) and the
Evaluator Agent (to know which reference facts the answer must contain).

Questions are matched with word-boundary patterns. This keyword approach is deliberately simple and is the main limitation of the
system: a question phrased in a way these patterns do not know is treated as "asks about nothing recorded".
"""

import re

FIXTURE_CODE = re.compile(r"\bFX-9871-\d{5}\b", re.IGNORECASE)

# attribute -> pattern of the words that ask for it (checked on the lower-cased question)
ATTRIBUTES = {
    "home_team": re.compile(r"\bhome team\b|\bhosts?\b|\bhosting\b|\bhome side\b"),
    "home_ground": re.compile(r"\bhome ground\b|\bground\b|\bvenue\b|\bwhere\b"),
    "teams": re.compile(r"\bteams\b|\bwho is playing\b|\bwho plays\b|\bplaying in\b|\bfacing\b"),
    "spots": re.compile(r"\bspots?\b|\bslots?\b|\bplaces\b|\bopenings\b"),
    "fixture_name": re.compile(r"\bname\b|\bcalled\b|\btitle\b"),
}
# things a fixture question can ask about that the league database does not record
UNRECORDED = re.compile(r"\breferee\b|\bumpire\b|\bkick[- ]?off\b|\bstart time\b|\bwhat time\b|\bdate\b|\bscore\b|\bticket\b|\bprice\b|\bcost\b")


def fixture_codes(question: str) -> list[str]:
    return sorted({c.upper() for c in FIXTURE_CODE.findall(question)})


def attributes_asked(question: str) -> list[str]:
    q = question.lower()
    return [a for a, rx in ATTRIBUTES.items() if rx.search(q)]


def asks_unrecorded(question: str) -> bool:
    return bool(UNRECORDED.search(question.lower()))
