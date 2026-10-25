"""
DATA-260 Homework 7 - Part 2: the contract of the three HW5 domain tools, as JSON Schema.

One definition used twice: (1) it is what the model is told about each tool, and (2) it is what the agent
loop checks every call against BEFORE the call runs. Pure Python (no database, no model), so it is testable
offline. The schemas are strict: unknown properties are rejected, so a made-up argument is caught instead of
being silently ignored.

The domain rule "search query must be at least 3 characters" stays in execute_tool (HW5 Part 5.I), so a
too-short query reaches the tool layer and gets its normal {ok: false, error: ...} answer.
"""

import json

from jsonschema import Draft202012Validator

TOOL_SPECS = {
    "search_fixtures": {
        "description": ("Search fixtures by name or teams_players (case-insensitive substring). Returns a list of "
                        "fixture cards (id, fixture_name, teams_players, fixture_code, spots_available, home_team_id). "
                        "The query must be at least 3 characters."),
        "parameters": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "minLength": 1, "description": "text to look for"},
                "limit": {"type": "integer", "minimum": 1, "maximum": 100, "description": "max results (default 10)"},
            },
            "required": ["query"],
            "additionalProperties": False,
        },
    },
    "fixture_details": {
        "description": ("Full details of ONE fixture by its integer id, including its home team "
                        "(team_name, team_code). Use an id taken from a search result; never guess one."),
        "parameters": {
            "type": "object",
            "properties": {"id": {"type": "integer", "minimum": 1, "description": "fixture id"}},
            "required": ["id"],
            "additionalProperties": False,
        },
    },
    "team_fixture_counts": {
        "description": ("Aggregate: how many fixtures each team hosts. Returns a list of "
                        "{team_id, team_code, team_name, fixture_count}."),
        "parameters": {
            "type": "object",
            "properties": {"min_fixtures": {"type": "integer", "minimum": 0,
                                            "description": "only teams hosting at least this many (default 0)"}},
            "required": [],
            "additionalProperties": False,
        },
    },
}

# Failure kinds the agent loop reports (the assignment groups the first two under "malformed arguments").
UNKNOWN_TOOL = "unknown_tool"
MALFORMED_ARGUMENTS = "malformed_arguments"   # arguments were not a JSON object at all
SCHEMA_VIOLATION = "schema_violation"         # a JSON object, but it breaks the tool's schema


def ollama_tools(specs: dict = TOOL_SPECS) -> list[dict]:
    """The tool list in the OpenAI-style function format that ChatOllama.bind_tools accepts."""
    return [{"type": "function",
             "function": {"name": name, "description": spec["description"], "parameters": spec["parameters"]}}
            for name, spec in specs.items()]


def validate_call(name: str, args, specs: dict = TOOL_SPECS):
    """Check one tool call. Returns None if it is well-formed, else (kind, human-readable problem)."""
    if name not in specs:
        return UNKNOWN_TOOL, f"there is no tool named {name!r}; the available tools are {sorted(specs)}"
    if not isinstance(args, dict):
        return MALFORMED_ARGUMENTS, (f"the arguments for {name} must be a JSON object, "
                                     f"got {type(args).__name__}: {str(args)[:80]!r}")
    errors = sorted(Draft202012Validator(specs[name]["parameters"]).iter_errors(args), key=lambda e: list(e.path))
    if errors:
        problems = []
        for e in errors:
            where = ".".join(str(p) for p in e.path)
            problems.append(f"argument {where!r}: {e.message}" if where else e.message)
        return SCHEMA_VIOLATION, "; ".join(problems)
    return None


def schema_hint(name: str, specs: dict = TOOL_SPECS) -> str:
    """Compact schema text appended to a repair message, so the model can see exactly what is allowed."""
    if name not in specs:
        return "Available tools: " + ", ".join(f"{n}({', '.join(s['parameters']['properties'])})" for n, s in specs.items())
    return f"Schema for {name}: " + json.dumps(specs[name]["parameters"])
