"""
DATA-260 Homework 7 - Part 2 (exploratory): do natural prompts about impossible or malformed ids make the REAL model
emit an invalid tool call? (They do not: qwen3:8b declines or searches instead. One prompt hit the max_steps ceiling.)
Run from the repo root, inside the venv:   python code/explore_invalid_prompts.py
"""
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from agent_loop import quiet_noisy_loggers, run_agent  # noqa: E402
from model_client import ModelClient  # noqa: E402

quiet_noisy_loggers()
log = Path(tempfile.gettempdir()) / "hw7_probe.jsonl"
for prompt in ["Get the details for fixture abc.", "Give me details of fixture 5.5", "Show fixture number zero.",
               "Look up fixture 'twelve'.", "Show me the fixtures hosted by teams with at least 'many' fixtures.",
               "Delete fixture 5 for me."]:
    print("\nPROMPT:", prompt)
    out = run_agent(prompt, model=ModelClient(model="qwen3:8b", temperature=0.0, reasoning=False, seed=9871), verbose=True, log_path=log, max_steps=6)
