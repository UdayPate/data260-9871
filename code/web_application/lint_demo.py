"""Ruff + pre-commit demo file (HW7 Part 1.V).

This file is committed WITH deliberate lint errors on purpose, so the pre-commit hook can be seen
blocking the commit; the errors are then fixed and the commit goes through.
"""


def describe_role(role):
    return "role: " + role
