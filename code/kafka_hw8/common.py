"""
DATA-260 Homework 8 - shared constants, logging and Fixture validation.

Used by the worker (worker.py), the RPC client (kafka_rpc.py), the FastAPI wrapper
(api.py) and the demo (homework_demo.py). Nothing here talks to Kafka.
"""

import logging
import os
import re
import sys

PREFIX = "s9871"
PORT_BASE = 8871
REQUEST_TOPIC = f"{PREFIX}_entity_requests"
RESPONSE_TOPIC = f"{PREFIX}_entity_responses"

# Inside docker compose the broker is kafka:19092; from the host it is localhost:9092.
BOOTSTRAP = os.environ.get("KAFKA_BOOTSTRAP", "localhost:9092")

CATEGORIES = {"soccer": "Soccer", "basketball": "Basketball", "volleyball": "Volleyball", "cricket": "Cricket"}
FIXTURE_FIELDS = ("fixture_name", "teams_players", "submitter_email", "description", "category", "agree_terms")
_EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def setup_logging(name: str) -> logging.Logger:
    """One line per event: 'HH:MM:SS.mmm [name] message'. stdout, so `docker logs` shows it."""
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(logging.Formatter("%(asctime)s.%(msecs)03d [%(name)s] %(message)s", "%Y-%m-%d %H:%M:%S"))
    log = logging.getLogger(name)
    log.handlers[:] = [handler]
    log.setLevel(logging.INFO)
    log.propagate = False
    return log


def validate_fixture(data) -> tuple[dict | None, str | None]:
    """Return (clean_fixture, None) or (None, error). Rejects missing, empty, wrong-type and unknown fields."""
    if not isinstance(data, dict):
        return None, "data must be an object"
    unknown = sorted(set(data) - set(FIXTURE_FIELDS))
    if unknown:
        return None, f"Unknown field(s): {', '.join(unknown)}"
    clean: dict = {}
    for field in FIXTURE_FIELDS[:4]:
        value = data.get(field)
        if not isinstance(value, str) or not value.strip():
            return None, f"{field} is required and must be a non-empty string"
        clean[field] = value.strip()
    if len(clean["fixture_name"]) > 255 or len(clean["teams_players"]) > 255:
        return None, "fixture_name and teams_players must be at most 255 characters"
    if not _EMAIL.match(clean["submitter_email"]):
        return None, "submitter_email is not a valid email address"
    category = data.get("category")
    if not isinstance(category, str) or category.strip().lower() not in CATEGORIES:
        return None, f"category must be one of: {', '.join(CATEGORIES.values())}"
    clean["category"] = CATEGORIES[category.strip().lower()]
    if data.get("agree_terms") is not True:
        return None, "agree_terms must be true"
    clean["agree_terms"] = True
    return clean, None
