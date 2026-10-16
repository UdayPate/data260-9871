# AGENT.md — durable project and agent instructions

<!-- Loaded into every file-memory system prompt (HW6 Part 4). Expanded from the HW1 version. -->

## Project description
1. This project is a community sports league fixtures assistant (DATA-260, domain 7). Its entities are Fixture (a scheduled match between two teams) and Team; fixture categories are Soccer, Basketball, Volleyball and Cricket.

## Technology stack
2. Use Python 3.12 with FastAPI, Pydantic v2 and PyMongo; the local model is qwen3:8b called only through the adapter in src/model_client.py; MongoDB database name is s9871_doc.

## Coding conventions
3. Every Python function must have type hints on all parameters and on the return value, and a one-line docstring written entirely on a single line, with the opening and closing triple quotes on that same line, for example `"""Return the fixtures for one category."""`.
4. Use snake_case for function and variable names, and keep every function under 25 lines.

## Testing approach
5. Verify code by running it for real on sample data and checking the output; reading code is never sufficient evidence that it works.

## Prohibited actions
6. Never use eval(), exec(), or a bare `except:`; never use print() for logging (use the logging module instead).
7. Never run git add, git commit or git push on the user's behalf, and never fabricate numbers or results.

## Code review mode (kept from HW1)
8. When asked to review code, respond ONLY with a concise bulleted list of issues, with no prose outside the bullets; if there are no issues, respond with a single bullet saying so. For any request that is not a code review, respond normally and helpfully.
